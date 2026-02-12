
import os
import json
import time
import uuid
import psutil
from datetime import datetime, timedelta
from flask import jsonify, request, session, send_from_directory, render_template, send_file, make_response
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import generate_password_hash
from sqlalchemy.sql import func, text
from extensions import db
# app is passed to register_routes, so we don't need to import it globally
from ai_providers import RESPONSE_CACHE, CACHE_MAX_SIZE

# AI providers availability flags
mistral_api_available = bool(os.environ.get("MISTRAL_API_KEY"))
perplexity_api_available = bool(os.environ.get("PERPLEXITY_API_KEY"))
from models import User, ChatMessage, Conversation
from ai_providers import generate_chat_response
from categories import (
    get_all_categories, get_category_by_id, get_subcategory_by_id, 
    get_all_topics, get_topic_info, get_category_name, get_subcategory_name, get_topic_name
)
from analytics import track_response_time, track_error, get_analytics_summary, get_database_analytics
from auth import (
    generate_jwt_token, verify_jwt_token, jwt_required, admin_required,
    get_current_user_id, get_token_payload, blacklist_token
)

def register_routes(app):
    # Custom scrollbar CSS route
    @app.route('/static/css/custom-scrollbar.css')
    def serve_custom_scrollbar():
        """Serve custom scrollbar CSS file"""
        return app.send_static_file('css/custom-scrollbar.css')
    
    # Root path to serve index.html
    @app.route('/')
    def index():
        """Serve the main index.html page for the SPA"""
        try:
            return send_from_directory(app.static_folder, 'index.html')
        except Exception as e:
            app.logger.error(f"Error serving index.html: {str(e)}")
            return jsonify({
                'error': 'Server error', 
                'message': 'An error occurred while serving the main page.'
            }), 500
    
    # API Status route
    @app.route('/api/status', methods=['GET'])
    def api_status():
        """Return basic API status information for health checks"""
        return jsonify({
            "status": "online",
            "version": "1.1.0",
            "apis": {
                "mistral": bool(os.environ.get("MISTRAL_API_KEY"))
            },
            "provider": "mistral",
            "message": "Veda AI Backend - Ready to serve Hindu sacred text knowledge with Mistral AI"
        })
    
    # User authentication routes
    @app.route('/api/auth/register', methods=['POST'])
    def register():
        data = request.get_json()
        
        # Validate request data
        if not data or not data.get('username') or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Missing required fields'}), 400
            
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        # Check if user already exists
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
            
        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'Email already exists'}), 400
            
        # Create new user
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Auto login the new user
        login_user(user)
        
        # Generate JWT tokens
        access_token = generate_jwt_token(user.id, 'access')
        refresh_token = generate_jwt_token(user.id, 'refresh')
        
        return jsonify({
            'message': 'User created successfully', 
            'user': user.to_dict(),
            'tokens': {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_type': 'Bearer'
            }
        
        }), 201
    
    @app.route('/api/auth/login', methods=['POST'])
    def login():
        data = request.get_json()
        
        # Validate request data
        if not data or (not data.get('username') and not data.get('email')) or not data.get('password'):
            return jsonify({'error': 'Missing required fields'}), 400
            
        identifier = data.get('username') or data.get('email')
        password = data.get('password')
        
        # Find user by username or email
        user = User.query.filter_by(username=identifier).first() or User.query.filter_by(email=identifier).first()
        
        if not user or not user.check_password(password):
            return jsonify({'error': 'Invalid username/email or password'}), 401
            
        # Login the user
        login_user(user)
    
        
        # Generate JWT tokens
        access_token = generate_jwt_token(user.id, 'access')
        refresh_token = generate_jwt_token(user.id, 'refresh')
        
        return jsonify({
            'message': 'Login successful', 
            'user': user.to_dict(),
            'tokens': {
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_type': 'Bearer'
            }
        }), 200
    
    @app.route('/api/auth/logout', methods=['POST'])
    @login_required
    def logout():
        logout_user()
        return jsonify({'message': 'Logout successful'}), 200
    
    @app.route('/api/auth/user', methods=['GET'])
    def get_current_user():
        # Check if there's a valid token
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if token:
            # Verify token
            payload = verify_jwt_token(token)
            if payload and 'user_id' in payload:
                user_id = payload['user_id']
                user = User.query.get(user_id)
                if user:
                    return jsonify({'user': user.to_dict()}), 200
        
        return jsonify({'user': None}), 200
        
    @app.route('/api/auth/refresh', methods=['POST'])
    def refresh_token():
        """Refresh access token using a valid refresh token"""
        data = request.get_json()
        
        if not data or not data.get('refresh_token'):
            return jsonify({'error': 'Missing refresh token'}), 400
            
        refresh_token = data.get('refresh_token')
        
        # Verify refresh token
        payload = verify_jwt_token(refresh_token)
        if not payload or payload.get('type') != 'refresh':
            return jsonify({'error': 'Invalid or expired refresh token'}), 401
            
        # Get user from token
        user_id = payload.get('user_id')
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        # Generate new access token
        access_token = generate_jwt_token(user.id, 'access')
        
        return jsonify({
            'access_token': access_token,
            'token_type': 'Bearer'
        }), 200
    
    @app.route('/api/auth/protected', methods=['GET'])
    @jwt_required
    def protected_route():
        """Test route for JWT authentication"""
        # Get user from token (user_id is set by jwt_required decorator)
        user = User.query.get(request.user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        return jsonify({
            'message': 'This is a protected route',
            'user_id': user.id,
            'username': user.username
        }), 200
        
    @app.route('/api/auth/admin', methods=['GET'])
    @jwt_required
    @admin_required
    def admin_route():
        """Test route for admin-only access"""
        # Get user from token (user_id is set by jwt_required decorator)
        user = User.query.get(request.user_id)
        
        return jsonify({
            'message': 'This is an admin-only route',
            'user_id': user.id,
            'username': user.username,
            'is_admin': user.is_admin
        }), 200
    
    # Conversation routes
    @app.route('/api/conversations', methods=['GET'])
    @jwt_required(optional=True)  # Allow both authenticated and anonymous users
    def get_conversations():
        """Get conversations for the current user or public anonymous conversations"""
        # Get query parameters
        category = request.args.get('category')
        topic = request.args.get('topic')
        search = request.args.get('search')
        public_only = request.args.get('public_only', 'false').lower() == 'true'
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Limit per_page to reasonable values
        if per_page > 50:
            per_page = 50
        
        # Get user_id using the helper function from auth.py    
        user_id = get_current_user_id()
        
        # Build the query based on authentication status
        if user_id and not public_only:
            # For authenticated users, show their own conversations
            query = Conversation.query.filter_by(user_id=user_id)
        else:
            # For anonymous users or when public_only is true, show only public conversations
            query = Conversation.query.filter_by(user_id=None)
        
        # Apply category and topic filters if provided
        if category:
            query = query.filter_by(category=category)
        
        if topic:
            query = query.filter_by(topic=topic)
            
        # Apply search filter if provided
        if search and search.strip():
            # Search in conversation titles
            search_term = f"%{search.strip()}%"
            
            # First try to search by title
            title_matches = query.filter(Conversation.title.ilike(search_term))
            
            # If we have a direct match by title, prioritize those results
            if title_matches.count() > 0:
                query = title_matches
            else:
                # Otherwise, search in messages within those conversations
                # This is a more complex query that joins conversations with their messages
                conversation_ids = db.session.query(ChatMessage.conversation_id).distinct()\
                    .filter(ChatMessage.conversation_id.isnot(None))\
                    .filter(db.or_(
                        ChatMessage.message.ilike(search_term),
                        ChatMessage.response.ilike(search_term)
                    ))
                
                # Apply user filter to the subquery
                if user_id and not public_only:
                    conversation_ids = conversation_ids.join(Conversation)\
                        .filter(Conversation.user_id == user_id)
                else:
                    conversation_ids = conversation_ids.join(Conversation)\
                        .filter(Conversation.user_id.is_(None))
                
                # Apply category and topic filters to the subquery if needed
                if category:
                    conversation_ids = conversation_ids.filter(Conversation.category == category)
                if topic:
                    conversation_ids = conversation_ids.filter(Conversation.topic == topic)
                
                # Get the actual IDs
                conversation_ids = [r[0] for r in conversation_ids.all()]
                
                # Filter the main query to include these conversation IDs
                if conversation_ids:
                    query = query.filter(Conversation.id.in_(conversation_ids))
                else:
                    # No matches found in messages, return empty set
                    query = query.filter(False)
        
        # Order by updated_at (newest first)
        query = query.order_by(Conversation.updated_at.desc())
        
        # Apply pagination
        total = query.count()
        conversations = query.offset((page - 1) * per_page).limit(per_page).all()
        
        # Calculate pagination metadata
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
        has_next = page < total_pages
        has_prev = page > 1
        
        return jsonify({
            'conversations': [conv.to_dict() for conv in conversations],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_prev': has_prev
            }
        }), 200
    
    @app.route('/api/conversations/<int:conversation_id>', methods=['GET'])
    @jwt_required(optional=True)  # Allow both authenticated and anonymous users
    def get_conversation(conversation_id):
        """Get a specific conversation with its messages"""
        app.logger.info(f"Retrieving conversation with ID: {conversation_id}")
        
        try:
            conversation = Conversation.query.get(conversation_id)
            if not conversation:
                app.logger.warning(f"Conversation ID {conversation_id} not found")
                return jsonify({'error': 'Conversation not found'}), 404
            
            # Get user ID using helper function
            user_id = get_current_user_id()
            
            # Check if user is admin
            is_admin = False
            if user_id:
                user = User.query.get(user_id)
                is_admin = user and user.is_admin
            
            # Check user permission for authenticated users
            if user_id:
                if conversation.user_id and conversation.user_id != user_id and not is_admin:
                    app.logger.warning(f"Unauthorized access attempt for conversation {conversation_id} by user {user_id}")
                    return jsonify({'error': 'Unauthorized access to conversation'}), 403
            
            # For anonymous users, only allow access to conversations with null user_id
            elif conversation.user_id is not None:
                app.logger.warning(f"Anonymous user attempted to access private conversation {conversation_id}")
                return jsonify({'error': 'Unauthorized access to conversation'}), 403
            
            # Convert conversation to a dictionary with messages
            conversation_dict = conversation.to_dict(include_messages=True)
            
            # Extract messages from the conversation dict for frontend compatibility
            messages = conversation_dict.pop('messages', [])
            
            app.logger.info(f"Successfully retrieved conversation {conversation_id} with {len(messages)} messages")
            
            # Return in a format consistent with frontend expectations
            return jsonify({
                'conversation': conversation_dict,
                'messages': messages
            }), 200
            
        except Exception as e:
            app.logger.error(f"Error retrieving conversation {conversation_id}: {str(e)}")
            return jsonify({'error': f'Error retrieving conversation: {str(e)}'}), 500
    
    @app.route('/api/conversations', methods=['POST'])
    @jwt_required
    def create_conversation():
        """Create a new conversation"""
        data = request.get_json()
        
        # Validate request data
        if not data or not data.get('category') or not data.get('topic'):
            return jsonify({'error': 'Missing required fields'}), 400
            
        title = data.get('title', "New Conversation")
        category = data.get('category')
        topic = data.get('topic')
        
        # Validate category and topic exist
        if not get_category_by_id(category):
            return jsonify({'error': f'Invalid category: {category}'}), 400
    
             # Get topic information
        topic_info = get_topic_info(topic, category)
        if not topic_info:
            return jsonify({'error': f'Invalid topic: {topic} for category: {category}'}), 400
         
        # Get user from JWT token
        user_id = request.user_id
        t
        
        # Create new conversation
        conversation = Conversation(
            user_id=user_id,
            title=title,
            category=category,
            topic=topic
        )
        
        db.session.add(conversation)
        db.session.commit()
        
        return jsonify({
            'message': 'Conversation created successfully',
            'conversation': conversation.to_dict()
        }), 201
    
    @app.route('/api/conversations/<int:conversation_id>', methods=['DELETE'])
    @jwt_required
    def delete_conversation(conversation_id):
        """Delete a conversation"""
        conversation = Conversation.query.get_or_404(conversation_id)
        
        # Get user ID from JWT token
        user_id = request.user_id
        user = User.query.get(user_id)
        
        # Check user permission
        if conversation.user_id != user_id and not user.is_admin:
            return jsonify({'error': 'Unauthorized access to conversation'}), 403
            
        db.session.delete(conversation)
        db.session.commit()
        
        return jsonify({'message': 'Conversation deleted successfully'}), 200
    
    @app.route('/api/conversations/<int:conversation_id>/rename', methods=['PUT'])
    @jwt_required
    def rename_conversation(conversation_id):
        """Rename a conversation"""
        data = request.get_json()
        conversation = Conversation.query.get_or_404(conversation_id)
        
        # Get user ID from JWT token
        user_id = request.user_id
        user = User.query.get(user_id)
        
        # Check user permission
        if conversation.user_id != user_id and not user.is_admin:
            return jsonify({'error': 'Unauthorized access to conversation'}), 403
            
        if not data or not data.get('title'):
            return jsonify({'error': 'Missing title field'}), 400
            
        conversation.title = data.get('title')
        db.session.commit()
        
        return jsonify({
            'message': 'Conversation renamed successfully',
            'conversation': conversation.to_dict()
        }), 200
    
    # Health check endpoint for system monitoring
    @app.route('/api/health', methods=['GET'])
    def health_check():
        """
        Health check endpoint for system monitoring and status verification.
        
        Checks database connection, AI provider availability, and system metrics.
        Returns detailed health status of various components.
        """
        health_data = {
            'status': 'ok',
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0',
            'components': {}
        }
        
        # Check database connection
        try:
            # Simple database query to verify connection
            db_start_time = time.time()
            db.session.execute(text('SELECT 1')).scalar()
            db_response_time = time.time() - db_start_time
            
            health_data['components']['database'] = {
                'status': 'ok',
                'response_time_ms': round(db_response_time * 1000, 2)
            }
        except Exception as e:
            health_data['status'] = 'degraded'
            health_data['components']['database'] = {
                'status': 'error',
                'message': 'Database connection failed'
            }
            app.logger.error(f"Health check - Database error: {str(e)}")
        
        # Check AI provider availability
        ai_providers_status = {
            'mistral': mistral_api_available,
            'perplexity': perplexity_api_available
        }
        
        health_data['components']['ai_providers'] = {
            'status': 'ok' if any(ai_providers_status.values()) else 'error',
            'providers': ai_providers_status
        }
        
        if not any(ai_providers_status.values()):
            health_data['status'] = 'critical'
        
        # Check cache status
        try:
            cache_size = len(RESPONSE_CACHE)
            health_data['components']['cache'] = {
                'status': 'ok',
                'size': cache_size,
                'max_size': CACHE_MAX_SIZE,
                'utilization_percent': round((cache_size / CACHE_MAX_SIZE) * 100, 2) if CACHE_MAX_SIZE > 0 else 0
            }
        except Exception as e:
            health_data['components']['cache'] = {
                'status': 'error',
                'message': 'Cache status check failed'
            }
            app.logger.error(f"Health check - Cache error: {str(e)}")
        
        # Include system metrics
        import psutil
        try:
            memory = psutil.virtual_memory()
            health_data['components']['system'] = {
                'status': 'ok',
                'cpu_percent': psutil.cpu_percent(interval=0.1),
                'memory_percent': memory.percent,
                'memory_available_mb': round(memory.available / (1024 * 1024), 2)
            }
        except Exception:
            # Don't fail the health check if we can't get system metrics
            health_data['components']['system'] = {
                'status': 'unknown',
                'message': 'System metrics unavailable'
            }
        
        # Return appropriate status code based on overall health
        status_code = 200  # OK
        if health_data['status'] == 'critical':
            status_code = 503  # Service Unavailable
        elif health_data['status'] == 'degraded':
            status_code = 200  # Still OK but with warnings
        
        return jsonify(health_data), status_code

    # Chat message routes
    @app.route('/api/chat', methods=['POST'])
    @jwt_required(optional=True)  # Allow both authenticated and anonymous users
    def chat():
        """
        Generate a chat response based on user input, category, and topic.
        
        This endpoint processes chat requests, validates parameters, generates AI responses,
        and manages conversation history with database storage.
        """
        import uuid
        
        # Start timing for performance tracking
        start_time = datetime.utcnow()
        request_id = str(uuid.uuid4())
        
        # Validate request data with improved error messages
        data = request.get_json()
        if not data:
            return jsonify({
                'error': 'Invalid request',
                'details': 'Request body must contain valid JSON',
                'request_id': request_id
            }), 400
        
        # Check required fields with detailed feedback
        required_fields = ['message', 'category', 'topic']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return jsonify({
                'error': 'Missing required fields', 
                'details': f"Required fields: {', '.join(missing_fields)}",
                'request_id': request_id
            }), 400
            
        message = data.get('message')
        category = data.get('category')
        topic = data.get('topic')
        conversation_id = data.get('conversation_id')  # Optional parameter for existing conversation
        provider = data.get('provider')  # Optional parameter to specify AI provider
        
        # Get user_id using helper function from auth.py
        user_id = get_current_user_id()
        
        # Check if user is admin
        is_admin = False
        if user_id:
            user = User.query.get(user_id)
            is_admin = user and user.is_admin
        
        # Rate limiting - check for excessive requests
        # In future this could be enhanced with redis or a more sophisticated rate limiter
        if not user_id:
            app.logger.info("Unauthenticated user chat request")
            # Allow anonymous users but log this for monitoring
        
        # Validate category and topic exist
        if not get_category_by_id(category):
            return jsonify({'error': f'Invalid category: {category}'}), 400
            
        # Get topic information
        topic_info = get_topic_info(topic, category)
        if not topic_info:
            return jsonify({'error': f'Invalid topic: {topic} for category: {category}'}), 400
        
        # Find or create conversation (for both authenticated and anonymous users)
        conversation = None
        if conversation_id:
            # Use existing conversation
            conversation = Conversation.query.get(conversation_id)
            
            # Verify conversation belongs to user (only if user is authenticated)
            if conversation and user_id and conversation.user_id and conversation.user_id != user_id and not is_admin:
                return jsonify({'error': 'Unauthorized access to conversation'}), 403
                
            # If conversation doesn't exist, log it but don't throw an error
            if not conversation:
                app.logger.warning(f"Conversation ID {conversation_id} not found, will create a new conversation")
        
        # Track start time for response timing
        start_time = datetime.utcnow()
        
        try:
            # Generate AI response with optional provider
            ai_response = generate_chat_response(message, category, topic, provider)
            
            # Calculate response time
            response_time = (datetime.utcnow() - start_time).total_seconds()
            app.logger.info(f"Response generation time: {response_time:.2f} seconds")
            
            # We're only using Mistral AI provider
            response_provider = "mistral"
            
            # Track analytics for successful response
            # Determine which model was used based on is_short_query pattern in ai_providers.py
            is_short_query = len(message.split()) <= 3 or message.lower().strip() in [
                "hi", "hello", "hey", "namaste", "ram ram", "jai shree krishna", "jai shree ram"
            ]
            model = "mistral-small-latest" if is_short_query else "mistral-large-latest"
            track_response_time(category, topic, model, response_time)
            
            # Only save successful responses to the database
            if ai_response and 'response' in ai_response:
                # Create conversation if needed (for both authenticated and anonymous users)
                if not conversation:
                    conversation = Conversation(
                        user_id=user_id,  # Will be NULL for anonymous users
                        category=category,
                        topic=topic
                    )
                    db.session.add(conversation)
                    db.session.flush()  # Get ID without committing
                    
                # Save the message to the database
                chat_message = ChatMessage(
                    user_id=user_id,
                    message=message,
                    response=ai_response['response'],
                    category=category,
                    topic=topic
                )
                
                # Link to conversation if available
                if conversation:
                    chat_message.conversation_id = conversation.id
                    # Update conversation timestamp
                    conversation.updated_at = datetime.utcnow()
                
                db.session.add(chat_message)
                db.session.commit()
                
                # If this is the first message in a conversation, update the title
                if conversation and conversation.messages.count() == 1:
                    conversation.generate_title()
                    db.session.commit()
                
                app.logger.info(f"Chat message saved to database with ID: {chat_message.id}")
                
                # Include conversation info in response if available
                conversation_info = None
                if conversation:
                    conversation_info = {
                        'id': conversation.id,
                        'title': conversation.title
                    }
                
            else:
                app.logger.warning("No valid response received from AI provider")
            
            # Format response for frontend
            response_data = {
                'response': ai_response.get('response', 'No response generated'),
                'timestamp': datetime.utcnow().isoformat(),
                'category': category,
                'topic': topic,
                'provider': response_provider,
                'response_time': response_time
            }
            
            # Add conversation info if available
            if conversation:
                response_data['conversation'] = {
                    'id': conversation.id,
                    'title': conversation.title
                }
            
            return jsonify(response_data), 200
            
        except Exception as e:
            app.logger.error(f"Error in chat endpoint: {str(e)}")
            
            # Track error for analytics
            error_type = type(e).__name__
            track_error(category, topic, error_type, str(e))
            
            # Create culturally appropriate error response
            error_response = {
                'response': "Jay Shree Krishna 🙏 I apologize, but I'm experiencing technical difficulties at the moment. Please try again shortly.",
                'timestamp': datetime.utcnow().isoformat(),
                'error': str(e),
                'category': category,
                'topic': topic
            }
            return jsonify(error_response), 200  # Return 200 with error message rather than 500 for better UX
    
    @app.route('/api/messages', methods=['GET'])
    @jwt_required
    def get_user_messages():
        # Get query parameters
        category = request.args.get('category')
        topic = request.args.get('topic')
        
        # Get user ID from JWT token
        user_id = request.user_id
        
        query = ChatMessage.query.filter_by(user_id=user_id)
        
        if category:
            query = query.filter_by(category=category)
        
        if topic:
            query = query.filter_by(topic=topic)
        
        # Order by created_at (newest first)
        messages = query.order_by(ChatMessage.created_at.desc()).all()
        
        return jsonify({'messages': [msg.to_dict() for msg in messages]}), 200
    
    # Admin routes
    @app.route('/api/admin/users', methods=['GET'])
    @jwt_required
    @admin_required
    def get_all_users():
        users = User.query.all()
        return jsonify({'users': [user.to_dict() for user in users]}), 200
    
    @app.route('/api/admin/messages', methods=['GET'])
    @jwt_required
    @admin_required
    def get_all_messages():
        messages = ChatMessage.query.order_by(ChatMessage.created_at.desc()).all()
        return jsonify({'messages': [msg.to_dict() for msg in messages]}), 200
    
    @app.route('/api/admin/analytics', methods=['GET'])
    @jwt_required
    @admin_required
    def get_admin_analytics():
        """Get analytics data for administrators"""
        # Get in-memory analytics summary
        memory_analytics = get_analytics_summary()
        
        # Get database analytics
        db_analytics = get_database_analytics(db)
        
        # Get time-based analytics
        time_period = request.args.get('period', 'day')
        time_analytics = {}
        
        if time_period == 'hour':
            # Get hourly data for the last 24 hours
            hourly_data = []
            for hour in range(24):
                start_time = datetime.utcnow() - timedelta(hours=24-hour)
                end_time = datetime.utcnow() - timedelta(hours=23-hour)
                count = ChatMessage.query.filter(
                    ChatMessage.created_at >= start_time,
                    ChatMessage.created_at < end_time
                ).count()
                hourly_data.append({
                    'hour': hour,
                    'count': count,
                    'time': start_time.strftime('%H:00')
                })
            time_analytics['hourly'] = hourly_data
            
        elif time_period == 'week':
            # Get daily data for the last 7 days
            daily_data = []
            for day in range(7):
                start_time = datetime.utcnow() - timedelta(days=7-day)
                end_time = datetime.utcnow() - timedelta(days=6-day)
                count = ChatMessage.query.filter(
                    ChatMessage.created_at >= start_time,
                    ChatMessage.created_at < end_time
                ).count()
                daily_data.append({
                    'day': day,
                    'count': count,
                    'time': start_time.strftime('%A')
                })
            time_analytics['daily'] = daily_data
            
        else:  # default to daily
            # Get daily data for the last 30 days
            daily_data = []
            for day in range(30):
                start_time = datetime.utcnow() - timedelta(days=30-day)
                end_time = datetime.utcnow() - timedelta(days=29-day)
                count = ChatMessage.query.filter(
                    ChatMessage.created_at >= start_time,
                    ChatMessage.created_at < end_time
                ).count()
                daily_data.append({
                    'day': day,
                    'count': count,
                    'time': start_time.strftime('%d %b')
                })
            time_analytics['daily'] = daily_data
            
        # Combine analytics data
        analytics_data = {
            'memory_analytics': memory_analytics,
            'database_analytics': db_analytics,
            'time_analytics': time_analytics,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return jsonify(analytics_data), 200
    
    @app.route('/api/admin/analytics/export', methods=['GET'])
    @jwt_required
    @admin_required
    def export_analytics():
        """
        Export analytics data as CSV for administrators
        Formats include:
        - responses: Response time data for each request
        - errors: Error data for each failed request
        - summary: Summary of all analytics data
        """
            
        export_format = request.args.get('format', 'summary')
        
        # Get analytics data
        memory_analytics = get_analytics_summary()
        db_analytics = get_database_analytics(db)
        
        # Create CSV data based on requested format
        if export_format == 'responses':
            # Export detailed response time data
            response_data = []
            
            # Get last 1000 messages for analysis
            messages = ChatMessage.query.order_by(
                ChatMessage.created_at.desc()
            ).limit(1000).all()
            
            # CSV headers
            csv_data = "id,category,topic,created_at,message_length,response_length\n"
            
            # Add message data
            for msg in messages:
                csv_data += f"{msg.id},{msg.category},{msg.topic},{msg.created_at},"
                csv_data += f"{len(msg.message)},{len(msg.response)}\n"
                
            # Set response headers
            response = make_response(csv_data)
            response.headers["Content-Disposition"] = "attachment; filename=response_analytics.csv"
            response.headers["Content-Type"] = "text/csv"
            return response
            
        elif export_format == 'errors':
            # Get error data from memory analytics
            csv_data = "category,topic,error_type,error_message,timestamp\n"
            
            # We don't store error timestamps in memory, so we'll use current time
            timestamp = datetime.utcnow().isoformat()
            
            # Add error data
            for error_type, count in memory_analytics.get('top_errors', []):
                # Format: error_type (category:topic)
                parts = error_type.split(' (')
                if len(parts) == 2:
                    error_name = parts[0]
                    category_topic = parts[1].rstrip(')')
                    if ':' in category_topic:
                        category, topic = category_topic.split(':')
                        csv_data += f"{category},{topic},{error_name},\"Error occurred\",{timestamp}\n"
            
            # Set response headers
            response = make_response(csv_data)
            response.headers["Content-Disposition"] = "attachment; filename=error_analytics.csv"
            response.headers["Content-Type"] = "text/csv"
            return response
            
        else:  # summary format
            # Create summary CSV
            csv_data = "metric,value\n"
            
            # Database analytics
            csv_data += f"total_users,{db_analytics['total_users']}\n"
            csv_data += f"total_conversations,{db_analytics['total_conversations']}\n"
            csv_data += f"total_messages,{db_analytics['total_messages']}\n"
            csv_data += f"messages_last_24h,{db_analytics['messages_last_24h']}\n"
            csv_data += f"avg_messages_per_conversation,{db_analytics['avg_messages_per_conversation']}\n"
            
            # Memory analytics
            csv_data += f"successful_requests,{memory_analytics['successful_requests']}\n"
            csv_data += f"total_requests,{memory_analytics['total_requests']}\n"
            csv_data += f"success_rate,{memory_analytics['success_rate']}\n"
            csv_data += f"avg_response_time,{memory_analytics['avg_response_time']}\n"
            
            # Add timestamp
            csv_data += f"timestamp,{datetime.utcnow().isoformat()}\n"
            
            # Top categories and topics - database
            csv_data += "\ncategory,count\n"
            for category in db_analytics['top_categories']:
                csv_data += f"{category['category']},{category['count']}\n"
                
            csv_data += "\ntopic,count\n"
            for topic in db_analytics['top_topics']:
                csv_data += f"{topic['topic']},{topic['count']}\n"
            
            # Set response headers
            response = make_response(csv_data)
            response.headers["Content-Disposition"] = "attachment; filename=analytics_summary.csv"
            response.headers["Content-Type"] = "text/csv"
            return response
    
    # Categories and Topics routes
    @app.route('/api/categories', methods=['GET'])
    def get_categories():
        """Get all categories with their subcategories and topics"""
        categories = get_all_categories()
        return jsonify({'categories': categories}), 200
    
    @app.route('/api/categories/<category_id>', methods=['GET'])
    def get_category(category_id):
        """Get a specific category by id"""
        category = get_category_by_id(category_id)
        
        if not category:
            return jsonify({'error': 'Category not found'}), 404
            
        return jsonify({'category': category}), 200
        
    @app.route('/api/categories/<category_id>/subcategories/<subcategory_id>', methods=['GET'])
    def get_subcategory(category_id, subcategory_id):
        """Get a specific subcategory by id"""
        subcategory = get_subcategory_by_id(category_id, subcategory_id)
        
        if not subcategory:
            return jsonify({'error': 'Subcategory not found'}), 404
            
        return jsonify({'subcategory': subcategory}), 200
        
    @app.route('/api/topics', methods=['GET'])
    def get_topics():
        """Get all topics"""
        topics = get_all_topics()
        return jsonify({'topics': topics}), 200
        
    @app.route('/api/suggested-topics', methods=['GET'])
    def get_suggested_topics():
        """Get suggested topics based on user's conversation history or popular topics"""
        # Get query parameters
        limit = min(request.args.get('limit', 5, type=int), 10)  # Max 10 suggestions
        
        # Check if there's a valid token
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        user_id = None
        if token:
            # Verify token
            payload = verify_jwt_token(token)
            if payload and 'user_id' in payload:
                user_id = payload['user_id']
        
        if user_id:
            # For authenticated users, suggest topics based on their history
            # First, get the user's recent topics from their conversations
            recent_topics = db.session.query(Conversation.topic, 
                                            Conversation.category,
                                            func.count(Conversation.id).label('count')) \
                                .filter(Conversation.user_id == user_id) \
                                .group_by(Conversation.topic, Conversation.category) \
                                .order_by(func.count(Conversation.id).desc()) \
                                .limit(limit) \
                                .all()
                                
            # Format results
            suggestions = []
            for topic, category, count in recent_topics:
                topic_info = get_topic_info(topic, category)
                if topic_info:  # Make sure the topic still exists in our catalog
                    suggestions.append({
                        'topic': topic,
                        'topic_name': get_topic_name(topic),
                        'category': category,
                        'category_name': get_category_name(category),
                        'count': count
                    })
            
            # If user has no history or limited history, supplement with popular topics
            if len(suggestions) < limit:
                # Get popular topics excluding the ones already added
                existing_topics = [s['topic'] for s in suggestions]
                popular_topics = db.session.query(ChatMessage.topic, 
                                                ChatMessage.category,
                                                func.count(ChatMessage.id).label('count')) \
                                    .filter(ChatMessage.topic.notin_(existing_topics)) \
                                    .group_by(ChatMessage.topic, ChatMessage.category) \
                                    .order_by(func.count(ChatMessage.id).desc()) \
                                    .limit(limit - len(suggestions)) \
                                    .all()
                                    
                for topic, category, count in popular_topics:
                    topic_info = get_topic_info(topic, category)
                    if topic_info:
                        suggestions.append({
                            'topic': topic,
                            'topic_name': get_topic_name(topic),
                            'category': category,
                            'category_name': get_category_name(category),
                            'count': count,
                            'is_popular': True
                        })
        else:
            # For anonymous users, suggest popular topics
            popular_topics = db.session.query(ChatMessage.topic, 
                                            ChatMessage.category,
                                            func.count(ChatMessage.id).label('count')) \
                                .group_by(ChatMessage.topic, ChatMessage.category) \
                                .order_by(func.count(ChatMessage.id).desc()) \
                                .limit(limit) \
                                .all()
                                
            suggestions = []
            for topic, category, count in popular_topics:
                topic_info = get_topic_info(topic, category)
                if topic_info:
                    suggestions.append({
                        'topic': topic,
                        'topic_name': get_topic_name(topic),
                        'category': category,
                        'category_name': get_category_name(category),
                        'count': count,
                        'is_popular': True
                    })
        
        return jsonify({'suggestions': suggestions}), 200
        
    @app.route('/api/topics/<topic_id>', methods=['GET'])
    def get_topic(topic_id):
        """Get topic info by id"""
        category_id = request.args.get('category_id')
        subcategory_id = request.args.get('subcategory_id')
        
        topic = get_topic_info(topic_id, category_id, subcategory_id)
        
        if not topic:
            return jsonify({'error': 'Topic not found'}), 404
            
        return jsonify({'topic': topic}), 200
    
    # Catch-all route for the SPA
    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def catch_all(path):
        """
        This catch-all route is added to allow the frontend to use client-side routing.
        The API routes are handled first, and this is used as a fallback to serve
        the index.html file for the Single Page Application.
        """
        # Return a 404 response with JSON for API endpoints that don't exist
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Not found',
                'message': f'The endpoint {request.path} does not exist.'
            }), 404
                    
        # Special handling for source files and assets - allow direct access
        if path.startswith('src/') or path.startswith('assets/'):
            # Clean the path to prevent directory traversal
            safe_path = os.path.normpath(path).lstrip('/')
            
            # First try to serve from static folder
            try:
                static_file_path = os.path.join(app.static_folder, safe_path)
                if os.path.exists(static_file_path) and os.path.isfile(static_file_path):
                    return send_from_directory(app.static_folder, safe_path)
            except:
                app.logger.warning(f"Failed to serve file from static folder: {safe_path}")
                pass
                
            # If not found in static, check attached_assets folder
            if path.startswith('src/'):
                try:
                    # Remove the 'src/' prefix since files are directly in attached_assets
                    asset_path = path.replace('src/', '')
                    asset_file_path = os.path.join('attached_assets', asset_path)
                    
                    if os.path.exists(asset_file_path) and os.path.isfile(asset_file_path):
                        # Set appropriate mimetype based on file extension
                        extension = os.path.splitext(asset_file_path)[1].lower()
                        mimetype = {
                            '.js': 'text/javascript',
                            '.jsx': 'text/javascript',
                            '.ts': 'text/javascript',
                            '.tsx': 'text/javascript',
                            '.css': 'text/css',
                            '.json': 'application/json',
                            '.svg': 'image/svg+xml',
                            '.png': 'image/png',
                            '.jpg': 'image/jpeg',
                            '.jpeg': 'image/jpeg',
                        }.get(extension, 'text/plain')
                        
                        return send_file(asset_file_path, mimetype=mimetype)
                except Exception as e:
                    app.logger.warning(f"Failed to serve file from attached_assets: {path.replace('src/', '')}, Error: {str(e)}")
                    pass
                
        # Check if the specific file exists in the static folder
        try:
            static_file_path = os.path.join(app.static_folder, path)
            if os.path.exists(static_file_path) and os.path.isfile(static_file_path):
                return send_from_directory(app.static_folder, path)
        except:
            app.logger.warning(f"Failed to check or serve file: {path}")
            pass
            
        # For all other routes, serve the index.html file (for client-side routing)
        try:
            return send_from_directory(app.static_folder, 'index.html')
        except Exception as e:
            app.logger.error(f"Error serving index.html: {str(e)}")
            return jsonify({
                'error': 'Server error', 
                'message': 'An error occurred while serving the requested page.'
            }), 500