from flask import Flask, request, jsonify
from flask_session import Session
from flask_wtf import CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import logging
from datetime import timedelta
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize extensions
db = SQLAlchemy()
sess = Session()
csrf = CSRFProtect()
migrate = Migrate()

# Initialize SocketIO with CORS enabled and other configurations
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25
)

# Import WebSocket services
from app.services.rider_websocket import init_rider_websocket

def create_app(config_name='default'):
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Load environment variables from .env file in the root directory
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        logger.info(f"Loaded .env file from: {env_path}")
    else:
        logger.warning(f".env file not found at {env_path}")
    
    # Debug: Log important environment variables
    logger.info("=== Application Configuration ===")
    for key in [
        'FLASK_ENV', 'DEBUG', 'DATABASE_URL', 'MAIL_SERVER', 'MAIL_PORT', 
        'MAIL_USE_TLS', 'MAIL_USERNAME', 'REDIS_URL'
    ]:
        logger.info(f"{key}: {os.getenv(key, '[NOT SET]')}")
    logger.info("================================")
    
    # Basic configuration
    app.config.update(
        SECRET_KEY=os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production'),
        SESSION_TYPE='filesystem',
        UPLOAD_FOLDER='static/uploads',
        SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV') == 'production',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        JSON_SORT_KEYS=False,
        JSON_AS_ASCII=False,
        TEMPLATES_AUTO_RELOAD=True,
        SEND_FILE_MAX_AGE_DEFAULT=timedelta(days=30)
    )
    
    # Database configuration
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL', 'mysql+mysqlconnector://root:password@localhost/pawfect_findsdatabase'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            'pool_recycle': 280,
            'pool_pre_ping': True,
            'pool_size': 20,
            'max_overflow': 30,
            'pool_timeout': 30,
            'connect_args': {
                'connect_timeout': 10
            }
        },
        # Redis for message queue if available
        REDIS_URL=os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    )
    
    # Configure session to use Redis if available
    if 'redis' in os.getenv('CACHE_TYPE', '').lower():
        app.config.update(
            SESSION_TYPE='redis',
            SESSION_REDIS=redis.from_url(app.config['REDIS_URL'])
        )
    
    # Email configuration - load directly from environment
    email_from = os.getenv('EMAIL_FROM')
    sender_name = 'Pawfect Finds'
    
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() in ['true', '1']
    app.config['MAIL_USERNAME'] = email_from
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    
    # Set the default sender with both name and email
    app.config['MAIL_DEFAULT_SENDER'] = (sender_name, email_from)
    app.config['MAIL_SENDER_NAME'] = sender_name
    
    # Debug email config
    print("\n=== Email Configuration ===")
    print(f"MAIL_SERVER: {app.config['MAIL_SERVER']}")
    print(f"MAIL_PORT: {app.config['MAIL_PORT']}")
    print(f"MAIL_USE_TLS: {app.config['MAIL_USE_TLS']}")
    print(f"MAIL_USERNAME: {app.config['MAIL_USERNAME']}")
    print(f"MAIL_DEFAULT_SENDER: {app.config['MAIL_DEFAULT_SENDER']}")
    print("MAIL_PASSWORD:", "[SET]" if app.config['MAIL_PASSWORD'] else "[NOT SET]")
    print("=========================\n")
    
    # Initialize extensions with app
    db.init_app(app)
    sess.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    
    # Initialize WebSocket with the app
    socketio.init_app(
        app,
        message_queue=app.config.get('REDIS_URL') if 'redis' in os.getenv('CACHE_TYPE', '').lower() else None,
        cors_allowed_origins="*"
    )
    
    # Initialize rider WebSocket handlers
    init_rider_websocket(socketio)
    
    # Register error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({"error": "Not found"}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"Internal Server Error: {str(error)}")
        return jsonify({"error": "Internal server error"}), 500
    
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        logger.warning(f"CSRF Error: {str(error)}")
        return jsonify({"error": "Invalid CSRF token"}), 400
    
    # Register before/after request handlers
    @app.before_request
    def before_request():
        # Ensure we have a valid session
        if 'user_id' not in session and request.endpoint not in ['static', 'public.index', 'auth.login', 'auth.register']:
            return redirect(url_for('auth.login'))
    
    @app.after_request
    def add_security_headers(response):
        # Add security headers to all responses
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if 'Content-Security-Policy' not in response.headers:
            response.headers['Content-Security-Policy'] = "default-src 'self'"
        return response
    
    # Log application startup
    @app.before_first_request
    def startup():
        logger.info("=== Application Startup ===")
        logger.info(f"Environment: {app.config.get('ENV', 'production')}")
        logger.info(f"Debug mode: {app.debug}")
        logger.info(f"Database: {app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1]}")
        logger.info("==========================")
    
    # Register blueprints
    from app.controllers import (
        auth_controller, admin_controller, seller_controller, 
        user_controller, public_controller, cart_controller,
        order_controller, search_controller, review_controller,
        rider_controller
    )
    
    app.register_blueprint(auth_controller.auth_bp)
    app.register_blueprint(admin_controller.admin_bp, url_prefix='/admin')
    app.register_blueprint(seller_controller.seller_bp, url_prefix='/seller')
    app.register_blueprint(user_controller.user_bp, url_prefix='/user')
    app.register_blueprint(public_controller.public_bp)
    app.register_blueprint(cart_controller.cart_bp, url_prefix='/cart')
    app.register_blueprint(order_controller.order_bp, url_prefix='/order')
    app.register_blueprint(search_controller.search_bp, url_prefix='/search')
    app.register_blueprint(review_controller.review_bp, url_prefix='/review')
    app.register_blueprint(rider_controller.rider_bp, url_prefix='/rider')
    
    # Health check endpoint
    @app.route('/health')
    def health_check():
        return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})
    
    # Import models to ensure they are registered with SQLAlchemy
    from app.models import models
    
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
    
    # Create upload directories
    upload_folders = [
        app.config['UPLOAD_FOLDER'],
        os.path.join(app.config['UPLOAD_FOLDER'], 'products'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'documents')
    ]
    
    for folder in upload_folders:
        os.makedirs(folder, exist_ok=True)
    
    # Register blueprints (only main for now)
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)
    
    from app.controllers import auth_bp, user_bp, admin_bp, seller_bp, public_bp, rider_bp
    from app.services.database import Database
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(seller_bp, url_prefix='/seller')
    app.register_blueprint(rider_bp, url_prefix='/rider')
    app.register_blueprint(public_bp)
    
    @app.context_processor
    def inject_seller_data():
        if 'user_id' in session and session.get('role') == 'seller':
            try:
                db = Database()
                # Get pending orders count
                pending_count = db.execute_query(
                    """
                    SELECT COUNT(*) as count 
                    FROM orders 
                    WHERE seller_id = %s AND status = 'pending'
                    """,
                    (session['user_id'],),
                    fetch=True,
                    fetchone=True
                )
                # Get total unread messages count (if you have a messaging system)
                unread_messages = 0  # Add your message count logic here
                
                return {
                    'pending_orders': pending_count['count'] if pending_count else 0,
                    'unread_messages': unread_messages
                }
            except Exception as e:
                current_app.logger.error(f"Error in seller context processor: {str(e)}")
                return {
                    'pending_orders': 0,
                    'unread_messages': 0
                }
        return {
            'pending_orders': 0,
            'unread_messages': 0
        }
    
    from app.models import user
    
    return app
