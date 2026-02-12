"""
Analytics module for tracking conversation metrics and performance.

This module provides functionality to track and analyze various metrics
related to chat conversations, including response times, success rates,
and user engagement patterns.
"""

import logging
import time
from datetime import datetime, timedelta
from functools import wraps
from flask import request, g
from sqlalchemy import func, desc
from models import ChatMessage, Conversation, User

# Configure logging
logger = logging.getLogger(__name__)

# In-memory analytics store for current session
# This will be lost on server restart - for persistent analytics use the database
ANALYTICS_STORE = {
    'response_times': [],
    'requests_per_category': {},
    'requests_per_topic': {},
    'errors': {},
    'total_requests': 0,
    'successful_requests': 0
}

def track_response_time(category, topic, model, response_time):
    """
    Track response time for analytics
    
    Args:
        category (str): The content category
        topic (str): The specific topic
        model (str): The AI model used
        response_time (float): Response time in seconds
    """
    # Store in memory
    ANALYTICS_STORE['response_times'].append({
        'timestamp': datetime.utcnow().isoformat(),
        'category': category,
        'topic': topic,
        'model': model,
        'response_time': response_time
    })
    
    # Track category popularity
    ANALYTICS_STORE['requests_per_category'][category] = ANALYTICS_STORE['requests_per_category'].get(category, 0) + 1
    
    # Track topic popularity
    topic_key = f"{category}:{topic}"
    ANALYTICS_STORE['requests_per_topic'][topic_key] = ANALYTICS_STORE['requests_per_topic'].get(topic_key, 0) + 1
    
    # Update total requests
    ANALYTICS_STORE['total_requests'] += 1
    ANALYTICS_STORE['successful_requests'] += 1
    
    logger.debug(f"Tracked response time: {response_time:.2f}s for {category}/{topic} using {model}")

def track_error(category, topic, error_type, error_message):
    """
    Track an error for analytics
    
    Args:
        category (str): The content category
        topic (str): The specific topic
        error_type (str): The type of error
        error_message (str): The error message
    """
    # Create error key
    error_key = f"{error_type}"
    
    # Store error count
    ANALYTICS_STORE['errors'][error_key] = ANALYTICS_STORE['errors'].get(error_key, 0) + 1
    
    # Update total requests
    ANALYTICS_STORE['total_requests'] += 1
    
    logger.debug(f"Tracked error: {error_type} for {category}/{topic}: {error_message}")

def get_analytics_summary():
    """
    Get a summary of analytics data
    
    Returns:
        dict: Summary of analytics data
    """
    # Calculate average response time
    avg_response_time = 0
    if ANALYTICS_STORE['response_times']:
        response_times = [entry['response_time'] for entry in ANALYTICS_STORE['response_times']]
        avg_response_time = sum(response_times) / len(response_times)
    
    # Calculate success rate
    success_rate = 0
    if ANALYTICS_STORE['total_requests'] > 0:
        success_rate = (ANALYTICS_STORE['successful_requests'] / ANALYTICS_STORE['total_requests']) * 100
    
    # Get top categories
    top_categories = sorted(
        ANALYTICS_STORE['requests_per_category'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    # Get top topics
    top_topics = sorted(
        ANALYTICS_STORE['requests_per_topic'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    # Get top errors
    top_errors = sorted(
        ANALYTICS_STORE['errors'].items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]
    
    return {
        'total_requests': ANALYTICS_STORE['total_requests'],
        'successful_requests': ANALYTICS_STORE['successful_requests'],
        'success_rate': success_rate,
        'avg_response_time': avg_response_time,
        'top_categories': top_categories,
        'top_topics': top_topics,
        'top_errors': top_errors,
        'timestamp': datetime.utcnow().isoformat()
    }

def get_database_analytics(db):
    """
    Get analytics from the database
    
    Args:
        db: SQLAlchemy database instance
    
    Returns:
        dict: Analytics data from the database
    """
    try:
        # Get total users
        total_users = User.query.count()
        
        # Get total conversations
        total_conversations = Conversation.query.count()
        
        # Get total messages
        total_messages = ChatMessage.query.count()
        
        # Get average messages per conversation
        avg_messages_per_conversation = 0
        if total_conversations > 0:
            avg_messages_per_conversation = total_messages / total_conversations
        
        # Get top categories from the database
        top_categories_db = db.session.query(
            ChatMessage.category, 
            func.count(ChatMessage.id).label('count')
        ).group_by(ChatMessage.category).order_by(desc('count')).limit(5).all()
        
        # Get top topics from the database
        top_topics_db = db.session.query(
            ChatMessage.topic,
            func.count(ChatMessage.id).label('count')
        ).group_by(ChatMessage.topic).order_by(desc('count')).limit(5).all()
        
        # Get messages in the last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        messages_last_24h = ChatMessage.query.filter(ChatMessage.created_at >= yesterday).count()
        
        return {
            'total_users': total_users,
            'total_conversations': total_conversations,
            'total_messages': total_messages,
            'avg_messages_per_conversation': avg_messages_per_conversation,
            'top_categories': [{'category': cat, 'count': count} for cat, count in top_categories_db],
            'top_topics': [{'topic': topic, 'count': count} for topic, count in top_topics_db],
            'messages_last_24h': messages_last_24h,
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting database analytics: {str(e)}")
        return {
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }