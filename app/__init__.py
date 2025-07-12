from flask import Flask
from config import config
from app.extensions import init_extensions

def create_app(config_name='default'):
    """Application factory pattern."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    init_extensions(app)
    
    # Import models to ensure they are registered with SQLAlchemy
    from app import models
    
    # Import WebSocket handlers
    from app import websocket_handlers

    # Initialize security middleware
    from app.security.session_security import init_security_middleware
    init_security_middleware(app)

    # Register blueprints
    from app.modules.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')
    
    from app.modules.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    from app.modules.waiter import bp as waiter_bp
    app.register_blueprint(waiter_bp, url_prefix='/waiter')
    
    from app.modules.customer import bp as customer_bp
    app.register_blueprint(customer_bp, url_prefix='/customer')
    
    from app.modules.menu import bp as menu_bp
    app.register_blueprint(menu_bp, url_prefix='/menu')
    
    from app.modules.order import bp as order_bp
    app.register_blueprint(order_bp, url_prefix='/order')
    
    from app.modules.service import bp as service_bp
    app.register_blueprint(service_bp, url_prefix='/service')
    
    from app.modules.loyalty import bp as loyalty_bp
    app.register_blueprint(loyalty_bp, url_prefix='/loyalty')
    
    from app.modules.payment import bp as payment_bp
    app.register_blueprint(payment_bp, url_prefix='/payment')
    
    from app.modules.qr import bp as qr_bp
    app.register_blueprint(qr_bp, url_prefix='/qr')
    
    from app.api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Register order API blueprint directly with the Flask app
    from app.modules.order.api.order_api import bp as order_api_bp
    app.register_blueprint(order_api_bp)
    
    # Register loyalty API blueprint
    from app.modules.loyalty.api import bp as loyalty_api_bp
    app.register_blueprint(loyalty_api_bp)
    
    # Register payment API blueprint
    from app.modules.payment.api.payment_api import bp as payment_api_bp
    app.register_blueprint(payment_api_bp)
    
    # Register main routes
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    # Register context processors
    @app.context_processor
    def inject_system_settings():
        """Inject system settings into template context"""
        from app.models import SystemSettings

        def get_system_setting(key, default=None):
            return SystemSettings.get_setting(key, default)

        return dict(get_system_setting=get_system_setting)

    return app
