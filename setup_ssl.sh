#!/bin/bash
# Self-signed SSL setup for NexVision using OpenSSL
set -e

SERVER_IP=$(hostname -I | awk '{print $1}')
SSL_DIR="/etc/ssl/nexvision"
NGINX_CONF="/etc/nginx/sites-available/nexvision"
NGINX_BACKUP="${NGINX_CONF}.pre-ssl.bak"
DH_PARAMS="/etc/ssl/nexvision/dhparam.pem"

echo "[1/4] Creating SSL directory..."
mkdir -p "$SSL_DIR"
chmod 755 "$SSL_DIR"

echo "[2/4] Generating self-signed certificate (RSA-4096, 10 years)..."
echo "      CN = $SERVER_IP"
openssl req -x509 -nodes -days 3650 \
  -newkey rsa:4096 \
  -keyout "$SSL_DIR/nexvision.key" \
  -out    "$SSL_DIR/nexvision.crt" \
  -subj   "/C=US/ST=Local/L=Local/O=NexVision/OU=IPTV/CN=${SERVER_IP}" \
  -addext "subjectAltName=IP:${SERVER_IP},IP:127.0.0.1"

chmod 600 "$SSL_DIR/nexvision.key"
chmod 644 "$SSL_DIR/nexvision.crt"

echo "[3/4] Generating DH parameters (2048-bit)..."
openssl dhparam -out "$DH_PARAMS" 2048
chmod 644 "$DH_PARAMS"

echo "[4/4] Updating Nginx config..."
cp "$NGINX_CONF" "$NGINX_BACKUP"
echo "      Backup saved: $NGINX_BACKUP"

cat > "$NGINX_CONF" << 'NGINXCONF'
# ─────────────────────────────────────────────────────────────────────────────
# NexVision IPTV — Nginx Production Configuration (HTTPS + Self-Signed SSL)
# ─────────────────────────────────────────────────────────────────────────────

upstream nexvision_app {
    server unix:/run/nexvision/gunicorn.sock fail_timeout=0;
    keepalive 64;
}

proxy_cache_path /var/cache/nexvision/hls
    levels=1:2
    keys_zone=hls_cache:10m
    max_size=500m
    inactive=60s
    use_temp_path=off;

proxy_cache_path /var/cache/nexvision/api
    levels=1:2
    keys_zone=api_cache:20m
    max_size=200m
    inactive=120s
    use_temp_path=off;

# ── HTTP → HTTPS redirect ─────────────────────────────────────────────────────
server {
    listen 80;
    listen [::]:80;
    server_name _;
    return 301 https://$host$request_uri;
}

# ── HTTPS server ──────────────────────────────────────────────────────────────
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name _;

    # ── SSL certificates ──────────────────────────────────────────────────────
    ssl_certificate     /etc/ssl/nexvision/nexvision.crt;
    ssl_certificate_key /etc/ssl/nexvision/nexvision.key;
    ssl_dhparam         /etc/ssl/nexvision/dhparam.pem;

    # ── Modern TLS settings ───────────────────────────────────────────────────
    ssl_protocols             TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers               ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_session_cache         shared:SSL:10m;
    ssl_session_timeout       1d;
    ssl_session_tickets       off;

    # ── Security headers ──────────────────────────────────────────────────────
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;
    add_header X-Frame-Options           SAMEORIGIN                            always;
    add_header X-Content-Type-Options    nosniff                               always;
    add_header X-XSS-Protection          "1; mode=block"                       always;
    add_header Referrer-Policy           "strict-origin-when-cross-origin"     always;

    access_log  /var/log/nginx/nexvision_access.log  combined buffer=64k flush=5s;
    error_log   /var/log/nginx/nexvision_error.log   warn;

    client_max_body_size 4G;
    sendfile   on;
    tcp_nopush on;
    tcp_nodelay on;

    gzip on;
    gzip_types application/json text/plain text/css application/javascript;
    gzip_min_length 1024;

    # ── Static files ──────────────────────────────────────────────────────────
    location / {
        root /opt/nexvision/web/tv;
        try_files $uri $uri/index.html @flask;
        expires 1h;
        add_header Cache-Control "public, must-revalidate";
    }

    location /admin/ {
        alias /opt/nexvision/web/admin/;
        try_files $uri $uri/index.html @flask;
        expires 1h;
        add_header Cache-Control "public, must-revalidate";
    }

    # ── X-Accel-Redirect internal location ───────────────────────────────────
    location /internal/vod/ {
        internal;
        alias /opt/nexvision/vod/;
        add_header Cache-Control "public, max-age=3600";
        add_header Access-Control-Allow-Origin "*";
        sendfile on;
        tcp_nopush on;
        add_header Accept-Ranges bytes;
    }

    # ── HLS playlists (.m3u8) ─────────────────────────────────────────────────
    location ~* ^/vod/hls/(.+)\.m3u8$ {
        proxy_pass http://nexvision_app;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache         hls_cache;
        proxy_cache_key     "$uri";
        proxy_cache_valid   200 5s;
        proxy_cache_use_stale error timeout updating;
        add_header X-Cache-Status $upstream_cache_status;
    }

    # ── HLS segments (.ts) ────────────────────────────────────────────────────
    location ~* ^/vod/hls/.+\.ts$ {
        proxy_pass http://nexvision_app;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
    }

    # ── VOD thumbnails ────────────────────────────────────────────────────────
    location /vod/thumbnails/ {
        alias /opt/nexvision/vod/thumbnails/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    # ── Flask fallback ────────────────────────────────────────────────────────
    location @flask {
        proxy_pass http://nexvision_app;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect   off;
        proxy_read_timeout 120s;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }

    # ── API proxy ─────────────────────────────────────────────────────────────
    location /api/ {
        proxy_pass http://nexvision_app;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
    }

    # ── VOD proxy ─────────────────────────────────────────────────────────────
    location /vod/ {
        proxy_pass http://nexvision_app;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_read_timeout 300s;
        client_max_body_size 4G;
    }
}
NGINXCONF

echo ""
echo "Testing Nginx config..."
nginx -t && systemctl reload nginx

echo ""
echo "====================================================="
echo " HTTPS is now active on https://${SERVER_IP}"
echo " HTTP port 80 redirects to HTTPS automatically."
echo " Certificate: $SSL_DIR/nexvision.crt"
echo " Key:         $SSL_DIR/nexvision.key"
echo " NOTE: Browsers will show a security warning for"
echo "       self-signed certs — this is expected."
echo "       Accept the warning to proceed."
echo "====================================================="
