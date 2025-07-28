#!/bin/bash
# scripts/deploy_pi.sh
# One-command deployment script for PSYWARD DMS

set -e

INSTALL_DIR="/opt/psyward"
SERVICE_USER="psyward"

echo "=== PSYWARD DMS Deployment Script ==="

# Create service user
if ! id "$SERVICE_USER" &>/dev/null; then
    sudo useradd -r -s /bin/false -d $INSTALL_DIR $SERVICE_USER
fi

# Create directory structure
sudo mkdir -p $INSTALL_DIR
sudo mkdir -p /var/log/psyward
sudo mkdir -p /etc/psyward/keys
sudo mkdir -p /mnt/encrypted_data/{patients,uploads,backup}

# Clone or update repository
if [ -d "$INSTALL_DIR/.git" ]; then
    cd $INSTALL_DIR
    sudo -u $SERVICE_USER git pull
else
    sudo git clone https://github.com/your-org/psyward-dms.git $INSTALL_DIR
    sudo chown -R $SERVICE_USER:$SERVICE_USER $INSTALL_DIR
fi

# Create Python virtual environment
cd $INSTALL_DIR
sudo -u $SERVICE_USER python3.9 -m venv venv
sudo -u $SERVICE_USER ./venv/bin/pip install --upgrade pip

# Install Python dependencies
sudo -u $SERVICE_USER ./venv/bin/pip install -r requirements.txt

# Set up environment
sudo tee /etc/psyward/psyward.env << EOF
FLASK_APP=app.py
FLASK_ENV=production
SECRET_KEY=$(openssl rand -hex 32)
DB_PATH=/mnt/encrypted_data/psyward.db
MASTER_KEY_PATH=/etc/psyward/keys/master.key
EOF

# Initialize database
cd $INSTALL_DIR
sudo -u $SERVICE_USER ./venv/bin/python -m flask db init
sudo -u $SERVICE_USER ./venv/bin/python -m flask db migrate
sudo -u $SERVICE_USER ./venv/bin/python -m flask db upgrade

# Set permissions
sudo chown -R $SERVICE_USER:$SERVICE_USER /var/log/psyward
sudo chown -R $SERVICE_USER:$SERVICE_USER /etc/psyward
sudo chown -R $SERVICE_USER:$SERVICE_USER /mnt/encrypted_data
sudo chmod 700 /etc/psyward/keys

# Install systemd service
sudo cp $INSTALL_DIR/system/services/psyward.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable psyward.service

# Configure Nginx
sudo tee /etc/nginx/sites-available/psyward << EOF
server {
    listen 80;
    server_name _;
    
    # Redirect to HTTPS
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl http2;
    server_name _;
    
    ssl_certificate /etc/psyward/ssl/cert.pem;
    ssl_certificate_key /etc/psyward/ssl/key.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts for Pi Zero
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
        proxy_read_timeout 300;
    }
    
    # File upload size
    client_max_body_size 10M;
}
EOF

# Generate self-signed SSL certificate
sudo mkdir -p /etc/psyward/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/psyward/ssl/key.pem \
    -out /etc/psyward/ssl/cert.pem \
    -subj "/C=US/ST=State/L=City/O=PSYWARD/CN=psyward.local"

# Enable Nginx site
sudo ln -sf /etc/nginx/sites-available/psyward /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Start services
sudo systemctl start psyward.service

echo "=== Deployment Complete! ==="
echo "Access PSYWARD DMS at: https://$(hostname -I | cut -d' ' -f1)"
echo "Default admin credentials: admin@psyward.local / ChangeMe123!"
echo "IMPORTANT: Change the default password immediately!"