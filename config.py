import os
from datetime import timedelta

class Config:
    """Base configuration class."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///restaurant.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # File upload settings
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MENU_IMAGE_FOLDER = 'static/uploads/menu_images'
    PROFILE_IMAGE_FOLDER = 'static/uploads/profile_images'
    RECEIPT_FOLDER = 'static/uploads/receipts'
    
    # Loyalty program settings
    POINTS_PER_50_EGP = 100
    POINT_EXPIRY_MONTHS = 6
    
    # Pagination
    ORDERS_PER_PAGE = 20
    MENU_ITEMS_PER_PAGE = 12
    
    # Email settings (for future use)
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    
    # Redis settings for caching and real-time features
    REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'

    # WhatsApp Bot Integration
    WHATSAPP_BOT_NUMBER = os.environ.get('WHATSAPP_BOT_NUMBER') or '201234567890'
    WHATSAPP_API_URL = os.environ.get('WHATSAPP_API_URL') or 'http://localhost:3000'

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or 'sqlite:///restaurant_dev.db'
    WTF_CSRF_ENABLED = False  # Disable CSRF for development

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///restaurant.db'
    SESSION_COOKIE_SECURE = True

config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
