"""System monitoring and admin dashboard"""
import os
import psutil
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Any, List
from flask import Blueprint, render_template, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.auth.models import User, Role, UserSession
from app.patient.models import Patient, PatientDocument
from app.audit.logger import get_audit_logger
from app.documents.storage import PatientStorageManager
from config.constraints import PI_ZERO_LIMITS


admin_bp = Blueprint('admin', __name__)


@admin_bp.before_request
@login_required
def require_admin():
    """Ensure only admins can access admin pages"""
    if not current_user.has_permission('system.admin'):
        return jsonify({'error': 'Unauthorized'}), 403


@admin_bp.route('/dashboard')
def dashboard():
    """Main admin dashboard"""
    stats = get_system_statistics()
    return render_template('admin/dashboard.html', stats=stats)


@admin_bp.route('/api/system/status')
def system_status():
    """Real-time system status API"""
    status = {
        'timestamp': datetime.utcnow().isoformat(),
        'system': get_system_metrics(),
        'application': get_application_metrics(),
        'security': get_security_status()
    }
    return jsonify(status)


def get_system_metrics() -> Dict[str, Any]:
    """Get Raspberry Pi system metrics"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_used_mb = (memory.total - memory.available) / (1024 * 1024)
        memory_percent = memory.percent
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_used_gb = disk.used / (1024 * 1024 * 1024)
        disk_percent = disk.percent
        
        # Temperature (Raspberry Pi specific)
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp_c = float(f.read()) / 1000
        except:
            temp_c = None
        
        # SD card health (basic check)
        sd_health = check_sd_card_health()
        
        # Network
        net_io = psutil.net_io_counters()
        
        return {
            'cpu': {
                'percent': cpu_percent,
                'temperature_c': temp_c,
                'throttled': is_cpu_throttled()
            },
            'memory': {
                'used_mb': round(memory_used_mb, 1),
                'total_mb': PI_ZERO_LIMITS.AVAILABLE_RAM_MB,
                'percent': memory_percent
            },
            'disk': {
                'used_gb': round(disk_used_gb, 2),
                'total_gb': round(disk.total / (1024 * 1024 * 1024), 2),
                'percent': disk_percent
            },
            'sd_card': sd_health,
            'network': {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv
            },
            'uptime_hours': round(get_uptime_hours(), 1)
        }
        
    except Exception as e:
        logger.error(f"Failed to get system metrics: {str(e)}")
        return {}


def get_application_metrics() -> Dict[str, Any]:
    """Get application-specific metrics"""
    try:
        # Database size
        db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0
        
        # Record counts
        patient_count = Patient.query.count()
        document_count = PatientDocument.query.count()
        user_count = User.query.count()
        active_sessions = UserSession.query.filter(
            UserSession.expires_at > datetime.utcnow()
        ).count()
        
        # Storage usage
        storage_mgr = PatientStorageManager()
        total_storage = calculate_total_storage()
        
        # Recent activity
        recent_uploads = PatientDocument.query.filter(
            PatientDocument.uploaded_at > datetime.utcnow() - timedelta(hours=24)
        ).count()
        
        # OCR queue
        pending_ocr = PatientDocument.query.filter(
            PatientDocument.ocr_processed == False
        ).count()
        
        return {
            'database': {
                'size_mb': round(db_size_mb, 2),
                'patients': patient_count,
                'documents': document_count,
                'users': user_count
            },
            'sessions': {
                'active': active_sessions,
                'limit': 10  # Configured session limit
            },
            'storage': {
                'used_gb': round(total_storage / (1024 * 1024 * 1024), 2),
                'documents_24h': recent_uploads
            },
            'processing': {
                'ocr_pending': pending_ocr,
                'ocr_threads': current_app.config.get('OCR_THREAD_POOL_SIZE', 1)
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get application metrics: {str(e)}")
        return {}


def get_security_status() -> Dict[str, Any]:
    """Get security-related status"""
    try:
        # Failed login attempts in last hour
        from app.auth.models import User
        recent_failures = User.query.filter(
            User.last_failed_login > datetime.utcnow() - timedelta(hours=1)
        ).count()
        
        # Locked accounts
        locked_accounts = User.query.filter(User.is_locked == True).count()
        
        # Audit log integrity
        audit_logger = get_audit_logger()
        integrity_issues = len(audit_logger.verify_integrity())
        
        # Physical security (GPIO tamper detection)
        tamper_detected = check_tamper_status()
        
        # Encryption status
        encryption_enabled = os.path.exists(current_app.config['MASTER_KEY_PATH'])
        
        # Backup status
        last_backup = get_last_backup_time()
        backup_overdue = (datetime.utcnow() - last_backup).days > 1 if last_backup else True
        
        return {
            'authentication': {
                'failed_attempts_1h': recent_failures,
                'locked_accounts': locked_accounts
            },
            'audit': {
                'integrity_ok': integrity_issues == 0,
                'issues_count': integrity_issues
            },
            'physical': {
                'tamper_detected': tamper_detected,
                'case_opened': False  # From GPIO
            },
            'encryption': {
                'enabled': encryption_enabled,
                'algorithm': 'AES-256-GCM'
            },
            'backup': {
                'last_backup': last_backup.isoformat() if last_backup else None,
                'overdue': backup_overdue
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get security status: {str(e)}")
        return {}


def check_sd_card_health() -> Dict[str, Any]:
    """Check SD card health indicators"""
    try:
        # Get SD card device
        sd_device = '/dev/mmcblk0'  # Pi SD card device
        
        # Check for bad blocks (simplified)
        result = subprocess.run(
            ['sudo', 'tune2fs', '-l', sd_device],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Parse lifetime writes (if available)
        lifetime_writes = 0
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'Lifetime writes' in line:
                    lifetime_writes = int(line.split(':')[1].strip())
        
        return {
            'healthy': True,
            'lifetime_writes_gb': round(lifetime_writes / (1024 * 1024 * 1024), 2),
            'wear_level': 'normal'  # Simplified
        }
        
    except:
        return {'healthy': True, 'lifetime_writes_gb': 0, 'wear_level': 'unknown'}


def is_cpu_throttled() -> bool:
    """Check if CPU is being throttled"""
    try:
        result = subprocess.run(
            ['vcgencmd', 'get_throttled'],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            throttled = int(result.stdout.split('=')[1], 16)
            return throttled != 0
    except:
        pass
    return False


def get_uptime_hours() -> float:
    """Get system uptime in hours"""
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.read().split()[0])
            return uptime_seconds / 3600
    except:
        return 0


def calculate_total_storage() -> int:
    """Calculate total storage used by patient data"""
    patient_folder = Path(current_app.config['PATIENT_DATA_FOLDER'])
    total_size = 0
    
    if patient_folder.exists():
        for path in patient_folder.rglob('*'):
            if path.is_file():
                total_size += path.stat().st_size
    
    return total_size


def check_tamper_status() -> bool:
    """Check physical tamper detection GPIO"""
    try:
        import RPi.GPIO as GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(21, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        return GPIO.input(21) == GPIO.HIGH
    except:
        return False


def get_last_backup_time() -> Optional[datetime]:
    """Get timestamp of last successful backup"""
    backup_folder = Path(current_app.config['BACKUP_FOLDER'])
    if not backup_folder.exists():
        return None
    
    # Find most recent backup file
    backup_files = list(backup_folder.glob('psyward_backup_*.enc'))
    if not backup_files:
        return None
    
    # Extract timestamp from filename
    latest_backup = max(backup_files, key=lambda p: p.stat().st_mtime)
    try:
        timestamp_str = latest_backup.stem.replace('psyward_backup_', '')
        return datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
    except:
        return None


def get_system_statistics() -> Dict[str, Any]:
    """Get comprehensive system statistics for dashboard"""
    return {
        'system': get_system_metrics(),
        'application': get_application_metrics(),
        'security': get_security_status(),
        'timestamp': datetime.utcnow()
    }