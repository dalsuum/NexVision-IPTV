# NexVision IPTV Platform - Complete Deployment Guide

**Version**: 2.0 (March 2026)
**System**: NexVision IPTV Platform v8.9
**Target OS**: Ubuntu 22.04 LTS / Debian 12
**Classification**: Technical Deployment Guide

---

## 📋 Pre-Deployment Checklist

Before starting, confirm:
- [ ] Server meets minimum hardware requirements (see §1)
- [ ] Ubuntu 22.04 LTS installed and updated
- [ ] SSH access to server confirmed
- [ ] Domain name or static IP assigned
- [ ] MySQL root password ready (if using MySQL instead of SQLite)
- [ ] SSL certificate available (optional, for HTTPS)
- [ ] Maintenance window approved
- [ ] Rollback plan confirmed

---

## 1. HARDWARE REQUIREMENTS

### Minimum Requirements
| Component | Specification | Notes |
|-----------|---------------|-------|
| **CPU** | 4 cores (Intel/AMD 64-bit) | Streaming transcoding workload |
| **RAM** | 8GB | 4GB minimum, 16GB recommended |
| **Storage** | 100GB SSD | 50GB system + 50GB content |
| **Network** | 1Gbps | Critical for concurrent streaming |
| **OS** | Ubuntu 22.04 LTS | Debian 12 also supported |

### Production Requirements (500+ concurrent streams)
| Component | Specification | Notes |
|-----------|---------------|-------|
| **CPU** | 16+ cores | High-performance streaming |
| **RAM** | 32GB+ | Multiple concurrent processes |
| **Storage** | 1TB+ NVMe SSD | High-performance VOD delivery |
| **Network** | 10Gbps | Dedicated network interface |

---

## 2. SYSTEM PREPARATION

### 2.1 Update System
```bash
# Update package lists and system
sudo apt update && sudo apt full-upgrade -y

# Install essential packages
sudo apt install -y python3 python3-pip python3-venv git nginx sqlite3 \
    curl wget unzip htop ncdu tree jq

# Install Python development headers (for some packages)
sudo apt install -y python3-dev build-essential

# Reboot if kernel was updated
sudo reboot
```

### 2.2 Create System User
```bash
# Create nexvision system user
sudo useradd -r -m -s /bin/bash nexvision

# Add to www-data group for Nginx integration
sudo usermod -a -G www-data nexvision

# Set up basic directory structure
sudo mkdir -p /opt/nexvision/{logs,backups,hls,thumbnails,vod_data}
sudo chown -R nexvision:nexvision /opt/nexvision
```

### 2.3 Database Setup (SQLite Default)
```bash
# SQLite is the default - no additional setup needed
# Database will be created automatically at /opt/nexvision/nexvision.db

# Optional: Install MySQL/MariaDB instead
# sudo apt install -y mysql-server mysql-client
# sudo mysql_secure_installation
```

---

## 3. APPLICATION DEPLOYMENT

### 3.1 Clone/Deploy Application Code
```bash
# Method A: Git clone (if repository available)
sudo -u nexvision git clone https://github.com/your-org/nexvision.git /opt/nexvision
cd /opt/nexvision

# Method B: Upload files directly
# Upload your nexvision files to /opt/nexvision/
sudo chown -R nexvision:nexvision /opt/nexvision
```

### 3.2 Python Environment Setup
```bash
# Switch to nexvision user
sudo -u nexvision bash
cd /opt/nexvision

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install flask gunicorn requests python-dotenv sqlite3 \
    PyMySQL cryptography Pillow feedparser xmltodict

# Multi-storage backend dependencies (optional)
pip install boto3 azure-storage-blob google-cloud-storage
```

### 3.3 Application Configuration

