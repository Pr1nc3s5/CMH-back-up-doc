"""Document storage management with patient folder structure"""
import os
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from flask import current_app
from app import db, logger
from app.patient.models import Patient, PatientDocument


class PatientStorageManager:
    """Manage patient document storage with HIPAA compliance"""
    
    def __init__(self):
        self.base_path = Path(current_app.config['PATIENT_DATA_FOLDER'])
        self.backup_path = Path(current_app.config['BACKUP_FOLDER'])
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure storage directories exist with proper permissions"""
        for path in [self.base_path, self.backup_path]:
            path.mkdir(parents=True, exist_ok=True)
            # Set restrictive permissions (owner only)
            os.chmod(path, 0o700)
    
    def get_patient_folder(self, patient_id: int) -> Path:
        """Get or create patient folder"""
        folder = self.base_path / str(patient_id)
        folder.mkdir(exist_ok=True)
        return folder
    
    def calculate_patient_storage(self, patient_id: int) -> Dict[str, Any]:
        """Calculate storage usage for a patient"""
        folder = self.get_patient_folder(patient_id)
        
        total_size = 0
        file_count = 0
        
        for file_path in folder.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
                file_count += 1
        
        return {
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'file_count': file_count,
            'folder_path': str(folder)
        }
    
    def archive_old_documents(self, days_old: int = 2555) -> int:
        """Archive documents older than specified days (HIPAA 7 years)"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        archived_count = 0
        
        # Query old documents
        old_docs = PatientDocument.query.filter(
            PatientDocument.created_at < cutoff_date,
            PatientDocument.archived == False
        ).all()
        
        for doc in old_docs:
            try:
                self._archive_document(doc)
                doc.archived = True
                archived_count += 1
            except Exception as e:
                logger.error(f"Failed to archive document {doc.id}: {str(e)}")
        
        db.session.commit()
        return archived_count
    
    def _archive_document(self, document: PatientDocument):
        """Move document to archive storage"""
        archive_folder = self.backup_path / 'archive' / str(document.patient_id)
        archive_folder.mkdir(parents=True, exist_ok=True)
        
        # Move files
        if document.file_path and Path(document.file_path).exists():
            shutil.move(document.file_path, 
                       archive_folder / Path(document.file_path).name)
        
        if document.text_path and Path(document.text_path).exists():
            shutil.move(document.text_path,
                       archive_folder / Path(document.text_path).name)
    
    def perform_backup(self) -> Dict[str, Any]:
        """Perform encrypted backup to external storage"""
        from app.auth.security import FileEncryption, generate_file_key
        
        backup_key = generate_file_key()
        encryptor = FileEncryption(backup_key)
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_name = f"psyward_backup_{timestamp}"
        
        # Create backup archive
        temp_archive = Path('/tmp') / f"{backup_name}.tar"
        
        try:
            # Create tar archive
            import tarfile
            with tarfile.open(temp_archive, 'w') as tar:
                tar.add(self.base_path, arcname='patient_data')
            
            # Encrypt backup
            encrypted_backup = self.backup_path / f"{backup_name}.enc"
            encryptor.encrypt_file(str(temp_archive), str(encrypted_backup))
            
            # Save backup key (should be stored securely offline)
            key_file = self.backup_path / f"{backup_name}.key"
            with open(key_file, 'wb') as f:
                f.write(backup_key)
            os.chmod(key_file, 0o600)
            
            # Calculate backup size
            backup_size = encrypted_backup.stat().st_size
            
            return {
                'success': True,
                'backup_file': str(encrypted_backup),
                'key_file': str(key_file),
                'size_mb': round(backup_size / (1024 * 1024), 2),
                'timestamp': timestamp
            }
            
        finally:
            # Cleanup temp file
            if temp_archive.exists():
                temp_archive.unlink()
    
    def verify_storage_integrity(self) -> List[Dict[str, Any]]:
        """Verify integrity of stored documents"""
        issues = []
        
        # Check all patient documents
        documents = PatientDocument.query.filter_by(archived=False).all()
        
        for doc in documents:
            # Check file existence
            if doc.file_path and not Path(doc.file_path).exists():
                issues.append({
                    'document_id': doc.id,
                    'issue': 'missing_file',
                    'path': doc.file_path
                })
            
            # Check text file
            if doc.text_path and not Path(doc.text_path).exists():
                issues.append({
                    'document_id': doc.id,
                    'issue': 'missing_ocr',
                    'path': doc.text_path
                })
            
            # Verify file size matches
            if doc.file_path and Path(doc.file_path).exists():
                actual_size = Path(doc.file_path).stat().st_size
                if actual_size != doc.file_size:
                    issues.append({
                        'document_id': doc.id,
                        'issue': 'size_mismatch',
                        'expected': doc.file_size,
                        'actual': actual_size
                    })
        
        return issues