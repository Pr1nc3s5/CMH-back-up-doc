#!/bin/bash
# system/pi_setup/01_encrypt_disk.sh
# Setup LUKS encryption for Raspberry Pi SD card

set -e

echo "=== PSYWARD DMS - Disk Encryption Setup ==="
echo "WARNING: This will encrypt your SD card. Make sure you have backups!"
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Install required packages
sudo apt-get update
sudo apt-get install -y cryptsetup

# Create encrypted partition (assuming /dev/mmcblk0p3 for data)
echo "Setting up encrypted partition..."
sudo cryptsetup luksFormat /dev/mmcblk0p3

# Open encrypted partition
echo "Opening encrypted partition..."
sudo cryptsetup luksOpen /dev/mmcblk0p3 psyward_data

# Format with BTRFS for compression
sudo mkfs.btrfs -L psyward_data /dev/mapper/psyward_data

# Mount with compression
sudo mkdir -p /mnt/encrypted_data
sudo mount -o compress-force=zstd:1,noatime /dev/mapper/psyward_data /mnt/encrypted_data

# Add to crypttab for boot
echo "psyward_data /dev/mmcblk0p3 none luks" | sudo tee -a /etc/crypttab

# Add to fstab
echo "/dev/mapper/psyward_data /mnt/encrypted_data btrfs compress-force=zstd:1,noatime 0 0" | sudo tee -a /etc/fstab

echo "Encryption setup complete!"