#### Create Environment File
```bash
# Create .env configuration file
cat > /opt/nexvision/.env << 'EOF'
# Basic Configuration
SECRET_KEY=your-secret-key-here-change-this
VOD_API_KEY=your-vod-api-key-here
DEBUG=False
DATABASE_URL=sqlite:///nexvision.db

# Hotel Information
HOTEL_NAME=NexVision Hotel
HOTEL_LOGO=
DEPLOYMENT_MODE=hotel

# Storage Configuration (Multi-Storage)
VOD_STORAGE_TYPE=local
VOD_STORAGE_CONFIG={"base_path": "/opt/nexvision/vod_data"}

# S3 Storage (if using)
# VOD_STORAGE_TYPE=s3
# VOD_STORAGE_CONFIG={"bucket": "nexvision-vod", "region": "us-east-1", "access_key": "your-key", "secret_key": "your-secret"}

# Azure Storage (if using)
# VOD_STORAGE_TYPE=azure
# VOD_STORAGE_CONFIG={"account_name": "nexvision", "account_key": "your-key", "container": "vod"}

# GCS Storage (if using)
# VOD_STORAGE_TYPE=gcs
# VOD_STORAGE_CONFIG={"bucket": "nexvision-vod", "credentials_file": "/opt/nexvision/gcs-credentials.json"}

# NAS Storage (if using)
# VOD_STORAGE_TYPE=nas
# VOD_STORAGE_CONFIG={"base_path": "/mnt/nas/vod_data", "mount_point": "/mnt/nas"}
EOF

# Set secure permissions
chown nexvision:nexvision .env
chmod 600 .env

# Generate secure keys
python3 -c "import secrets; print(f'SECRET_KEY={secrets.token_urlsafe(32)}')" >> .env.tmp
python3 -c "import secrets; print(f'VOD_API_KEY={secrets.token_urlsafe(32)}')" >> .env.tmp
# Then manually update .env with the generated keys
```

### 3.4 Database Initialization
```bash
# Initialize database (run as nexvision user)
cd /opt/nexvision
source venv/bin/activate

# Start application briefly to create database
python3 app.py &
sleep 5
pkill -f "python3 app.py"

# Verify database creation
ls -la nexvision.db
sqlite3 nexvision.db ".tables"
```

---

## 4. WEB SERVER CONFIGURATION

### 4.1 Nginx Configuration
```bash
# Create nginx site configuration
sudo tee /etc/nginx/sites-available/nexvision << 'EOF'
server {
    listen 80;
    server_name localhost;  # Change to your domain

    client_max_body_size 1G;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    # Static content caching
    location ~* \.(css|js|jpg|jpeg|png|gif|ico|svg|woff|woff2|ttf|eot|m3u8|ts|mp4)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # Internal file serving for HLS/VOD (X-Accel-Redirect)
    location /internal/vod/ {
        internal;
        alias /opt/nexvision/;
    }

    # VOD thumbnails
    location /vod/thumbnails/ {
        alias /opt/nexvision/thumbnails/;
    }

    # Main application proxy
    location / {
        proxy_pass http://YOUR_SERVER_IP_HERE:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;

        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

# Enable site and restart nginx
sudo ln -s /etc/nginx/sites-available/nexvision /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4.2 SSL/HTTPS Configuration (Optional)

#### Using Let's Encrypt
```bash
# Install certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com

# Verify auto-renewal
sudo certbot renew --dry-run
```

#### Using Custom Certificate
```bash
# Copy your certificate files to:
# /etc/ssl/certs/nexvision.crt
# /etc/ssl/private/nexvision.key

# Update nginx configuration with SSL block
# (Add listen 443 ssl, ssl_certificate directives)
```

---

## 5. SERVICE CONFIGURATION

### 5.1 Log Directory

# 1. Create the log directory
sudo mkdir -p /var/log/nexvision

# 2. Change ownership so the service can write to it
# (Assuming your service runs as user 'a13', if not, use 'www-data' or the appropriate user)
sudo chown -R a13:a13 /var/log/nexvision

# 3. Create the actual log files just to be safe
sudo touch /var/log/nexvision/access.log /var/log/nexvision/error.log
sudo chmod 664 /var/log/nexvision/*.log

### 5.2 Systemd Service Setup
```bash
# Create systemd service file
sudo tee /etc/systemd/system/nexvision.service << 'EOF'
[Unit]
Description=NexVision IPTV Platform
After=network.target mysql.service

