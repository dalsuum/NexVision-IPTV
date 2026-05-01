# NexVision IPTV — Security Hardening Guide

> Version: v8.21 — Last updated: 2026-05-01  
> Applies to: production deployments running Nginx + Gunicorn + Flask

---

## Table of Contents

1. [Threat Model](#1-threat-model)
2. [Authentication Architecture](#2-authentication-architecture)
3. [Secrets Management](#3-secrets-management)
4. [File & OS Permissions](#4-file--os-permissions)
5. [Network & Nginx Hardening](#5-network--nginx-hardening)
6. [Redis Security](#6-redis-security)
7. [Database Security](#7-database-security)
8. [Input Validation & Injection Prevention](#8-input-validation--injection-prevention)
9. [Rate Limiting & Abuse Prevention](#9-rate-limiting--abuse-prevention)
10. [HTTPS / TLS Setup](#10-https--tls-setup)
11. [Dependency & Patch Management](#11-dependency--patch-management)
12. [Audit Logging](#12-audit-logging)
13. [Incident Response](#13-incident-response)
14. [Security Checklist](#14-security-checklist)

---

## 1. Threat Model

NexVision runs inside a hotel LAN. The primary attack surfaces are:

| Surface | Attacker | Risk |
|---|---|---|
| Admin panel (`/admin/`) | Rogue guest, insider | Account takeover → full content control |
| Room token system | Guest spoofing another room | Message/package leakage between rooms |
| VOD API key | Leaked credentials | Unauthorized video ingestion or deletion |
| M3U import endpoint | Crafted URLs | SSRF to internal network services |
| File upload | Malicious file | Server-side code execution, disk exhaustion |
| Gunicorn socket | Local process | Privilege escalation if socket perms are wrong |
| Redis | Local process | Cache poisoning, session theft |

---

## 2. Authentication Architecture

### 2.1 Three Auth Tiers

```
┌─────────────────────────────────────────────────────────────┐
│  Tier 1 — Admin JWT                                          │
│  POST /api/auth/login  →  JWT (HS256, 24h expiry)           │
│  Header: Authorization: Bearer <token>                       │
│  Decorator: @admin_required (roles: admin, operator)         │
├─────────────────────────────────────────────────────────────┤
│  Tier 2 — Room Token                                         │
│  POST /api/rooms/register  →  UUID v4 token (permanent)     │
│  Header: X-Room-Token: <uuid>                               │
│  Decorator: token_required (low-privilege, room-scoped)      │
├─────────────────────────────────────────────────────────────┤
│  Tier 3 — VOD API Key                                        │
│  Static key from .env VOD_API_KEY                            │
│  Header: X-API-Key: <key>  or  ?api_key=<key>               │
│  Decorator: @require_api_key                                 │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 JWT Configuration

The JWT secret is read from `SECRET_KEY` in `.env`. The default fallback in
`app/config.py` is a hardcoded string — **this must be overridden in production**.

```bash
# Generate a strong secret
python3 -c "import secrets; print(secrets.token_hex(32))"
# Example output: 3f8a2b9c1d4e7f0a5b8c2d6e9f3a1b4c7d0e2f5a8b1c4d7e0f3a6b9c2d5e8f1a
```

Add to `.env`:
```ini
SECRET_KEY=<output from above>
```

JWT tokens are signed HS256 and expire in 24 hours. There is no refresh token
mechanism — re-login is required after expiry.

### 2.3 Room Token Security

Room tokens are UUIDs stored in the `rooms` table. A guest can only discover
their own token (shown on the registration screen). Tokens:

- Are per-room, not per-session (persistent until regenerated)
- Are validated on every request via `X-Room-Token` header lookup in DB
- Control access to: packages, VIP channels/VOD, message read/dismiss state

To rotate a room's token (e.g., after checkout):

```bash
# Via admin panel: Rooms → Edit → Regenerate Token
# Via API:
curl -X POST /api/rooms/<rid>/token \
  -H "Authorization: Bearer <admin_jwt>"
```

### 2.4 Hardening Recommendations

- **Change the default admin password immediately** after first install
- **Create operator accounts** for staff who don't need destructive access
- **Never share the JWT** — it grants full content management
- **Set JWT expiry to 8h** for hotel staff shifts (requires code change in `auth_service.py`)
- **Rotate VOD API key** quarterly or after any suspected exposure

---

## 3. Secrets Management

### 3.1 Required Secrets in .env

```ini
# Flask JWT signing key — MUST be unique per deployment
SECRET_KEY=<32+ hex chars from secrets.token_hex(32)>

# VOD service API key — protects upload/delete endpoints
VOD_API_KEY=<16+ hex chars from secrets.token_hex(16)>

# MySQL credentials (if USE_MYSQL=1)
MYSQL_HOST=localhost
MYSQL_USER=nexvision
MYSQL_PASSWORD=<strong random password>
MYSQL_DB=nexvision
MYSQL_VOD_DB=nexvision_vod
```

### 3.2 File Permissions

```bash
# Secrets file — owner read/write only
chmod 600 /opt/nexvision/.env
chown nexvision:nexvision /opt/nexvision/.env

# Application code — owner read/write, group read
chmod 640 /opt/nexvision/app/*.py
chown nexvision:www-data /opt/nexvision/app/*.py

# Database (SQLite dev mode)
chmod 660 /opt/nexvision/nexvision.db
chown nexvision:www-data /opt/nexvision/nexvision.db

# Upload directory
chmod 750 /opt/nexvision/uploads/
chown nexvision:www-data /opt/nexvision/uploads/
```

### 3.3 Audit for Committed Secrets

```bash
# Check git history for secrets
git log --all --oneline | head -20
git log --all -- .env  # .env should never appear

# Scan for common patterns in commits
git log -p | grep -E "(SECRET|PASSWORD|API_KEY|TOKEN)" | head -20
```

### 3.4 Emergency Key Rotation

If a secret is compromised:

```bash
# 1. Generate new secrets
NEW_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
NEW_VOD_KEY=$(python3 -c "import secrets; print(secrets.token_hex(16))")

# 2. Update .env
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$NEW_SECRET/" /opt/nexvision/.env
sed -i "s/^VOD_API_KEY=.*/VOD_API_KEY=$NEW_VOD_KEY/" /opt/nexvision/.env

# 3. Restart — invalidates all existing JWT tokens (all admins must re-login)
sudo systemctl restart nexvision

# 4. If MySQL password was leaked, rotate it too:
# mysql -u root -e "ALTER USER 'nexvision'@'localhost' IDENTIFIED BY 'new_password';"
# Then update MYSQL_PASSWORD in .env and restart
```

---

## 4. File & OS Permissions

### 4.1 Service User Isolation

Run Gunicorn as a dedicated non-root user:

```bash
# Create user (no login shell, no home dir)
sudo useradd --system --no-create-home --shell /usr/sbin/nologin nexvision

# Verify
id nexvision  # uid=998(nexvision) gid=998(nexvision)
```

The systemd unit (`nexvision.service`) should set:
```ini
[Service]
User=nexvision
Group=www-data
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/opt/nexvision/uploads /opt/nexvision/vod /var/log/nexvision /run/nexvision
```

### 4.2 Directory Permissions Matrix

| Path | Owner | Perms | Why |
|---|---|---|---|
| `/opt/nexvision/` | nexvision:nexvision | `755` | Base directory |
| `/opt/nexvision/.env` | nexvision:nexvision | `600` | Secrets file |
| `/opt/nexvision/app/` | nexvision:www-data | `750` | App code |
| `/opt/nexvision/app/*.py` | nexvision:www-data | `640` | Python source |
| `/opt/nexvision/web/` | nexvision:www-data | `755` | Static frontend |
| `/opt/nexvision/uploads/` | nexvision:www-data | `750` | Admin uploads |
| `/opt/nexvision/vod/hls/` | nexvision:www-data | `750` | HLS segments |
| `/opt/nexvision/nexvision.db` | nexvision:www-data | `660` | SQLite |
| `/run/nexvision/` | nexvision:www-data | `755` | Socket dir |
| `/run/nexvision/gunicorn.sock` | nexvision:www-data | `660` | WSGI socket |

### 4.3 Verify Permissions

```bash
# Quick audit script
echo "=== .env ===" && ls -la /opt/nexvision/.env
echo "=== Socket ===" && ls -la /run/nexvision/gunicorn.sock
echo "=== DB ===" && ls -la /opt/nexvision/nexvision.db
echo "=== Uploads ===" && ls -la /opt/nexvision/uploads/ | head -5
```

### 4.4 Upload Directory Hardening

Uploaded files are served directly by Nginx under `/uploads/`. Prevent
server-side execution of uploaded content:

In `/etc/nginx/sites-available/nexvision`:
```nginx
location /uploads/ {
    alias /opt/nexvision/uploads/;
    # Disallow PHP, CGI execution
    location ~* \.(php|cgi|pl|py|sh)$ {
        return 403;
    }
    # Force download for non-image types
    add_header X-Content-Type-Options nosniff;
    expires 7d;
}
```

In `app/services/upload_service.py`, the allowed extension list is enforced:
```python
ALLOWED_IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
```

**Recommendation:** Add magic byte validation on top of extension checks to
prevent disguised executables. Add to `upload_service.py`:

```python
import imghdr

def _validate_image(file_path: str) -> bool:
    kind = imghdr.what(file_path)
    return kind in {'png', 'jpeg', 'gif', 'webp'}
```

---

## 5. Network & Nginx Hardening

### 5.1 Current Nginx Configuration

```nginx
# Key security settings already in nginx/nexvision.conf

# 4GB max body (for large VOD uploads) — tighten for admin API
client_max_body_size 4096m;

# Keepalive to Gunicorn
upstream nexvision_backend {
    server unix:/run/nexvision/gunicorn.sock;
    keepalive 64;
}
```

### 5.2 Recommended Security Headers

Add to the Nginx server block:

```nginx
server {
    # ...existing config...

    # Prevent clickjacking
    add_header X-Frame-Options "SAMEORIGIN" always;

    # Prevent MIME sniffing
    add_header X-Content-Type-Options "nosniff" always;

    # XSS filter (legacy browsers)
    add_header X-XSS-Protection "1; mode=block" always;

    # Referrer policy
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Content Security Policy (adjust src as needed)
    add_header Content-Security-Policy "
        default-src 'self';
        script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://www.gstatic.com;
        style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
        font-src 'self' https://fonts.gstatic.com;
        img-src 'self' data: blob: https:;
        media-src 'self' blob:;
        connect-src 'self';
        frame-ancestors 'none';
    " always;

    # Remove server version from headers
    server_tokens off;
}
```

### 5.3 Restrict Admin Panel to Staff Network

If the admin panel should only be accessible from the hotel management VLAN:

```nginx
location /admin/ {
    # Allow management VLAN only
    allow 192.168.1.0/24;   # Hotel management network
    allow 127.0.0.1;
    deny all;

    alias /opt/nexvision/web/admin/;
    try_files $uri $uri/ /admin/index.html;
}
```

### 5.4 Restrict VOD API Key Endpoints

```nginx
# VOD admin endpoints — restrict to localhost/server only
location ~* ^/vod/api/(upload|import|settings|auth) {
    allow 127.0.0.1;
    deny all;
    proxy_pass http://nexvision_backend;
    # ...headers...
}
```

### 5.5 Rate Limiting

Add rate limit zones to nginx.conf (http block):

```nginx
http {
    # Login endpoint — prevent brute force
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

    # General API
    limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;

    # Registration (room token requests)
    limit_req_zone $binary_remote_addr zone=register:10m rate=10r/m;
}
```

Apply in server block:

```nginx
# Protect login
location = /api/auth/login {
    limit_req zone=login burst=3 nodelay;
    limit_req_status 429;
    proxy_pass http://nexvision_backend;
}

# General API rate limit
location /api/ {
    limit_req zone=api burst=20 nodelay;
    limit_req_status 429;
    proxy_pass http://nexvision_backend;
}

# Room registration
location = /api/rooms/register {
    limit_req zone=register burst=5 nodelay;
    limit_req_status 429;
    proxy_pass http://nexvision_backend;
}
```

### 5.6 Fail2ban Integration

Install and configure Fail2ban to block repeated auth failures:

```bash
sudo apt install fail2ban -y
```

Create `/etc/fail2ban/filter.d/nexvision-auth.conf`:
```ini
[Definition]
failregex = ^<HOST> .* "POST /api/auth/login HTTP.*" 401
ignoreregex =
```

Create `/etc/fail2ban/jail.d/nexvision.conf`:
```ini
[nexvision-auth]
enabled  = true
port     = http,https
filter   = nexvision-auth
logpath  = /var/log/nexvision/access.log
maxretry = 5
findtime = 300
bantime  = 3600
```

```bash
sudo systemctl enable --now fail2ban
sudo fail2ban-client status nexvision-auth
```

---

## 6. Redis Security

### 6.1 Current Usage

Redis is used for hot caching. Cache keys are namespaced with `nv:` prefix.
TTL values (seconds):

| Cache key | TTL | Data |
|---|---|---|
| `nv:settings` | 60 | Hotel settings |
| `nv:channels` | 30 | Channel list |
| `nv:vod` | 60 | VOD catalogue |
| `nv:nav` | 120 | Navigation items |
| `nv:slides` | 60 | Promo slides |
| `nv:rss` | 300 | RSS feed items |
| `nv:weather` | 600 | Weather data |

### 6.2 Hardening Redis

By default Redis binds to all interfaces. Restrict it to localhost:

```bash
# /etc/redis/redis.conf
bind 127.0.0.1 ::1
protected-mode yes

# Require a password
requirepass <generate with: openssl rand -hex 32>

# Disable dangerous commands
rename-command FLUSHALL ""
rename-command FLUSHDB ""
rename-command CONFIG ""
rename-command DEBUG ""
rename-command KEYS ""
```

Update `.env` if you add a Redis password:
```ini
REDIS_URL=redis://:your_redis_password@localhost:6379/0
```

### 6.3 Cache Poisoning Mitigation

All cache keys are deterministic and invalidated on write operations. The
invalidation functions in `app/extensions.py` (`invalidate_settings()`,
`invalidate_channels()`, etc.) are called in every service that modifies data.

**Verify cache invalidation is called** whenever you add new write endpoints.

---

## 7. Database Security

### 7.1 SQLite (Development)

SQLite has no network exposure. Key risks: file permissions and SQLite WAL
files (`*.db-shm`, `*.db-wal`) being left world-readable.

```bash
chmod 660 /opt/nexvision/nexvision.db
chmod 660 /opt/nexvision/nexvision.db-shm
chmod 660 /opt/nexvision/nexvision.db-wal
```

### 7.2 MySQL (Production)

```sql
-- Create dedicated user with minimal privileges
CREATE USER 'nexvision'@'localhost' IDENTIFIED BY '<strong_password>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX ON nexvision.* TO 'nexvision'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, INDEX ON nexvision_vod.* TO 'nexvision'@'localhost';
FLUSH PRIVILEGES;

-- Verify no global privileges
SHOW GRANTS FOR 'nexvision'@'localhost';
-- Should NOT show SUPER, FILE, PROCESS, GRANT OPTION
```

Remove anonymous users and test database:
```sql
DELETE FROM mysql.user WHERE User='';
DROP DATABASE IF EXISTS test;
FLUSH PRIVILEGES;
```

### 7.3 SQL Injection Prevention

All database queries in the service layer use parameterized statements:

```python
# Correct — parameterized
conn.execute("SELECT * FROM channels WHERE id=?", (cid,))

# Wrong — string interpolation (never do this)
conn.execute(f"SELECT * FROM channels WHERE id={cid}")
```

The MySQL compatibility layer (`db/db_mysql.py`) translates `?` to `%s`
automatically — **do not use `%s` in SQLite-style code**, use `?` everywhere.

---

## 8. Input Validation & Injection Prevention

### 8.1 Current Validation Points

| Input | Validation |
|---|---|
| File uploads | Extension whitelist (`ALLOWED_IMAGE_EXTS`) |
| Channel stream_url | No validation — see recommendation below |
| M3U import URL | Fetched by server — SSRF risk |
| Prayer times lat/lon | Passed to external API — numeric check recommended |
| RSS feed URL | Fetched server-side — SSRF risk |
| VOD import URL | Fetched server-side — SSRF risk |

### 8.2 SSRF Mitigations

Three endpoints fetch remote URLs server-side:
- `POST /api/channels/import-m3u` (M3U URL)
- `POST /api/rss` (RSS feed URL)
- `POST /vod/api/import` (video URL)

**Recommended validation** (add to each service before `requests.get()`):

```python
from urllib.parse import urlparse
import ipaddress

BLOCKED_NETS = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'),
]

def _safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False
    try:
        import socket
        ip = ipaddress.ip_address(socket.gethostbyname(parsed.hostname))
        return not any(ip in net for net in BLOCKED_NETS)
    except Exception:
        return False
```

### 8.3 XSS Prevention

Admin panel output uses the `esc()` helper for all user-supplied strings:
```javascript
function esc(s){
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
```

All dynamic content in the TV client must pass through `esc()`. Never use
`innerHTML` with unescaped API data.

### 8.4 Content-Type Enforcement

Nginx sets `X-Content-Type-Options: nosniff` and each Nginx location explicitly
sets `Content-Type` for static files. API responses from Flask always return
`application/json`.

---

## 9. Rate Limiting & Abuse Prevention

### 9.1 Nginx Rate Limiting (see Section 5.5)

Already covered. Apply `limit_req` on `/api/auth/login` and `/api/rooms/register`.

### 9.2 Large Request Limits

The 4GB `client_max_body_size` applies globally for VOD uploads. Tighten for
non-VOD API routes:

```nginx
# Default: 10MB for API endpoints
location /api/ {
    client_max_body_size 10m;
    proxy_pass http://nexvision_backend;
}

# VOD upload: 4GB
location /vod/api/upload {
    client_max_body_size 4096m;
    proxy_pass http://nexvision_backend;
}
```

### 9.3 Gunicorn Worker Limits

`app/gunicorn.conf.py` already sets `max_requests = 5000` per worker to prevent
memory leaks from unbounded request accumulation. The `timeout = 120` prevents
slow-loris attacks from tying up workers.

---

## 10. HTTPS / TLS Setup

### 10.1 Let's Encrypt (Recommended)

Requires a public domain name pointing to the server:

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-hotel-domain.com

# Auto-renewal (already set up by certbot)
sudo systemctl status certbot.timer
```

### 10.2 Self-Signed Certificate (LAN Only)

For hotel LAN deployments without a public domain:

```bash
# Generate a 10-year self-signed cert
sudo openssl req -x509 -nodes -days 3650 \
    -newkey rsa:4096 \
    -keyout /etc/ssl/nexvision/privkey.pem \
    -out /etc/ssl/nexvision/fullchain.pem \
    -subj "/CN=nexvision.hotel.local" \
    -addext "subjectAltName=IP:192.168.1.100,DNS:nexvision.hotel.local"

chmod 600 /etc/ssl/nexvision/privkey.pem
```

### 10.3 Nginx SSL Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Modern TLS only
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # HSTS — only add once HTTPS is confirmed working
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

    # OCSP stapling (Let's Encrypt only)
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 1.1.1.1 valid=300s;

    # ...rest of config...
}

# HTTP → HTTPS redirect
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$host$request_uri;
}
```

---

## 11. Dependency & Patch Management

### 11.1 Current Dependencies

All production dependencies are pinned in `requirements_prod.txt`. Review for
known vulnerabilities monthly:

```bash
# Activate venv
source /opt/nexvision/venv/bin/activate

# Audit with pip-audit
pip install pip-audit
pip-audit -r requirements_prod.txt

# Or with safety
pip install safety
safety check -r requirements_prod.txt
```

### 11.2 Updating Dependencies

```bash
# Check what's outdated
pip list --outdated

# Update a specific package (test in dev first)
pip install --upgrade Flask==3.x.x

# After testing, pin the new version in requirements_prod.txt
```

### 11.3 System Packages

```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# Check for security updates only
sudo apt list --upgradable 2>/dev/null | grep -i security
```

---

## 12. Audit Logging

### 12.1 Current Nginx Access Logs

```
/var/log/nexvision/access.log — all HTTP requests
/var/log/nexvision/error.log  — Nginx + Gunicorn errors
```

Useful queries:
```bash
# Failed login attempts (401 on auth endpoint)
grep '"POST /api/auth/login' /var/log/nexvision/access.log | grep ' 401 '

# Admin panel access
grep '/admin/' /var/log/nexvision/access.log | awk '{print $1, $7}' | sort | uniq -c | sort -rn | head

# VOD upload events
grep '"POST /vod/api/upload' /var/log/nexvision/access.log

# 5xx errors (server-side failures)
grep ' 5[0-9][0-9] ' /var/log/nexvision/access.log | tail -50
```

### 12.2 Recommended: Application-Level Audit Log

Add to `app/hooks.py` to log admin write operations:

```python
import logging

audit_log = logging.getLogger('nexvision.audit')
handler = logging.FileHandler('/var/log/nexvision/audit.log')
handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
audit_log.addHandler(handler)
audit_log.setLevel(logging.INFO)

def log_admin_action(user, method, path, body_summary=''):
    audit_log.info(f"ADMIN user={user} {method} {path} {body_summary}")
```

Call from `@admin_required` decorated endpoints on POST/PUT/DELETE requests.

### 12.3 Log Rotation

```bash
# /etc/logrotate.d/nexvision
/var/log/nexvision/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    postrotate
        nginx -s reopen
    endscript
}
```

---

## 13. Incident Response

### 13.1 Suspected Account Compromise

```bash
# 1. Immediately rotate SECRET_KEY (invalidates all JWTs)
NEW_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$NEW_KEY/" /opt/nexvision/.env
sudo systemctl restart nexvision

# 2. Review recent admin actions in access log
grep '/api/' /var/log/nexvision/access.log | grep -v '"GET' | \
  awk '{print $1, $4, $6, $7, $9}' | sort | tail -100

# 3. Change the admin password via DB
python3 -c "
import bcrypt
pw = b'new_strong_password'
hashed = bcrypt.hashpw(pw, bcrypt.gensalt()).decode()
print(f'UPDATE users SET password=\"{hashed}\" WHERE username=\"admin\";')
"
# Then run in sqlite3 /opt/nexvision/nexvision.db
```

### 13.2 Suspected Data Breach

```bash
# Check what was accessed recently
grep '200\|201' /var/log/nexvision/access.log | \
  grep -E '(channels|vod|rooms|messages|users)' | \
  awk '{print $1, $7}' | tail -200

# Look for bulk data exports
grep '"GET /api/channels' /var/log/nexvision/access.log | grep ' 200 '
grep '"GET /api/rooms' /var/log/nexvision/access.log | grep ' 200 '
```

### 13.3 Service Recovery Checklist

1. `sudo systemctl status nexvision nginx redis mysql`
2. `curl -s http://localhost/api/settings | python3 -m json.tool`
3. `sqlite3 nexvision.db "SELECT COUNT(*) FROM channels;"`
4. `redis-cli PING`
5. Check logs: `sudo journalctl -u nexvision -n 50`

---

## 14. Security Checklist

Run before every production deployment:

### Secrets
- [ ] `SECRET_KEY` is unique, 64+ hex chars, not the default
- [ ] `VOD_API_KEY` is unique, not the default `nexvision-vod-key-2024`
- [ ] `MYSQL_PASSWORD` is strong and not reused from dev
- [ ] `.env` permissions are `600`, owned by `nexvision`
- [ ] `.env` is in `.gitignore` and never appears in `git log -- .env`

### Authentication
- [ ] Default `admin` password has been changed
- [ ] Operator accounts exist for staff (not sharing the admin credential)
- [ ] Room tokens have been rotated for all checked-out rooms

### Network
- [ ] Admin panel restricted to management VLAN (or at least behind VPN)
- [ ] Rate limiting applied to login and registration endpoints
- [ ] Fail2ban monitoring the access log
- [ ] HTTPS enabled with a valid certificate (or self-signed for LAN)

### Permissions
- [ ] Gunicorn runs as `nexvision` (non-root)
- [ ] Socket `/run/nexvision/gunicorn.sock` perms are `660`
- [ ] Upload directory does not serve executable files
- [ ] Nginx has `server_tokens off`

### Dependencies
- [ ] `pip-audit` shows no critical CVEs
- [ ] System packages are up to date (`apt upgrade`)
- [ ] Node.js EPG service using a non-root PM2 user

### Database
- [ ] MySQL user has no `SUPER` or `FILE` privileges
- [ ] Anonymous MySQL users removed
- [ ] SQLite WAL files not world-readable

### Logging
- [ ] Access logs retained for 30 days
- [ ] Log rotation configured
- [ ] Error log monitored (or alerting configured)

---

*NexVision IPTV Security Hardening Guide — v8.21*  
*Maintainer: dalsuum — Report vulnerabilities privately to dalsuum08@gmail.com*
