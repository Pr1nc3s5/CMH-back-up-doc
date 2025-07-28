"""HIPAA-compliant audit logging with tamper protection"""
import os
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
import blake2b
from flask import current_app, request
from app import db, logger


class TamperProofLog:
    """Append-only audit log with cryptographic integrity"""
    
    def __init__(self, log_path: str):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Initialize log file if not exists"""
        if not self.log_path.exists():
            # Write genesis entry
            genesis = {
                'entry_id': 0,
                'timestamp': datetime.utcnow().isoformat(),
                'event': 'LOG_INITIALIZED',
                'data': {'version': '1.0'},
                'previous_hash': '0' * 64
            }
            genesis['hash'] = self._calculate_hash(genesis)
            
            with open(self.log_path, 'w') as f:
                json.dump(genesis, f)
                f.write('\n')
            
            # Set file as append-only (on Linux)
            try:
                os.system(f'sudo chattr +a {self.log_path}')
            except:
                pass
    
    def append(self, event: str, user_id: Optional[int], data: Dict[str, Any]) -> str:
        """Append new entry to audit log"""
        # Get last entry hash
        previous_hash = self._get_last_hash()
        
        # Create new entry
        entry = {
            'entry_id': self._get_next_id(),
            'timestamp': datetime.utcnow().isoformat(),
            'event': event,
            'user_id': user_id,
            'ip_address': request.remote_addr if request else None,
            'user_agent': request.user_agent.string if request else None,
            'data': data,
            'previous_hash': previous_hash
        }
        
        # Calculate hash including previous hash
        entry['hash'] = self._calculate_hash(entry)
        
        # Append to log
        with open(self.log_path, 'a') as f:
            json.dump(entry, f, separators=(',', ':'))
            f.write('\n')
        
        return entry['hash']
    
    def _calculate_hash(self, entry: Dict[str, Any]) -> str:
        """Calculate BLAKE2b hash of entry"""
        # Create consistent string representation
        content = json.dumps({
            'entry_id': entry['entry_id'],
            'timestamp': entry['timestamp'],
            'event': entry['event'],
            'user_id': entry.get('user_id'),
            'data': entry.get('data', {}),
            'previous_hash': entry['previous_hash']
        }, sort_keys=True, separators=(',', ':'))
        
        # Calculate hash
        h = hashlib.blake2b(digest_size=32)
        h.update(content.encode('utf-8'))
        return h.hexdigest()
    
    def _get_last_hash(self) -> str:
        """Get hash of last log entry"""
        try:
            with open(self.log_path, 'rb') as f:
                # Seek to end and read backwards to find last line
                f.seek(0, 2)  # End of file
                file_size = f.tell()
                
                if file_size == 0:
                    return '0' * 64
                
                # Read last ~1KB to find last line
                read_size = min(file_size, 1024)
                f.seek(file_size - read_size)
                lines = f.read().decode('utf-8').strip().split('\n')
                
                if lines:
                    last_entry = json.loads(lines[-1])
                    return last_entry['hash']
        except Exception as e:
            logger.error(f"Failed to get last hash: {str(e)}")
        
        return '0' * 64
    
    def _get_next_id(self) -> int:
        """Get next entry ID"""
        try:
            with open(self.log_path, 'rb') as f:
                f.seek(0, 2)
                file_size = f.tell()
                
                if file_size == 0:
                    return 1
                
                # Read last line
                read_size = min(file_size, 1024)
                f.seek(file_size - read_size)
                lines = f.read().decode('utf-8').strip().split('\n')
                
                if lines:
                    last_entry = json.loads(lines[-1])
                    return last_entry['entry_id'] + 1
        except:
            pass
        
        return 1
    
    def verify_integrity(self, start_id: int = 0, end_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Verify log integrity by checking hash chain"""
        issues = []
        previous_hash = '0' * 64
        
        with open(self.log_path, 'r') as f:
            for line_num, line in enumerate(f):
                if not line.strip():
                    continue
                
                try:
                    entry = json.loads(line)
                    
                    # Check if within range
                    if entry['entry_id'] < start_id:
                        continue
                    if end_id and entry['entry_id'] > end_id:
                        break
                    
                    # Verify previous hash matches
                    if entry['previous_hash'] != previous_hash:
                        issues.append({
                            'entry_id': entry['entry_id'],
                            'issue': 'broken_chain',
                            'expected_previous': previous_hash,
                            'actual_previous': entry['previous_hash']
                        })
                    
                    # Verify entry hash
                    calculated_hash = self._calculate_hash(entry)
                    if calculated_hash != entry['hash']:
                        issues.append({
                            'entry_id': entry['entry_id'],
                            'issue': 'invalid_hash',
                            'expected': calculated_hash,
                            'actual': entry['hash']
                        })
                    
                    previous_hash = entry['hash']
                    
                except json.JSONDecodeError:
                    issues.append({
                        'line': line_num + 1,
                        'issue': 'invalid_json'
                    })
        
        return issues


# Global audit logger instance
_audit_logger = None


def get_audit_logger() -> TamperProofLog:
    """Get or create audit logger instance"""
    global _audit_logger
    if _audit_logger is None:
        log_path = current_app.config.get('AUDIT_LOG_PATH', '/var/log/psyward/audit.log')
        _audit_logger = TamperProofLog(log_path)
    return _audit_logger


# Convenience functions for common events
def log_login_attempt(user_id: Optional[int], success: bool, ip_address: str, 
                     failure_reason: Optional[str] = None):
    """Log authentication attempt"""
    logger = get_audit_logger()
    logger.append('LOGIN_ATTEMPT', user_id, {
        'success': success,
        'ip_address': ip_address,
        'failure_reason': failure_reason
    })


def log_patient_access(user_id: int, patient_id: int, access_type: str, 
                      fields_accessed: List[str] = None):
    """Log patient record access"""
    logger = get_audit_logger()
    logger.append('PATIENT_ACCESS', user_id, {
        'patient_id': patient_id,
        'access_type': access_type,
        'fields_accessed': fields_accessed or []
    })


def log_document_event(event: str, user_id: int, data: Dict[str, Any]):
    """Log document-related events"""
    logger = get_audit_logger()
    logger.append(f'DOCUMENT_{event}', user_id, data)


def log_security_event(event: str, ip_address: str, data: Dict[str, Any] = None):
    """Log security-related events"""
    logger = get_audit_logger()
    logger.append(f'SECURITY_{event}', None, {
        'ip_address': ip_address,
        'data': data or {}
    })


def log_search_event(search_type: str, user_id: int, data: Dict[str, Any]):
    """Log search queries for monitoring"""
    logger = get_audit_logger()
    logger.append(f'{search_type}_SEARCH', user_id, data)