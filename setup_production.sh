#!/usr/bin/env bash
# =============================================================================
# NexVision IPTV — Production Server Setup
# Tested on Ubuntu 22.04 / Debian 12
#
# Usage:
#   sudo bash setup_production.sh
# =============================================================================
set -euo pipefail

APP_DIR="/var/www/nexvision"
DATA_DIR="/var/www/nexvision/vod_data"
LOG_DIR="/var/log/nexvision"
RUN_DIR="/run/nexvision"
CACHE_DIR="/var/cache/nexvision"
SERVICE_USER="www-data"

echo "=== NexVision Production Setup ==="

# ── 1. System packages ────────────────────────────────────────────────────────
echo "[1/8] Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    nginx \
    redis-server \
    mysql-server \
    python3 python3-pip python3-venv \
    ffmpeg \
    curl \
    ca-certificates

# ── 2. Python virtual environment ─────────────────────────────────────────────
echo "[2/8] Setting up Python virtualenv..."
python3 -m venv /opt/nexvision-venv
/opt/nexvision-venv/bin/pip install --upgrade pip -q
/opt/nexvision-venv/bin/pip install -r "$(dirname "$0")/requirements_prod.txt" -q

# ── 3. MySQL database ─────────────────────────────────────────────────────────
echo "[3/8] Configuring MySQL..."
# Load credentials from .env if present
ENV_FILE="$(dirname "$0")/.env"
if [[ -f "$ENV_FILE" ]]; then
    source <(grep -E '^(MYSQL_|VOD_MYSQL_)' "$ENV_FILE" | sed 's/^/export /')
fi

MYSQL_USER="${MYSQL_USER:-nexvision}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-change_me}"
MYSQL_DB="${MYSQL_DB:-nexvision}"
VOD_MYSQL_DB="${VOD_MYSQL_DB:-nexvision_vod}"

mysql -u root <<SQL
CREATE DATABASE IF NOT EXISTS \`${MYSQL_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS \`${VOD_MYSQL_DB}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${MYSQL_USER}'@'localhost' IDENTIFIED BY '${MYSQL_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${MYSQL_DB}\`.* TO '${MYSQL_USER}'@'localhost';
GRANT ALL PRIVILEGES ON \`${VOD_MYSQL_DB}\`.* TO '${MYSQL_USER}'@'localhost';
FLUSH PRIVILEGES;
SQL
echo "    MySQL databases and user created."

# ── 4. Redis ──────────────────────────────────────────────────────────────────
echo "[4/8] Enabling Redis..."
systemctl enable --now redis-server
echo "    Redis running."

# ── 5. Directory structure ────────────────────────────────────────────────────
echo "[5/8] Creating directories..."
mkdir -p "$APP_DIR"/{tv,admin} "$DATA_DIR"/{hls,thumbnails,uploads} \
         "$LOG_DIR" "$CACHE_DIR"/{hls,api}

# Runtime socket directory — must survive reboots; use tmpfiles.d
cat > /etc/tmpfiles.d/nexvision.conf <<EOF
d $RUN_DIR 0755 $SERVICE_USER $SERVICE_USER -
EOF
systemd-tmpfiles --create /etc/tmpfiles.d/nexvision.conf

chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR" "$DATA_DIR" \
         "$LOG_DIR" "$CACHE_DIR" "$RUN_DIR"
chmod -R 755 "$APP_DIR" "$DATA_DIR"

# ── 6. Nginx ──────────────────────────────────────────────────────────────────
echo "[6/8] Installing Nginx config..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/nginx/nexvision.conf" /etc/nginx/sites-available/nexvision
ln -sf /etc/nginx/sites-available/nexvision /etc/nginx/sites-enabled/nexvision
rm -f /etc/nginx/sites-enabled/default   # remove default site

nginx -t && systemctl reload nginx
echo "    Nginx configured."

# ── 7. Systemd service ────────────────────────────────────────────────────────
echo "[7/8] Installing systemd service..."
cat > /etc/systemd/system/nexvision.service <<EOF
[Unit]
Description=NexVision IPTV (Gunicorn + gevent)
After=network.target mysql.service redis.service
Requires=mysql.service redis.service

[Service]
Type=notify
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${SCRIPT_DIR}
EnvironmentFile=${SCRIPT_DIR}/.env
ExecStart=/opt/nexvision-venv/bin/gunicorn -c ${SCRIPT_DIR}/gunicorn.conf.py wsgi:application
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=30
Restart=on-failure
RestartSec=5s

# Security hardening
PrivateTmp=true
ProtectSystem=full
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nexvision
echo "    systemd service installed."

# ── 8. Static files ───────────────────────────────────────────────────────────
echo "[8/8] Symlinking static files..."
# TV client and admin panel served directly by Nginx
ln -sfn "$SCRIPT_DIR/tv"    "$APP_DIR/tv"
ln -sfn "$SCRIPT_DIR/admin" "$APP_DIR/admin"

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit ${SCRIPT_DIR}/.env   (copy from .env.example, set USE_MYSQL=1 USE_X_ACCEL=1)"
echo "  2. sudo systemctl start nexvision"
echo "  3. sudo systemctl status nexvision"
echo "  4. sudo journalctl -u nexvision -f   (follow logs)"
echo ""
echo "Static files:   $APP_DIR/{tv,admin}"
echo "VOD data:       $DATA_DIR"
echo "Logs:           $LOG_DIR"
echo "Socket:         $RUN_DIR/gunicorn.sock"
