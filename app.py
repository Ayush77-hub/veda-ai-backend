import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_cors import CORS


# Define base class for SQLAlchemy models
from extensions import db, login_manager

def create_app():
    # Create Flask app
    app = Flask(__name__, static_folder='../frontend/dist', static_url_path='/')
    
    # Configure app
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "veda-ai-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL") or "sqlite:///veda_ai.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    # Enable CORS
    CORS(app)
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    with app.app_context():
        # Import models to ensure they are registered with SQLAlchemy
        from models import User, Conversation, ChatMessage
        
        # Create database tables
        db.create_all()
        
        # user_loader callback
        @login_manager.user_loader
        def load_user(user_id):
            return User.query.get(int(user_id))
            
        # Import and register routes
        print("Importing routes...")
        from routes import register_routes
        register_routes(app)
        
    return app

# Create the app instance for deployment/running
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
