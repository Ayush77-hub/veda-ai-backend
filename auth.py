"""
JWT Authentication utilities for API security.
This module provides enhanced JWT token management including token creation, validation,
automatic token refresh, and middleware for protected routes.
"""

import os
import jwt
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app, g

# JWT Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'veda-ai-secret-key')  # Default fallback for development
JWT_ALGORITHM = 'HS256'
JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)  # 1 hour by default
JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)  # 30 days by default
JWT_BLACKLIST = set()  # In-memory token blacklist for revoked tokens

def generate_jwt_token(user_id, token_type='access', custom_claims=None):
    """
    Generate a JWT token for the user with optional custom claims
    
    Args:
        user_id (int): The ID of the user
        token_type (str): The type of token ('access' or 'refresh')
        custom_claims (dict, optional): Additional claims to include in the token
        
    Returns:
        str: JWT token
    """
    payload = {
        'user_id': user_id,
        'type': token_type,
        'iat': datetime.utcnow(),
        'iss': 'veda-ai-backend',
        'jti': str(datetime.utcnow().timestamp())  # Unique token ID for potential blacklisting
    }
    
    # Add custom claims if provided
    if custom_claims and isinstance(custom_claims, dict):
        payload.update(custom_claims)
    
    # Set expiration based on token type
    if token_type == 'access':
        payload['exp'] = datetime.utcnow() + JWT_ACCESS_TOKEN_EXPIRES
    else:  # refresh token
        payload['exp'] = datetime.utcnow() + JWT_REFRESH_TOKEN_EXPIRES
    
    # Generate token
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token

def verify_jwt_token(token, verify_type=None):
    """
    Verify JWT token and return payload if valid
    
    Args:
        token (str): JWT token to verify
        verify_type (str, optional): Verify that token is of a specific type ('access' or 'refresh')
        
    Returns:
        dict or None: Decoded payload or None if token is invalid
    """
    try:
        # Decode the token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        # Check if token is blacklisted
        if payload.get('jti') in JWT_BLACKLIST:
            logging.warning(f"Token from blacklist used: {payload.get('jti')}")
            return None
        
        # Verify token type if specified
        if verify_type and payload.get('type') != verify_type:
            logging.warning(f"Invalid token type: expected {verify_type}, got {payload.get('type')}")
            return None
            
        return payload
    except jwt.ExpiredSignatureError:
        logging.info("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logging.warning(f"Invalid token: {str(e)}")
        return None

def blacklist_token(token):
    """
    Add a token to the blacklist
    
    Args:
        token (str): The JWT token to blacklist
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
        jti = payload.get('jti')
        if jti:
            JWT_BLACKLIST.add(jti)
            logging.info(f"Token blacklisted: {jti}")
    except jwt.InvalidTokenError:
        logging.warning("Attempted to blacklist invalid token")

def jwt_required(f=None, refresh=False, optional=False):
    """
    Decorator to protect routes with JWT authentication
    
    Args:
        f (function, optional): The route function
        refresh (bool): If True, require a refresh token instead of an access token
        optional (bool): If True, still call the route even if no token is provided
    
    Usage:
        @app.route('/api/protected')
        @jwt_required
        def protected_route():
            # This will only execute if a valid JWT token is provided
            return jsonify({'message': 'This is a protected route'})
            
        @app.route('/api/refresh')
        @jwt_required(refresh=True)
        def refresh_token_route():
            # This will only execute if a valid refresh token is provided
            return jsonify({'message': 'Token refreshed'})
    """
    def decorator(func):
        @wraps(func)
        def decorated(*args, **kwargs):
            token_type = 'refresh' if refresh else 'access'
            
            # Get token from header
            auth_header = request.headers.get('Authorization')
            
            # Check if token exists
            if not auth_header or not auth_header.startswith('Bearer '):
                if optional:
                    # For optional authentication, continue without a token
                    return func(*args, **kwargs)
                return jsonify({
                    'error': 'Authentication required',
                    'message': 'Missing or invalid Authorization header'
                }), 401
            
            # Extract token
            token = auth_header.split(' ')[1]
            
            # Verify token
            payload = verify_jwt_token(token, verify_type=token_type)
            if not payload:
                if optional:
                    # For optional authentication, continue without a valid token
                    return func(*args, **kwargs)
                    
                return jsonify({
                    'error': 'Authentication failed',
                    'message': 'Invalid or expired token',
                    'needs_refresh': True  # Hint to the frontend that a refresh might be needed
                }), 401
            
            # Store user info in request and flask g for access in the route
            request.user_id = payload['user_id']
            request.token_payload = payload
            g.user_id = payload['user_id']
            g.token_payload = payload
            
            # Continue to the route
            return func(*args, **kwargs)
        return decorated
    
    # If called without arguments
    if f:
        return decorator(f)
    
    # If called with arguments
    return decorator

def admin_required(f):
    """
    Decorator to protect routes for admin users only
    Must be used after jwt_required
    
    Usage:
        @app.route('/api/admin-only')
        @jwt_required
        @admin_required
        def admin_route():
            # This will only execute if a valid JWT token is provided and the user is an admin
            return jsonify({'message': 'This is an admin-only route'})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Check if user_id is set in request context (by jwt_required)
        if not hasattr(request, 'user_id'):
            return jsonify({'error': 'Authentication required'}), 401
            
        # Import here to avoid circular imports
        from models import User
        
        # Get user and check admin status
        user = User.query.get(request.user_id)
        if not user or not user.is_admin:
            return jsonify({'error': 'Admin privileges required'}), 403
        
        # Continue to the route
        return f(*args, **kwargs)
    return decorated

def get_current_user_id():
    """
    Helper function to get the current user ID from the JWT token
    
    Returns:
        int or None: The current user ID or None if not authenticated
    """
    # Try from Flask g first (fastest)
    if hasattr(g, 'user_id'):
        return g.user_id
        
    # Then try from request object
    if hasattr(request, 'user_id'):
        return request.user_id
        
    # Finally, try to extract from Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        payload = verify_jwt_token(token)
        if payload and 'user_id' in payload:
            # Store in g for future use in this request
            g.user_id = payload['user_id']
            return payload['user_id']
            
    return None

def get_token_payload():
    """
    Helper function to get the current token payload
    
    Returns:
        dict or None: The token payload or None if not authenticated
    """
    if hasattr(g, 'token_payload'):
        return g.token_payload
        
    if hasattr(request, 'token_payload'):
        return request.token_payload
        
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        payload = verify_jwt_token(token)
        if payload:
            g.token_payload = payload
            return payload
            
    return None