"""Production configuration optimized for Raspberry Pi Zero"""
import os
from datetime import timedelta


class ProductionConfig:
    """Production configuration with Pi Zero optimizations"""
    
    # Basic Flask config
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(32).hex())
    DEBUG = False
    TESTING = False
    
    # Database - SQLite with encryption
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.environ.get('DB_PATH', '/mnt/encrypted_data/psyward.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 2,  # Limited connections for Pi Zero
        'pool_recycle': 300,
        'pool_pre_ping': True
    }
    
    # Security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)  # HIPAA compliance
    WTF_CSRF_TIME_LIMIT = None
    
    # File upload limits (Pi Zero memory constraint)
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB max file size
    UPLOAD_CHUNK_SIZE = 512 * 1024  # 512KB chunks
    
    # OCR settings
    TESSERACT_CMD = '/usr/bin/tesseract'
    TESSERACT_CONFIG = '--psm 11 -l medical --oem 1'
    OCR_THREAD_POOL_SIZE = 1  # Single thread for Pi Zero
    
    # Storage paths
    UPLOAD_FOLDER = '/mnt/encrypted_data/uploads'
    PATIENT_DATA_FOLDER = '/mnt/encrypted_data/patients'
    TEMP_FOLDER = '/tmp/psyward'
    BACKUP_FOLDER = '/mnt/backup'
    
    # Performance optimizations
    SEND_FILE_MAX_AGE_DEFAULT = 0  # No caching for medical records
    JSON_SORT_KEYS = False
    JSONIFY_PRETTYPRINT_REGULAR = False
    
    # Rate limiting (prevent DoS on limited hardware)
    RATELIMIT_STORAGE_URL = "memory://"
    RATELIMIT_DEFAULT = "100 per hour"
    RATELIMIT_HEADERS_ENABLED = True
    
    # Audit log
    AUDIT_LOG_PATH = '/var/log/psyward/audit.log'
    AUDIT_LOG_RETENTION_DAYS = 2555  # 7 years HIPAA requirement
    
    # Encryption
    ENCRYPTION_ALGORITHM = 'AES-256-GCM'
    KEY_DERIVATION_ITERATIONS = 100000
    MASTER_KEY_PATH = '/etc/psyward/keys/master.key'
    
    # Resource limits for Pi Zero
    MAX_MEMORY_PERCENT = 80
    CPU_AFFINITY = [0]  # Single core
    NICE_LEVEL = 10