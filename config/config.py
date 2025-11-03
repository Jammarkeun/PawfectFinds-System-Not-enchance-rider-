import os
from datetime import timedelta

class Config:
    # Basic Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'pawfect-finds-secret-key-2023'
    DEBUG = True  # Used by legacy app.py
    
    # Database configuration (used by raw mysql connector)
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or ''  # Empty password
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'pawfect_findsdatabase'
    
    # Mapping for app.services.database.Database
    DATABASE = {
        'host': MYSQL_HOST,
        'user': MYSQL_USER,
        'password': MYSQL_PASSWORD,
        'database': MYSQL_DB
    }
    
    # SQLAlchemy configuration (unused in legacy path, kept for compatibility)
    SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DB}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # Set to True for SQL debugging
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_TYPE = 'filesystem'
    
    # File upload configuration
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # Pagination
    POSTS_PER_PAGE = 12
    ORDERS_PER_PAGE = 10
    PRODUCTS_PER_PAGE = 12  # Used by public_controller
    
    # Security
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    
    # Email Configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    EMAIL_FROM = os.environ.get('EMAIL_FROM', MAIL_USERNAME)
    EMAIL_FROM_NAME = os.environ.get('EMAIL_FROM_NAME', 'Pawfect Finds')
    
    # Legacy support
    MAIL_SENDER_NAME = EMAIL_FROM_NAME
    MAIL_SENDER_EMAIL = EMAIL_FROM

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_ECHO = True

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_ECHO = False

class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
