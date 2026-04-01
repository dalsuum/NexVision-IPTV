# NexVision IPTV — System Operations Book (SOB)
**Document Type**: System Operations Book
**Version**: 2.0 (Updated March 2026)
**System**: NexVision IPTV Platform v8.9
**Classification**: Internal — IT Operations

---

## 1. SYSTEM OVERVIEW

### 1.1 Purpose
NexVision IPTV is a hotel-grade Internet Protocol Television platform delivering live TV channels, Video on Demand (VOD), radio, messaging, RSS ticker, and guest information services to hotel rooms, lobby TVs, and guest mobile devices.

### 1.2 Business Impact
| Category | Detail |
|---|---|
| **Criticality** | High — Guest-facing service |
| **Availability Target** | 99.5% uptime (≤ 3.6 hrs downtime/month) |
| **Users** | Hotel guests (TV/phone/tablet) + Staff (admin panel) |
| **Peak Load** | Up to 500 concurrent streaming sessions |

### 1.3 System Architecture (Current)

#### Core Components
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   TV Clients    │────│      Nginx       │────│   Flask App     │
│   (199KB HTML5) │    │  (Reverse Proxy) │    │   (8,895 lines) │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │                        │
                       ┌──────────────────┐    ┌─────────────────┐
                       │   Static Files   │    │  SQLite Database│
                       │  (HLS, VOD, etc) │    │    (4.9MB+)     │
                       └──────────────────┘    └─────────────────┘
                                │
                       ┌──────────────────┐
                       │ Multi-Storage    │
                       │ (Local/NAS/S3/   │
                       │ Azure/GCS)       │
                       └──────────────────┘
```

#### Current Scale
- **Channels**: 11,427+ live TV channels
- **Rooms**: 20 registered hotel rooms
- **Packages**: Content packages with bulk assignment capability
- **VOD Storage**: Multi-backend support (5 storage types)
- **EPG Coverage**: Auto-sync with live programme data

---

## 2. SERVICE INVENTORY

### 2.1 Core Services

| Service | Port | Protocol | Status Check | Purpose |
|---------|------|----------|--------------|---------|
| **Nginx** | 80/443 | HTTP/HTTPS | `curl -I http://localhost` | Reverse proxy & static files |
| **Flask/Gunicorn** | 5000 | HTTP | `curl http://localhost:5000/api/health` | Main application |
| **MySQL/MariaDB** | 3306 | TCP | `mysqladmin ping` | Database (if used) |

### 2.2 Application Services

| Component | Location | Purpose | Health Check |
|-----------|----------|---------|--------------|
| **TV Client** | `/opt/nexvision/tv/index.html` | Guest interface | Load in browser |
| **Admin Panel** | `/opt/nexvision/admin/index.html` | Management UI | Admin login test |
| **Multi-Storage Admin** | `/storage/` URL path | Storage management | Storage API test |

---

## 3. MONITORING & HEALTH CHECKS

### 3.1 System Health Endpoints

```bash
# Basic health check
curl -s http://localhost/api/health

# Channel count check
curl -s http://localhost/api/channels?limit=1&envelope=1 | jq '.total'

# Storage health check
curl -s http://localhost/storage/health

# Admin authentication check
curl -s http://localhost/admin
```

### 3.2 Key Performance Indicators

| Metric | Normal Range | Warning | Critical | Check Method |
|--------|--------------|---------|----------|--------------|
| **Response Time** | < 200ms | 200-500ms | > 500ms | `curl -w "%{time_total}"` |
| **Channel Load Time** | < 2s | 2-5s | > 5s | Browser dev tools |
| **Concurrent Streams** | < 300 | 300-450 | > 450 | Nginx logs analysis |
| **Database Size** | < 10MB | 10-50MB | > 50MB | `ls -lah nexvision.db` |

### 3.3 Log File Locations

```bash
# Nginx logs (important for streaming issues)
/var/log/nginx/nexvision_access.log
/var/log/nginx/nexvision_error.log

# Application logs
/opt/nexvision/logs/app.log           # Main application
/opt/nexvision/logs/vod.log          # VOD streaming
/opt/nexvision/logs/storage.log      # Multi-storage operations

# System logs
journalctl -u nginx
journalctl -u nexvision              # If systemd service
```

---

## 4. ROUTINE OPERATIONS

### 4.1 Daily Checks

```bash
# 1. Service status
systemctl status nginx
ps aux | grep gunicorn

# 2. Disk space (important for VOD)
df -h /opt/nexvision

# 3. Channel count integrity
sqlite3 /opt/nexvision/nexvision.db "SELECT COUNT(*) FROM channels WHERE active=1"

# 4. Room registration status
sqlite3 /opt/nexvision/nexvision.db "SELECT COUNT(*) FROM rooms WHERE online=1"

# 5. Recent error logs
tail -n 50 /var/log/nginx/nexvision_error.log
```

### 4.2 Weekly Maintenance

```bash
# 1. Database optimization (if needed)
sqlite3 /opt/nexvision/nexvision.db "VACUUM;"

# 2. Log rotation check
logrotate -d /etc/logrotate.d/nginx

# 3. Storage backend health
curl -s http://localhost/storage/health | jq '.'

# 4. EPG sync status
curl -s http://localhost/api/epg?hours=24 | jq length
```

