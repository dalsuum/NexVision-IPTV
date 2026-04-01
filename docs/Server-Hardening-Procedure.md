# NexVision IPTV — Server Hardening Procedure
**Document Type:** Security Hardening Procedure
**Version:** 1.0
**System:** NexVision IPTV Platform v8.9
**Target OS:** Ubuntu 22.04 LTS
**Classification:** Internal — IT Security

---

> ⚠️ **IMPORTANT:** Apply hardening BEFORE going live. Test each step in a staging environment first. Some changes (SSH port, firewall) can lock you out if misconfigured — always maintain a secondary console/KVM access.

---

## 1. OPERATING SYSTEM HARDENING

### 1.1 Keep System Updated
```bash
sudo apt update && sudo apt upgrade -y

# Enable automatic security updates
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
# Select YES to automatic updates

# Configure to auto-apply security patches only
sudo nano /etc/apt/apt.conf.d/50unattended-upgrades
# Ensure this line is uncommented:
# "${distro_id}:${distro_codename}-security";
```

### 1.2 Remove Unnecessary Packages
```bash
sudo apt autoremove -y
sudo apt purge -y telnet rsh-client rsh-redone-client
sudo systemctl disable --now avahi-daemon cups bluetooth 2>/dev/null || true
```

### 1.3 Disable Core Dumps
```bash
echo "* hard core 0" | sudo tee -a /etc/security/limits.conf
echo "fs.suid_dumpable = 0" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 1.4 Kernel Security Parameters
```bash
sudo nano /etc/sysctl.d/99-nexvision-security.conf
```

```ini
# Prevent IP spoofing
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1

# Disable IP forwarding (not a router)
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0

# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Disable source routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0

# Log suspicious packets
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# Protect against SYN flood attacks
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2

# Ignore ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0

# Disable IPv6 if not needed
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
```

```bash
sudo sysctl --system
```

---

## 2. USER AND ACCESS HARDENING

### 2.1 SSH Key-Based Authentication Only
```bash
# On your LOCAL machine — generate SSH key pair
ssh-keygen -t ed25519 -C "nexvision-admin" -f ~/.ssh/nexvision_admin

# Copy public key to server
ssh-copy-id -i ~/.ssh/nexvision_admin.pub admin@SERVER_IP

# Test key login before disabling password auth
ssh -i ~/.ssh/nexvision_admin admin@SERVER_IP
```

### 2.2 Harden SSH Configuration
```bash
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup
sudo nano /etc/ssh/sshd_config
```

```ini
# Change default SSH port (choose 1024–65535, e.g., 2222)
Port 2222

# Disable root login
PermitRootLogin no

# Disable password authentication (keys only)
PasswordAuthentication no
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys

# Disable empty passwords
PermitEmptyPasswords no

# Limit auth attempts
MaxAuthTries 3
MaxSessions 5

# Disable less-secure auth methods
ChallengeResponseAuthentication no
UsePAM yes
X11Forwarding no
AllowTcpForwarding no
GatewayPorts no
PermitTunnel no

# Allowed users only (replace 'admin' with your username)
AllowUsers admin

# Login grace time
LoginGraceTime 30

# Idle timeout: disconnect after 15 minutes idle
ClientAliveInterval 900
ClientAliveCountMax 0

# Log level
LogLevel VERBOSE
```

```bash
# Validate config before restarting
sudo sshd -t

# Restart SSH (keep current session open!)
sudo systemctl restart sshd

# Open new terminal and test new port BEFORE closing current session
ssh -i ~/.ssh/nexvision_admin -p 2222 admin@SERVER_IP
```

### 2.3 Sudo Configuration
```bash
# Only specific users should have sudo access
sudo visudo
```

```
# /etc/sudoers — add at the bottom
admin ALL=(ALL) ALL

# nexvision app user — NO sudo
Defaults        !visiblepw
```

### 2.4 Password Policy
```bash
sudo apt install -y libpam-pwquality

sudo nano /etc/security/pwquality.conf
```

```ini
minlen = 14
minclass = 4
maxrepeat = 2
dcredit = -1
ucredit = -1
lcredit = -1
ocredit = -1
```

```bash
# Account lockout after failed logins
sudo nano /etc/pam.d/common-auth
# Add at top:
# auth required pam_tally2.so onerr=fail audit silent deny=5 unlock_time=900
```

---

## 3. FIREWALL CONFIGURATION

### 3.1 UFW (Uncomplicated Firewall)
```bash
# Reset to defaults
sudo ufw reset

# Default policies — deny all incoming, allow all outgoing
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH on custom port (change 2222 to your port)
sudo ufw allow 2222/tcp comment 'SSH'

