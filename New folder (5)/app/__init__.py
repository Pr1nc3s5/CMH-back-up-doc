"""
PSYWARD Document Management System
HIPAA-compliant medical records system optimized for Raspberry Pi Zero
"""
import os
import logging
from typing import Optional
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from cryptography.fernet import Fernet
import redis

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/psyward/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def create_app(config_name: str = 'production') -> Flask:
    """Create and configure the Flask application"""
    app = Flask(__name__)
    
    # Load configuration
    if config_name == 'production':
        from config.production import ProductionConfig
        app.config.from_object(ProductionConfig)
    else:
        from config.default import DevelopmentConfig
        app.config.from_object(DevelopmentConfig)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
    
    # Security headers
    if config_name == 'production':
        Talisman(app, force_https=True, strict_transport_security=True)
    
    # Configure login manager
    login_manager.login_view = 'auth.login'
    login_manager.session_protection = 'strong'
    
    # Register blueprints
    from app.auth import auth_bp
    from app.documents import documents_bp
    from app.patient import patient_bp
    from app.admin import admin_bp
    from app.audit import audit_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(documents_bp, url_prefix='/documents')
    app.register_blueprint(patient_bp, url_prefix='/patients')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(audit_bp, url_prefix='/audit')
    
    # Create database tables
    with app.app_context():
        db.create_all()
        _initialize_encryption_keys()
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register template filters
    register_template_filters(app)
    
    return app


def _initialize_encryption_keys():
    """Initialize master encryption key if not exists"""
    key_path = os.environ.get('MASTER_KEY_PATH', '/etc/psyward/keys/master.key')
    if not os.path.exists(key_path):
        os.makedirs(os.path.dirname(key_path), exist_ok=True)
        key = Fernet.generate_key()
        with open(key_path, 'wb') as f:
            f.write(key)
        os.chmod(key_path, 0o600)
        logger.info("Generated new master encryption key")


def register_error_handlers(app: Flask):
    """Register custom error handlers"""
    
    @app.errorhandler(403)
    def forbidden(e):
        from app.audit.logger import log_security_event
        log_security_event('ACCESS_DENIED', request.remote_addr)
        return {'error': 'Access denied'}, 403
    
    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        logger.error(f"Internal error: {str(e)}")
        return {'error': 'Internal server error'}, 500


def register_template_filters(app: Flask):
    """Register custom Jinja2 filters"""
    
    @app.template_filter('redact_phi')
    def redact_phi(text: str) -> str:
        """Redact PHI from text for display"""
        import re
        # SSN pattern
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', 'XXX-XX-XXXX', text)
        # MRN pattern (assumed 6-10 digits)
        text = re.sub(r'\b\d{6,10}\b', 'XXXXXXXXXX', text)
        return text