### 4.3 Package Management Operations

#### Adding All Channels to Package (New Feature)
1. **Via Admin UI**:
   - Navigate to Admin → Packages → Edit Package
   - Check ☑️ "Include ALL channels (11,427+ total)"
   - Click Save

2. **Via API** (for automation):
   ```bash
   curl -X PUT http://localhost/api/packages/2 \
     -H "Content-Type: application/json" \
     -d '{"name": "All Channels", "select_all_channels": true}'
   ```

---

## 5. TROUBLESHOOTING

### 5.1 Common Issues

#### Issue: "Channels not showing on TV"
**Symptoms**: TV client shows "Live TV (0)" or empty channel list
**Causes & Solutions**:
1. **Package not assigned**: Check Admin → Rooms → ensure room has package assigned
2. **Token issues**: Clear TV browser cache, re-register room
3. **API issues**: Check `curl http://localhost/api/channels?limit=5`

#### Issue: "VOD not playing"
**Symptoms**: Video fails to load, 404 errors in browser
**Causes & Solutions**:
1. **Nginx alias misconfigured**: Check `/etc/nginx/sites-available/nexvision`
2. **Storage backend down**: Check storage health endpoint
3. **File permissions**: Verify nexvision user can read VOD files

#### Issue: "Admin panel login fails"
**Symptoms**: Login redirects back to login page
**Causes & Solutions**:
1. **Database corruption**: Check SQLite integrity
2. **Session issues**: Clear browser cookies
3. **Password hash**: Reset admin password via direct DB update

#### Issue: "EPG not showing"
**Symptoms**: No programme information on channels
**Causes & Solutions**:
1. **EPG source down**: Check EPG sync status in admin
2. **Channel matching**: Verify tvg_id mapping in channels
3. **Sync frequency**: Check EPG auto-sync settings

### 5.2 Emergency Procedures

#### Service Recovery
1. **Quick restart**:
   ```bash
   systemctl restart nginx
   cd /opt/nexvision && pkill gunicorn && python3 app.py &
   ```

2. **Database recovery**:
   ```bash
   cp nexvision.db nexvision.db.backup
   sqlite3 nexvision.db ".dump backup.sql"
   ```

3. **Configuration rollback**:
   ```bash
   cd /opt/nexvision
   git status                    # Check what changed
   git checkout -- app.py       # Rollback specific file
   ```

---

## 6. CHANGE MANAGEMENT

### 6.1 Configuration Changes

#### Safe Change Procedure
1. **Backup current state**:
   ```bash
   cp /opt/nexvision/app.py /opt/nexvision/app.py.backup.$(date +%Y%m%d_%H%M%S)
   cp /opt/nexvision/nexvision.db /opt/nexvision/nexvision.db.backup.$(date +%Y%m%d_%H%M%S)
   ```

2. **Test in staging** (if available)

3. **Apply changes during low-traffic window**

4. **Verify functionality**:
   - Admin panel login
   - TV client load test
   - Channel streaming test
   - VOD playback test

### 6.2 Database Schema Updates

When updating database schema:
```bash
# 1. Backup first
sqlite3 nexvision.db ".backup backup_$(date +%Y%m%d).db"

# 2. Apply changes via SQL file or admin interface

# 3. Verify integrity
sqlite3 nexvision.db "PRAGMA integrity_check;"

# 4. Test core functionality
```

---

## 7. PERFORMANCE TUNING

### 7.1 Nginx Optimization

Key settings in `/etc/nginx/sites-available/nexvision`:
```nginx
# High-performance streaming
sendfile on;
tcp_nopush on;
tcp_nodelay on;

# Caching for static content
location ~* \.(m3u8|ts|mp4)$ {
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

### 7.2 Database Optimization

```bash
# SQLite tuning (add to app.py)
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = 1000000;
PRAGMA temp_store = memory;
```

### 7.3 Storage Backend Optimization

- **Local Storage**: Use SSD for VOD files
- **NAS**: Ensure gigabit connection
- **Cloud Storage**: Use CDN for frequently accessed content

---

## 8. SECURITY OPERATIONS

### 8.1 Access Control Verification

```bash
# Check admin authentication
curl -s http://localhost/admin | grep -q "login" && echo "Auth working"

# Verify room token isolation
curl -s -H "X-Room-Token: invalid" http://localhost/api/channels

# Check file permissions
ls -la /opt/nexvision/nexvision.db    # Should be nexvision:nexvision 600
```

### 8.2 Security Monitoring

Monitor for:
- Failed login attempts in admin panel
- Unusual API access patterns
- Large file downloads (potential content theft)
- Unexpected database size growth

---

## APPENDIX: CONTACT INFORMATION

**System Administrator**: IT Operations Team
**Emergency Contact**: 24/7 IT Helpdesk
**Vendor Support**: NexVision Technical Support

**Related Documents**:
- [DEPLOYMENT-GUIDE.md](DEPLOYMENT-GUIDE.md) - Installation procedures
- [Server-Hardening-Procedure.md](Server-Hardening-Procedure.md) - Security hardening
- [STORAGE-QUICK-REFERENCE.md](STORAGE-QUICK-REFERENCE.md) - Storage operations

---
*Document last updated: March 23, 2026*