# Allow HTTP/HTTPS for hotel guests
sudo ufw allow 80/tcp comment 'HTTP - Hotel guests'
sudo ufw allow 443/tcp comment 'HTTPS - Hotel guests'

# Block internal services from external access
sudo ufw deny 3306/tcp comment 'Block MySQL external'
sudo ufw deny 6379/tcp comment 'Block Redis external'
sudo ufw deny 5000/tcp comment 'Block Flask dev port'

# Rate limit SSH (max 6 connections per 30 seconds per IP)
sudo ufw limit 2222/tcp

# Enable firewall
sudo ufw enable
sudo ufw status verbose
```

### 3.2 Restrict Admin Panel Access (Optional but Recommended)
If admin panel should only be accessible from staff network:
```bash
# Allow admin panel only from staff IP range
sudo ufw allow from 192.168.1.0/24 to any port 80 comment 'Admin - Staff LAN only'

# Or allow admin from specific management IP
sudo ufw allow from 192.168.1.100 to any port 80 comment 'Admin - IT workstation'
```

Alternatively, add IP restriction in Nginx for the `/admin/` location:
```nginx
location /admin/ {
    allow 192.168.1.0/24;   # Staff network
    allow 127.0.0.1;
    deny all;
    ...
}
```

---

## 4. NGINX SECURITY HARDENING

### 4.1 Hide Nginx Version
```bash
sudo nano /etc/nginx/nginx.conf
```
Add inside `http { }` block:
```nginx
server_tokens off;
```

### 4.2 Security Headers
Add to the Nginx server block in `nexvision.conf`:
```nginx
# Security headers
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

# Prevent clickjacking on admin panel
location /admin/ {
    add_header X-Frame-Options "DENY" always;
    ...
}
```

### 4.3 Rate Limiting (Prevent Abuse)
Add to `nginx.conf` inside `http { }` block:
```nginx
# Limit API requests
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;

# Limit connection count per IP
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;
limit_conn conn_limit 20;
```

Add to `nexvision.conf` locations:
```nginx
location /api/ {
    limit_req zone=api_limit burst=60 nodelay;
    ...
}

location /api/login {
    limit_req zone=login_limit burst=5 nodelay;
    ...
}
```

### 4.4 Block Malicious Requests
```nginx
# Block common attack patterns
location ~* \.(php|asp|aspx|jsp|cgi)$ {
    deny all;
    return 404;
}

# Block access to hidden files
location ~ /\. {
    deny all;
    return 404;
}

# Block access to Python source files
location ~* \.(py|pyc|pyo|db|sqlite|env|conf|cfg|ini|log|sh)$ {
    deny all;
    return 404;
}
```

### 4.5 Client Body Size Limit
```nginx
# Limit upload size (adjust to match your video upload requirement)
client_max_body_size 2G;
client_body_timeout 300s;
```

---

## 5. MYSQL HARDENING

### 5.1 Restrict MySQL User Permissions
```sql
-- Remove global privileges, grant only what's needed
sudo mysql -u root -p

-- Verify nexvision user only has access to its own databases
SHOW GRANTS FOR 'nexvision'@'localhost';

-- If any global grants exist, revoke them
REVOKE ALL PRIVILEGES ON *.* FROM 'nexvision'@'localhost';
GRANT ALL PRIVILEGES ON nexvision.* TO 'nexvision'@'localhost';
GRANT ALL PRIVILEGES ON nexvision_vod.* TO 'nexvision'@'localhost';
FLUSH PRIVILEGES;

-- Remove anonymous users
DELETE FROM mysql.user WHERE User='';

-- Remove remote root access
DELETE FROM mysql.user WHERE User='root' AND Host NOT IN ('localhost', '127.0.0.1', '::1');

FLUSH PRIVILEGES;
EXIT;
```

### 5.2 MySQL Network Binding
```bash
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf
```
```ini
# Bind MySQL to localhost only
bind-address = 127.0.0.1
mysqlx-bind-address = 127.0.0.1
```
```bash
sudo systemctl restart mysql
```

### 5.3 MySQL SSL (Optional)
```bash
sudo mysql_ssl_rsa_setup --uid=mysql
# Then add to nexvision user:
# ALTER USER 'nexvision'@'localhost' REQUIRE SSL;
```

### 5.4 Enable MySQL Audit Logging
```bash
sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf
```
```ini
# Audit log
general_log = 0          # Keep off unless debugging (performance impact)
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow.log
long_query_time = 2
```

---

## 6. REDIS HARDENING

### 6.1 Bind Redis to Localhost
```bash
sudo nano /etc/redis/redis.conf
```
```ini
# Bind to localhost only
bind 127.0.0.1 -::1

# Disable protected mode (already bound to localhost)
protected-mode yes

# Set a strong password
requirepass REDIS_STRONG_PASSWORD_HERE

