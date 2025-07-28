#!/bin/bash
# system/pi_setup/03_install_deps.sh
# Install PSYWARD dependencies on Raspberry Pi

set -e

echo "=== Installing PSYWARD Dependencies ==="

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python 3.9 and development tools
sudo apt-get install -y \
    python3.9 python3.9-dev python3.9-venv \
    python3-pip build-essential

# Install system dependencies
sudo apt-get install -y \
    tesseract-ocr tesseract-ocr-eng \
    libtesseract-dev libleptonica-dev \
    libmagic1 libmagic-dev \
    libjpeg-dev libpng-dev libtiff-dev \
    libwebp-dev libopenjp2-7-dev \
    libssl-dev libffi-dev \
    sqlite3 libsqlite3-dev \
    nginx redis-server \
    git curl wget

# Install ImageMagick for PDF processing
sudo apt-get install -y imagemagick

# Build and install Tesseract with medical dictionary
echo "Building Tesseract with medical dictionary..."
cd /tmp
wget https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata
sudo mkdir -p /usr/share/tesseract-ocr/5/tessdata
sudo cp eng.traineddata /usr/share/tesseract-ocr/5/tessdata/

# Install SQLCipher
echo "Building SQLCipher..."
cd /tmp
git clone https://github.com/sqlcipher/sqlcipher.git
cd sqlcipher
./configure --enable-tempstore=yes CFLAGS="-DSQLITE_HAS_CODEC" LDFLAGS="-lcrypto"
make
sudo make install

# Install Python packages (ARM-optimized)
echo "Installing Python packages..."
pip3 install --upgrade pip wheel setuptools

# Create medical dictionary for Tesseract
sudo tee /usr/share/tesseract-ocr/5/tessdata/medical.user-words << EOF
diagnosis
prescription
medication
symptom
psychiatric
psychotropic
antidepressant
antipsychotic
benzodiazepine
schizophrenia
bipolar
depression
anxiety
therapy
counseling
admission
discharge
EOF

echo "Dependencies installed successfully!"