[Service]
Type=notify
User=nexvision
Group=nexvision
RuntimeDirectory=nexvision
WorkingDirectory=/opt/nexvision
Environment=PATH=/opt/nexvision/venv/bin
ExecStart=/opt/nexvision/venv/bin/gunicorn --bind YOUR_SERVER_IP_HERE:5000 --workers 4 --timeout 120 app:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable nexvision
sudo systemctl start nexvision

# Check service status
sudo systemctl status nexvision
```

### 5.2 Log Rotation Setup
```bash
# Create logrotate configuration
sudo tee /etc/logrotate.d/nexvision << 'EOF'
/opt/nexvision/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    copytruncate
    notifempty
    missingok
    su nexvision nexvision
}
EOF
```

---

## 6. MULTI-STORAGE BACKEND SETUP

### 6.1 Local Storage (Default)
```bash
# Create storage directories
sudo -u nexvision mkdir -p /opt/nexvision/{vod_data,hls,thumbnails}

# Set permissions
sudo chmod 755 /opt/nexvision/vod_data
sudo chmod 755 /opt/nexvision/hls
sudo chmod 755 /opt/nexvision/thumbnails
```

### 6.2 NAS Storage Setup
```bash
# Install NFS client (for NFS mounts)
sudo apt install -y nfs-common

# Create mount point
sudo mkdir -p /mnt/nas

# Add to /etc/fstab for permanent mount
echo "nas-server:/volume/nexvision /mnt/nas nfs defaults 0 0" | sudo tee -a /etc/fstab

# Mount NAS
sudo mount -a

# Update .env configuration
# VOD_STORAGE_TYPE=nas
# VOD_STORAGE_CONFIG={"base_path": "/mnt/nas/vod_data", "mount_point": "/mnt/nas"}
```

### 6.3 Cloud Storage Setup (S3/Azure/GCS)

#### AWS S3
```bash
# Create credentials file (if not using IAM roles)
sudo -u nexvision mkdir -p /opt/nexvision/.aws
cat > /opt/nexvision/.aws/credentials << EOF
[default]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY
EOF

# Update .env
# VOD_STORAGE_TYPE=s3
# VOD_STORAGE_CONFIG={"bucket": "nexvision-vod", "region": "us-east-1"}
```

#### Azure Blob Storage
```bash
# Update .env with Azure configuration
# VOD_STORAGE_TYPE=azure
# VOD_STORAGE_CONFIG={"account_name": "nexvision", "account_key": "your-key", "container": "vod"}
```

#### Google Cloud Storage
```bash
# Upload service account key file
# Place your GCS credentials JSON file at /opt/nexvision/gcs-credentials.json
sudo chown nexvision:nexvision /opt/nexvision/gcs-credentials.json
chmod 600 /opt/nexvision/gcs-credentials.json

# Update .env
# VOD_STORAGE_TYPE=gcs
# VOD_STORAGE_CONFIG={"bucket": "nexvision-vod", "credentials_file": "/opt/nexvision/gcs-credentials.json"}
```

---

## 7. INITIAL CONFIGURATION

### 7.1 Admin User Setup
```bash
# Access the admin panel
# Navigate to: http://your-server/admin
# Login with default credentials (check app.py for defaults)
# Change admin password immediately

# Or create admin user via database
sqlite3 /opt/nexvision/nexvision.db
INSERT INTO users (username, password_hash, role, active)
VALUES ('admin', 'your-hashed-password', 'admin', 1);
```

### 7.2 Sample Content Setup

#### Import Channels
```bash
# Upload channel M3U file via admin panel
# Or import via CSV (Admin → Channels → CSV Import)

# Example CSV format:
# name,stream_url,logo,group_title,tvg_id
# "BBC One","http://stream.url/bbc1","http://logo.url","UK","bbc1.uk"
```

#### Configure Packages
```bash
# Via Admin Panel:
# 1. Navigate to Admin → Packages → Add Package
# 2. Check "Include ALL channels (11,427+ total)" for full access
# 3. Assign package to rooms (Admin → Rooms)
```

#### Upload VOD Content
```bash
# For local storage:
sudo -u nexvision cp your-video.mp4 /opt/nexvision/vod_data/

# For cloud storage:
# Upload via admin panel or cloud provider's tools
```

### 7.3 Room Registration
```bash
# Create sample rooms via admin panel
# Admin → Rooms → Add Room
# Room numbers: 101, 102, 103, etc.