# Disable dangerous commands
rename-command FLUSHALL ""
rename-command FLUSHDB ""
rename-command CONFIG "CONFIG_NEXVISION_ONLY"
rename-command DEBUG ""
rename-command EVAL ""

# Memory limit
maxmemory 512mb
maxmemory-policy allkeys-lru
```

```bash
sudo systemctl restart redis-server

# Update .env to include Redis password
# REDIS_URL=redis://:REDIS_STRONG_PASSWORD_HERE@localhost:6379/0
```

---

## 7. APPLICATION SECURITY

### 7.1 File Permissions
```bash
# Application files — read-only for app user
sudo find /opt/nexvision -type f -exec chmod 640 {} \;
sudo find /opt/nexvision -type d -exec chmod 750 {} \;

# Writable directories (app needs to write)
sudo chmod 770 /opt/nexvision/videos
sudo chmod 770 /opt/nexvision/hls
sudo chmod 770 /opt/nexvision/uploads
sudo chmod 770 /opt/nexvision/thumbnails
sudo chmod 770 /opt/nexvision/logs 2>/dev/null || true

# Protect .env file (most critical — contains passwords)
sudo chmod 600 /opt/nexvision/.env
sudo chown nexvision:nexvision /opt/nexvision/.env

# Python source — no execute for others
sudo chmod 640 /opt/nexvision/app.py
sudo chmod 640 /opt/nexvision/db_mysql.py
sudo chmod 640 /opt/nexvision/cache_setup.py
```

### 7.2 Validate Secret Key
```bash
# Generate a strong Flask secret key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Update in .env:
# SECRET_KEY=the_output_from_above
```

### 7.3 API Key Rotation
The admin API uses a key stored in the settings table. Rotate it after deployment:
1. Log in to admin panel → Settings
2. Change admin PIN to a strong value (min 8 chars, not `1234`)
3. Communicate new PIN securely to authorised staff

### 7.4 Content Security Policy for Admin Panel
If admin panel has XSS vulnerability exposure, consider adding to Nginx:
```nginx
location /admin/ {
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; style-src 'self' 'unsafe-inline';" always;
}
```

---

## 8. LOGGING AND MONITORING

### 8.1 Centralised Log Rotation
```bash
sudo nano /etc/logrotate.d/nexvision
```
```ini
/var/log/nexvision/*.log
/var/log/nginx/nexvision_*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 640 www-data adm
    sharedscripts
    postrotate
        nginx -s reopen 2>/dev/null || true
        systemctl kill -s USR1 nexvision 2>/dev/null || true
    endscript
}
```

### 8.2 Fail2ban — Brute Force Protection
```bash
sudo apt install -y fail2ban

sudo nano /etc/fail2ban/jail.d/nexvision.conf
```
```ini
[DEFAULT]
bantime  = 3600      # 1 hour ban
findtime = 600       # 10 minute window
maxretry = 5         # 5 failures before ban

[sshd]
enabled = true
port    = 2222       # Must match your SSH port
filter  = sshd
logpath = /var/log/auth.log

[nginx-http-auth]
enabled  = true
filter   = nginx-http-auth
port     = http,https
logpath  = /var/log/nginx/nexvision_error.log

[nginx-limit-req]
enabled  = true
filter   = nginx-limit-req
port     = http,https
logpath  = /var/log/nginx/nexvision_error.log
findtime = 600
bantime  = 7200
maxretry = 10

[nginx-botsearch]
enabled  = true
port     = http,https
filter   = nginx-botsearch
logpath  = /var/log/nginx/nexvision_access.log
maxretry = 2
```
```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
sudo fail2ban-client status
```

### 8.3 Audit Logging
```bash
sudo apt install -y auditd audispd-plugins

# Log file access to sensitive files
sudo auditctl -w /opt/nexvision/.env -p rwa -k nexvision_env
sudo auditctl -w /etc/nginx/sites-available/nexvision -p rwa -k nexvision_nginx
sudo auditctl -w /etc/systemd/system/nexvision.service -p rwa -k nexvision_svc

sudo systemctl enable auditd
sudo systemctl restart auditd
```

---

## 9. BACKUP SECURITY

### 9.1 Encrypt Backups
```bash
# Install encryption tool
sudo apt install -y gnupg

# Generate backup encryption key
gpg --gen-key
# Note the key ID

# Encrypt backup script output
# In backup.sh, add after creating the archive:
# gpg --encrypt --recipient backup@hotel.com /backup/nexvision_$DATE.sql
```

### 9.2 Off-Site Backup
```bash
# Example: sync to encrypted remote storage daily
# Configure credentials in /root/.rclone.conf first
# rclone sync /backup remote:nexvision-backups --transfers=4
```

### 9.3 Backup File Permissions
```bash
sudo chown -R root:root /backup
sudo chmod 700 /backup
sudo chmod 600 /backup/*.sql
sudo chmod 600 /backup/*.tar.gz
```

---

## 10. SSL/TLS HARDENING

### 10.1 Modern TLS Configuration
```bash
sudo nano /etc/nginx/sites-available/nexvision
```
Add to the HTTPS server block:
```nginx
# Modern TLS only
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
ssl_prefer_server_ciphers off;

# OCSP Stapling
ssl_stapling on;
ssl_stapling_verify on;
resolver 8.8.8.8 8.8.4.4 valid=300s;
resolver_timeout 5s;

# HSTS (only after confirming HTTPS works perfectly)
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

# Session settings
ssl_session_cache shared:SSL:10m;
ssl_session_timeout 1d;
ssl_session_tickets off;

# DH params
ssl_dhparam /etc/nginx/dhparam.pem;
```
```bash
# Generate strong DH parameters (takes 2-5 minutes)
sudo openssl dhparam -out /etc/nginx/dhparam.pem 2048
```

---

## 11. HARDENING VERIFICATION

### 11.1 Security Scan Checklist
```bash
# 1. Open ports (should only show 22/2222, 80, 443)
sudo ss -tlnp

# 2. Running services (minimise attack surface)
sudo systemctl list-units --type=service --state=running

# 3. SUID files (investigate any unusual entries)
sudo find / -perm /4000 -type f 2>/dev/null

# 4. World-writable files (should be minimal)
sudo find /opt/nexvision -perm -002 -type f 2>/dev/null

# 5. Check .env is not world-readable
ls -la /opt/nexvision/.env
# Expected: -rw------- 1 nexvision nexvision

# 6. Verify fail2ban active
sudo fail2ban-client status

# 7. Check UFW rules
sudo ufw status verbose

# 8. Verify MySQL not listening externally
sudo ss -tlnp | grep 3306
# Expected: only 127.0.0.1:3306

# 9. Verify Redis not listening externally
sudo ss -tlnp | grep 6379
# Expected: only 127.0.0.1:6379

# 10. SSH login test with key (should succeed)
ssh -i ~/.ssh/nexvision_admin -p 2222 admin@SERVER_IP echo "SSH OK"
```

### 11.2 External Security Test
```bash
# Run from a DIFFERENT machine (not the server itself)
# Basic port scan
nmap -sS -sV -p 1-65535 SERVER_IP

# Expected open ports: 2222 (SSH), 80 (HTTP), 443 (HTTPS only)
# All other ports should show filtered/closed

# HTTP security headers check
curl -I http://SERVER_IP/
# Should see: X-Frame-Options, X-Content-Type-Options, etc.
```

---

## 12. REGULAR MAINTENANCE SCHEDULE

| Task | Frequency | Who |
|---|---|---|
| OS security updates | Weekly (automated) | System |
| Review fail2ban bans | Weekly | IT Admin |
| Review Nginx error logs | Weekly | IT Admin |
| Rotate admin panel PIN | Monthly | IT Manager |
| Review user access list | Monthly | IT Manager |
| Test backup restore | Monthly | IT Admin |
| SSL certificate check | Monthly (auto-renews) | System |
| Full security audit | Quarterly | IT Manager |
| Password rotation (MySQL, Redis) | Quarterly | IT Admin |
| Review firewall rules | Quarterly | IT Manager |
| Penetration test | Annually | External vendor |

---

## 13. INCIDENT — SECURITY BREACH RESPONSE

```
1. ISOLATE — Disconnect server from hotel network immediately
   sudo ufw deny incoming  OR  ip link set eth0 down

2. PRESERVE — Take memory dump and disk snapshot before investigating
   sudo dd if=/dev/sda of=/backup/forensic_image.img bs=4M

3. IDENTIFY — Check auth logs for unauthorized access
   sudo grep "Failed password\|Accepted\|Invalid user" /var/log/auth.log | tail -100
   sudo last | head -30
   sudo journalctl -u nexvision --since "2 hours ago"

4. CONTAIN — Change all credentials
   - MySQL nexvision password
   - Redis requirepass
   - Flask SECRET_KEY
   - Admin panel PIN
   - SSH authorized keys (revoke all, re-add only verified keys)

5. RECOVER — Restore from last known clean backup
   - Verify backup integrity before restoring
   - Restore database from backup preceding compromise

6. REPORT — Document incident
   - Timeline of events
   - Data potentially exposed
   - Actions taken
   - Notify hotel management and legal if guest data affected
```

---

*Security hardening procedure version 1.0 — NexVision IPTV v8.9 — Last updated: 2026-03-20*
*Review this document after any major OS or application update.*
