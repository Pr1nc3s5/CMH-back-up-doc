"""
Automated backup script for PSYWARD DMS
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.documents.storage import PatientStorageManager

def main():
    app = create_app('production')
    
    with app.app_context():
        storage_mgr = PatientStorageManager()
        
        print(f"Starting backup at {datetime.utcnow()}")
        
        try:
            result = storage_mgr.perform_backup()
            
            if result['success']:
                print(f"Backup completed successfully")
                print(f"Backup file: {result['backup_file']}")
                print(f"Size: {result['size_mb']} MB")
                
                # Copy to external USB if mounted
                usb_path = Path('/mnt/usb_backup')
                if usb_path.exists():
                    import shutil
                    shutil.copy2(result['backup_file'], usb_path)
                    shutil.copy2(result['key_file'], usb_path)
                    print("Backup copied to USB drive")
            else:
                print("Backup failed!")
                sys.exit(1)
                
        except Exception as e:
            print(f"Backup error: {str(e)}")
            sys.exit(1)

if __name__ == '__main__':
    main()
