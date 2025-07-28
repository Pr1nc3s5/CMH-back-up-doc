#!/bin/bash
# system/pi_setup/02_optimize_os.sh
# Optimize Raspberry Pi OS for PSYWARD DMS

set -e

echo "=== Optimizing Raspberry Pi for PSYWARD DMS ==="

# Enable ZRAM for better memory management
echo "Setting up ZRAM..."
sudo apt-get install -y zram-tools
echo -e "ALGO=zstd\nPERCENT=150" | sudo tee /etc/default/zramswap
sudo service zramswap restart

# Optimize boot config
sudo tee -a /boot/config.txt << EOF

# PSYWARD optimizations
gpu_mem=16
over_voltage=2
arm_freq=1000
core_freq=500
sdram_freq=500
EOF

# Disable unnecessary services
echo "Disabling unnecessary services..."
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
sudo systemctl disable triggerhappy

# Set CPU governor to performance
echo "performance" | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Configure watchdog
sudo apt-get install -y watchdog
sudo tee /etc/watchdog.conf << EOF
watchdog-device = /dev/watchdog
max-load-1 = 24
min-memory = 1
watchdog-timeout = 10
EOF
sudo systemctl enable watchdog

# Set swappiness
echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf

# Install monitoring tools
sudo apt-get install -y htop iotop ncdu

echo "Optimization complete! Reboot recommended."
