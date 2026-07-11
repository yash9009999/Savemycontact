#!/bin/bash
# EC2 Deployment Script for Contact Extractor
# Run this on a fresh Ubuntu 22.04/24.04 EC2 instance
# Usage: chmod +x deploy.sh && sudo ./deploy.sh

set -e

APP_USER="ubuntu"
APP_DIR="/home/$APP_USER/contact-extractor"
REPO_URL="https://github.com/yash9009999/Savemycontact.git"

echo "========================================="
echo "  Contact Extractor - EC2 Deployment"
echo "========================================="

# Update system
echo "[1/7] Updating system packages..."
apt-get update && apt-get upgrade -y

# Install dependencies
echo "[2/7] Installing system dependencies..."
apt-get install -y python3 python3-pip python3-venv python3-dev nginx tesseract-ocr git \
    libjpeg-dev libpng-dev libtiff-dev libwebp-dev zlib1g-dev libfreetype6-dev \
    liblcms2-dev libopenjp2-7-dev build-essential

# Clone repository
echo "[3/7] Cloning repository..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# Set up virtual environment
echo "[4/7] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create directories
mkdir -p static/uploads csv_archive

# Set permissions
chown -R $APP_USER:$APP_USER "$APP_DIR"

# Create systemd service
echo "[5/7] Creating systemd service..."
cat > /etc/systemd/system/contact-extractor.service << EOF
[Unit]
Description=Contact Extractor Flask App
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
Environment="ADMIN_USER=admin"
Environment="ADMIN_PASS=admin@5001"
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 3 --bind unix:contact-extractor.sock --timeout 120 app:app

[Install]
WantedBy=multi-user.target
EOF

# Configure Nginx
echo "[6/7] Configuring Nginx..."
cat > /etc/nginx/sites-available/contact-extractor << EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 50M;

    location / {
        proxy_pass http://unix:/home/$APP_USER/contact-extractor/contact-extractor.sock;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location /static {
        alias $APP_DIR/static;
        expires 1d;
    }
}
EOF

# Enable site
ln -sf /etc/nginx/sites-available/contact-extractor /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t

# Start services
echo "[7/7] Starting services..."
systemctl daemon-reload
systemctl enable contact-extractor
systemctl restart contact-extractor
systemctl restart nginx

echo ""
echo "========================================="
echo "  Deployment Complete!"
echo "========================================="
echo ""
echo "  App URL: http://$(curl -s ifconfig.me)"
echo "  Admin:   http://$(curl -s ifconfig.me)/admin/login"
echo ""
echo "  Credentials:"
echo "    Username: admin"
echo "    Password: admin@5001"
echo ""
echo "  Useful commands:"
echo "    sudo systemctl status contact-extractor"
echo "    sudo systemctl restart contact-extractor"
echo "    sudo journalctl -u contact-extractor -f"
echo "========================================="
