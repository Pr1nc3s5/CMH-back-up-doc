"""Security utilities for authentication and encryption"""
import os
import secrets
from typing import Tuple, Optional
from datetime import datetime, timedelta
import argon2
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import pyotp
from flask import current_app
from config.constraints import PI_ZERO_LIMITS


# Argon2 parameters optimized for Pi Zero
ARGON2_TIME_COST = 4  # iterations
ARGON2_MEMORY_COST = 1024  # 1MB - safe for 512MB RAM
ARGON2_PARALLELISM = 1  # Single core
ARGON2_HASH_LEN = 32


def hash_password(password: str) -> str:
    """Hash password using Argon2 with Pi Zero optimized parameters"""
    ph = argon2.PasswordHasher(
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN
    )
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against Argon2 hash"""
    ph = argon2.PasswordHasher()
    try:
        ph.verify(password_hash, password)
        return True
    except argon2.exceptions.VerifyMismatchError:
        return False


def generate_file_key() -> bytes:
    """Generate a random 256-bit key for file encryption"""
    return secrets.token_bytes(32)


def derive_key_from_master(master_key: bytes, salt: bytes, info: bytes = b'file-encryption') -> bytes:
    """Derive a file encryption key from master key"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000  # NIST recommendation
    )
    return kdf.derive(master_key + info)


class FileEncryption:
    """AES-GCM file encryption optimized for low memory"""
    
    def __init__(self, key: bytes):
        self.aesgcm = AESGCM(key)
    
    def encrypt_file(self, file_path: str, output_path: str, 
                     chunk_size: int = PI_ZERO_LIMITS.ENCRYPTION_BUFFER * 1024) -> Tuple[str, bytes]:
        """Encrypt file in chunks to conserve memory"""
        nonce = os.urandom(12)  # 96-bit nonce for GCM
        
        with open(file_path, 'rb') as infile, open(output_path, 'wb') as outfile:
            # Write nonce at beginning
            outfile.write(nonce)
            
            while True:
                chunk = infile.read(chunk_size)
                if not chunk:
                    break
                
                # Encrypt chunk
                ciphertext = self.aesgcm.encrypt(nonce, chunk, None)
                outfile.write(ciphertext)
        
        return output_path, nonce
    
    def decrypt_file(self, file_path: str, output_path: str,
                     chunk_size: int = PI_ZERO_LIMITS.ENCRYPTION_BUFFER * 1024) -> str:
        """Decrypt file in chunks"""
        with open(file_path, 'rb') as infile:
            # Read nonce
            nonce = infile.read(12)
            
            with open(output_path, 'wb') as outfile:
                while True:
                    # Read chunk (ciphertext is 16 bytes larger due to tag)
                    chunk = infile.read(chunk_size + 16)
                    if not chunk:
                        break
                    
                    # Decrypt chunk
                    plaintext = self.aesgcm.decrypt(nonce, chunk, None)
                    outfile.write(plaintext)
        
        return output_path


class SessionManager:
    """Secure session management with timeout"""
    
    @staticmethod
    def create_session(user_id: int, ip_address: str, user_agent: str) -> str:
        """Create new session with secure ID"""
        from app.auth.models import UserSession
        
        session_id = secrets.token_urlsafe(48)
        expires_at = datetime.utcnow() + timedelta(
            seconds=current_app.config['PERMANENT_SESSION_LIFETIME'].total_seconds()
        )
        
        session = UserSession(
            id=session_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        
        from app import db
        db.session.add(session)
        db.session.commit()
        
        return session_id
    
    @staticmethod
    def validate_session(session_id: str, ip_address: str) -> Optional[int]:
        """Validate session and return user_id if valid"""
        from app.auth.models import UserSession
        
        session = UserSession.query.get(session_id)
        if not session:
            return None
        
        # Check expiration
        if session.expires_at < datetime.utcnow():
            from app import db
            db.session.delete(session)
            db.session.commit()
            return None
        
        # Validate IP (optional strict mode)
        if session.ip_address != ip_address:
            # Log potential session hijacking
            from app.audit.logger import log_security_event
            log_security_event('SESSION_IP_MISMATCH', ip_address, {
                'session_id': session_id,
                'expected_ip': session.ip_address
            })
        
        # Update last activity
        session.last_activity = datetime.utcnow()
        from app import db
        db.session.commit()
        
        return session.user_id


def generate_totp_secret() -> str:
    """Generate TOTP secret for 2FA"""
    return pyotp.random_base32()


def verify_totp(secret: str, token: str) -> bool:
    """Verify TOTP token"""
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=1)  # Allow 30 second window


def get_totp_uri(secret: str, email: str) -> str:
    """Get TOTP provisioning URI for QR code"""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(
        name=email,
        issuer_name='PSYWARD DMS'
    )