# Test room registration:
# Navigate to http://your-server on a test device
# Enter room number (e.g., 101) to register
```

---

## 8. POST-DEPLOYMENT TESTING

### 8.1 System Health Checks
```bash
# 1. Service status
systemctl status nexvision nginx

# 2. HTTP response test
curl -I http://localhost
curl -s http://YOUR_SERVER_IP_HERE/api/health

# 3. Database connectivity
sqlite3 /opt/nexvision/nexvision.db "SELECT COUNT(*) FROM channels;"

# 4. Storage backend test
curl -s http://YOUR_SERVER_IP_HERE/storage/health
```

### 8.2 Functional Testing

#### TV Client Test
1. Open `http://your-server` in a browser
2. Register with room number (e.g., 101)
3. Verify channels appear in "Live Channels"
4. Test channel playback
5. Test VOD playback
6. Test EPG data display

#### Admin Panel Test
1. Access `http://your-server/admin`
2. Login with admin credentials
3. Test channel management
4. Test package assignment
5. Test room management
6. Test storage configuration

---

## 9. SECURITY HARDENING

**Important**: Apply security hardening immediately after deployment.
See [Server-Hardening-Procedure.md](Server-Hardening-Procedure.md) for detailed procedures.

### Quick Security Checklist
- [ ] Change default admin password
- [ ] Set secure file permissions (600 for .env, 640 for app.py)
- [ ] Configure firewall (ufw or iptables)
- [ ] Enable SSL/HTTPS
- [ ] Set up fail2ban for brute force protection
- [ ] Configure log monitoring
- [ ] Disable unnecessary services
- [ ] Update system packages regularly

---

## 10. BACKUP STRATEGY

### 10.1 Database Backup
```bash
# Daily database backup
sudo -u nexvision crontab -e
# Add line:
0 2 * * * cd /opt/nexvision && sqlite3 nexvision.db ".backup backups/nexvision_$(date +\%Y\%m\%d).db"
```

### 10.2 Configuration Backup
```bash
# Backup configuration files
sudo tar -czf /opt/nexvision/backups/config_$(date +%Y%m%d).tar.gz \
    /opt/nexvision/.env \
    /opt/nexvision/app.py \
    /etc/nginx/sites-available/nexvision \
    /etc/systemd/system/nexvision.service
```

---

## 11. TROUBLESHOOTING

### Common Issues

#### "502 Bad Gateway"
- Check if nexvision service is running: `systemctl status nexvision`
- Check gunicorn port binding: `netstat -tlnp | grep 5000`
- Review nginx error log: `tail -f /var/log/nginx/error.log`

#### "Channels not loading"
- Verify package assignment: Admin → Rooms
- Check API response: `curl http://YOUR_SERVER_IP_HERE/api/channels?limit=5`
- Review room registration token

#### "VOD not playing"
- Check Nginx alias configuration for `/internal/vod/`
- Verify file permissions on VOD directory
- Test storage backend health

---

## 12. MONITORING & MAINTENANCE

### Recommended Monitoring
- System resources (CPU, RAM, disk space)
- Nginx access/error logs
- Application response times
- Database size and performance
- Storage backend connectivity
- SSL certificate expiration

### Maintenance Schedule
- **Daily**: Check service status, review error logs
- **Weekly**: Database optimization, log cleanup
- **Monthly**: Security updates, backup verification
- **Quarterly**: Performance review, capacity planning

---

## SUPPORT & DOCUMENTATION

**Related Documents**:
- [SOB-System-Operations-Book.md](SOB-System-Operations-Book.md) - Operations manual
- [Server-Hardening-Procedure.md](Server-Hardening-Procedure.md) - Security procedures
- [STORAGE-QUICK-REFERENCE.md](STORAGE-QUICK-REFERENCE.md) - Storage configuration
- [VOD-Storage-Architecture.md](VOD-Storage-Architecture.md) - Architecture details

**System Requirements**: Ubuntu 22.04 LTS, Python 3.8+, 8GB+ RAM
**Support**: Refer to operations manual for troubleshooting procedures

---

*Deployment Guide v2.0 - Updated March 23, 2026*
