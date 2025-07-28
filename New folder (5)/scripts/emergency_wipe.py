#!/usr/bin/env python3
"""
Emergency data wipe script for PSYWARD DMS
Triggered by physical tamper detection or manual activation
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WIPE_PATHS = [
    '/etc/psyward/keys',
    '/mnt/encrypted_data',
    '/var/log/psyward',
    '/opt/psyward/instance'
]

def secure_delete(path: Path):
    """Securely delete a file or directory"""
    if path.is_file():
        # Overwrite file with random data
        size = path.stat().st_size
        with open(path, 'wb') as f:
            f.write(os.urandom(size))
        os.unlink(path)
    elif path.is_dir():
        shutil.rmtree(path)

def crypto_shred():
    """Emergency cryptographic shredding"""
    logger.warning("EMERGENCY WIPE INITIATED!")
    
    # 1. Delete encryption keys (renders data unreadable)
    key_path = Path('/etc/psyward/keys')
    if key_path.exists():
        logger.info("Shredding encryption keys...")
        for key_file in key_path.glob('*.key'):
            secure_delete(key_file)
    
    # 2. Unmount encrypted volumes
    try:
        subprocess.run(['umount', '/mnt/encrypted_data'], check=False)
        subprocess.run(['cryptsetup', 'luksClose', 'psyward_data'], check=False)
    except:
        pass
    
    # 3. Wipe LUKS headers (makes encrypted data permanently unrecoverable)
    try:
        subprocess.run(['cryptsetup', 'luksErase', '/dev/mmcblk0p3'], check=False)
    except:
        pass
    
    # 4. Delete application data
    for wipe_path in WIPE_PATHS:
        path = Path(wipe_path)
        if path.exists():
            logger.info(f"Wiping {path}...")
            secure_delete(path)
    
    # 5. Clear system logs
    subprocess.run(['journalctl', '--rotate'], check=False)
    subprocess.run(['journalctl', '--vacuum-time=1s'], check=False)
    
    logger.info("EMERGENCY WIPE COMPLETE - System shutting down")
    
    # 6. Shutdown system
    subprocess.run(['shutdown', '-h', 'now'])

if __name__ == '__main__':
    # Require confirmation
    if len(sys.argv) > 1 and sys.argv[1] == '--confirm':
        crypto_shred()
    else:
        print("EMERGENCY WIPE - This will permanently destroy all data!")
        print("Run with --confirm to execute")
        sys.exit(1)