"""User authentication and authorization models"""
from datetime import datetime
from typing import Optional, List
from flask_login import UserMixin
from sqlalchemy import func
from app import db
from app.auth.security import verify_password, hash_password


class Role(db.Model):
    """User roles for RBAC"""
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    permissions = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Predefined roles
    ADMIN = 'admin'
    DOCTOR = 'doctor'
    NURSE = 'nurse'
    RECEPTIONIST = 'receptionist'
    AUDITOR = 'auditor'
    
    @classmethod
    def get_default_permissions(cls, role_name: str) -> List[str]:
        """Get default permissions for a role"""
        permissions_map = {
            cls.ADMIN: ['*'],  # All permissions
            cls.DOCTOR: [
                'patient.read', 'patient.write', 'patient.create',
                'document.read', 'document.write', 'document.upload',
                'audit.read'
            ],
            cls.NURSE: [
                'patient.read', 'patient.write',
                'document.read', 'document.upload'
            ],
            cls.RECEPTIONIST: [
                'patient.read', 'patient.create',
                'document.upload'
            ],
            cls.AUDITOR: [
                'patient.read', 'document.read', 'audit.read',
                'system.monitor'
            ]
        }
        return permissions_map.get(role_name, [])


class User(UserMixin, db.Model):
    """User model with security features"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Security fields
    file_key = db.Column(db.LargeBinary(32))  # Per-user file encryption key
    totp_secret = db.Column(db.String(32))  # 2FA secret
    require_2fa = db.Column(db.Boolean, default=False)
    
    # Account status
    is_active = db.Column(db.Boolean, default=True)
    is_locked = db.Column(db.Boolean, default=False)
    failed_login_attempts = db.Column(db.Integer, default=0)
    last_failed_login = db.Column(db.DateTime)
    
    # Relationships
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    role = db.relationship('Role', backref='users')
    
    # Audit fields
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    last_activity = db.Column(db.DateTime)
    
    # Session management
    sessions = db.relationship('UserSession', backref='user', cascade='all, delete-orphan')
    
    def set_password(self, password: str):
        """Hash and set user password"""
        self.password_hash = hash_password(password)
    
    def check_password(self, password: str) -> bool:
        """Verify password against hash"""
        return verify_password(password, self.password_hash)
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission"""
        if not self.role:
            return False
        if '*' in self.role.permissions:
            return True
        return permission in self.role.permissions
    
    def increment_failed_login(self):
        """Track failed login attempts"""
        self.failed_login_attempts += 1
        self.last_failed_login = datetime.utcnow()
        if self.failed_login_attempts >= 5:
            self.is_locked = True
        db.session.commit()
    
    def reset_failed_login(self):
        """Reset failed login counter on successful login"""
        self.failed_login_attempts = 0
        self.last_failed_login = None
        self.last_login = datetime.utcnow()
        db.session.commit()


class UserSession(db.Model):
    """Track active user sessions for security"""
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.String(64), primary_key=True)  # Session ID
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(45))  # IPv6 support
    user_agent = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    
    @classmethod
    def cleanup_expired(cls):
        """Remove expired sessions"""
        cls.query.filter(cls.expires_at < datetime.utcnow()).delete()
        db.session.commit()