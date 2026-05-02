# NexVision IPTV — Hotel Mode Deployment Guide

> **Audience**: System integrators, hotel IT teams, and network engineers deploying NexVision in hospitality environments.
>
> **Deployment Mode**: `hotel` (set via `settings` table key `deployment_mode`)
>
> **Last updated**: 2026-05-02

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Channel Type Reference](#2-channel-type-reference)
3. [Server Requirements](#3-server-requirements)
4. [Step-by-Step Server Deployment](#4-step-by-step-server-deployment)
5. [Network Configuration](#5-network-configuration)
6. [Nginx & Gunicorn Tuning](#6-nginx--gunicorn-tuning)
7. [Hotel Mode Configuration](#7-hotel-mode-configuration)
8. [Room & Package Setup](#8-room--package-setup)
9. [Channel Type Setup Per Room Category](#9-channel-type-setup-per-room-category)
10. [PMS Integration](#10-pms-integration)
11. [Health Checks & Monitoring](#11-health-checks--monitoring)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                          HOTEL NETWORK                               │
│                                                                      │
│  ┌─────────────┐   Multicast/IGMP    ┌────────────────────────────┐ │
│  │  Head-End   │──────────────────►  │  Managed Switch (IGMP      │ │
│  │  Encoder    │  (UDP 224.x.x.x)    │  Snooping enabled)         │ │
│  │  (Analog ►  │                     └──────────┬─────────────────┘ │
│  │   Digital)  │                                │ VLAN 10 (IPTV)    │
│  └─────────────┘                                │                   │
│                                                 ▼                   │
│  ┌─────────────┐   HTTP/HLS          ┌────────────────────────────┐ │
│  │  External   │──────────────────►  │   NexVision App Server     │ │
│  │  M3U        │  (Internet/CDN)     │   (Ubuntu 22.04 LTS)       │ │
│  │  Provider   │                     │                            │ │
│  └─────────────┘                     │  ┌──────────┐ ┌─────────┐ │ │
│                                      │  │  Nginx   │ │Gunicorn │ │ │
│  ┌─────────────┐   RF Signal         │  │ :80/:443 │ │ gevent  │ │ │
│  │  Analog     │──► Head-End ──────► │  └──────────┘ └─────────┘ │ │
│  │  Antenna/   │   Encoder           │  ┌──────────┐ ┌─────────┐ │ │
│  │  CATV       │                     │  │  MySQL   │ │  Redis  │ │ │
│  └─────────────┘                     │  └──────────┘ └─────────┘ │ │
│                                      └──────────────┬─────────────┘ │
│                                                     │               │
│             ┌────────────────────────────────────────┘              │
│             │  VLAN 20 (Guest Wi-Fi / In-Room LAN)                  │
│             ▼                                                        │
│   ┌─────┐ ┌─────┐ ┌──────────┐ ┌──────────┐ ┌──────┐             │
│   │ TV  │ │ TV  │ │ Tablet   │ │  Phone   │ │ Cast │             │
│   │Rm101│ │Rm102│ │(Lobby)   │ │(Guest)   │ │Device│             │
│   └─────┘ └─────┘ └──────────┘ └──────────┘ └──────┘             │
└──────────────────────────────────────────────────────────────────────┘
```

### Signal Flow

| Source | Path | Protocol | Who Handles |
|--------|------|----------|-------------|
| Analog antenna / CATV | Head-end encoder → switch | UDP multicast | Nginx passthrough |
| DVB-T/S encoder | Encoder → switch | UDP multicast | Nginx passthrough |
| External IPTV provider | Internet → server | HTTP M3U / HLS | Flask + Nginx proxy |
| Local VOD files | HDD → Nginx | HLS `.ts` segments | Nginx X-Accel-Redirect |
| Satellite decoder | Decoder → encoder → switch | UDP multicast | Nginx passthrough |

---

## 2. Channel Type Reference

NexVision stores each channel's delivery method in the `channel_type` column of the `channels` table.

### 2.1 UDP / Multicast (`stream_udp`)

**What it is**: TV channels delivered as multicast UDP streams inside the hotel LAN. Requires a head-end encoder (hardware or software) that converts the source signal (antenna, cable, satellite, analog) into IP multicast packets.

**URL format**:
```
udp://@<multicast-group>:<port>
udp://@224.1.1.1:5000
udp://@239.0.0.1:1234
```

**How the TV client receives it**: The TV app receives the stream URL from the API and opens it via a player that supports UDP multicast (e.g., ExoPlayer, VLC, native Android player). The stream **never passes through the NexVision app server** — the multicast traffic flows directly from the head-end to the TV over the LAN switch.

**Network requirements**:
- Layer 2 switches with **IGMP Snooping** enabled (prevents multicast flooding)
- All TVs and the head-end encoder on the same VLAN (or routed multicast between VLANs)
- Switch uplinks and access ports must handle the aggregated bitrate (e.g., 500 channels × 4 Mbps = 2 Gbps — use link aggregation or limit active streams)
- Head-end encoder must be on the same broadcast domain or IGMP Querier must be present

**When to use**:
- Standard hotel rooms with Android TV or Smart TV hardware
- High-density deployments (100+ TVs) — multicast scales to any number of receivers at zero additional bandwidth cost
- Live local TV, news, sports, religious channels

**Database entry example**:
```sql
INSERT INTO channels (name, stream_url, channel_type, media_group_id)
VALUES ('BBC World News', 'udp://@224.1.1.1:50000', 'stream_udp', 1);
```

---

### 2.2 M3U / HTTP Stream (`m3u`)

**What it is**: Channels delivered as HTTP or HTTPS streams, typically from an external IPTV provider or a remote CDN. Imported via an M3U8 playlist file or URL.

**URL formats**:
```
http://provider.com:8080/live/username/password/12345.ts
https://cdn.provider.com/stream/channel.m3u8
rtmp://live.provider.com/app/streamkey
```

**How to import**:

Via Admin Panel → Channels → Import M3U:
1. Paste the provider M3U URL (e.g., `http://provider.com:8080/get.php?username=X&password=Y&type=m3u_plus`)
2. Select channel type: **m3u**
3. Choose target media group
4. Click Import — NexVision parses the playlist and inserts all channels

Via API:
```bash
curl -X POST http://localhost/api/channels/import_m3u \
  -H "Content-Type: application/json" \
  -d '{"url": "http://provider.com/playlist.m3u", "channel_type": "m3u", "group_id": 1}'
```

**Network requirements**:
- The NexVision server must have outbound Internet access to the provider
- For HLS streams, the TV client fetches segments directly from the CDN (server is only the metadata broker)
- For `.ts` streams that the server proxies, ensure server has ≥100 Mbps uplink per 25 concurrent viewers

**When to use**:
- International channels not available locally
- IPTV subscription providers
- Backup channels if the local head-end fails
- Premium international sports/movies

---

### 2.3 Analog (via Head-End Encoder)

**What it is**: Analog TV signals (terrestrial antenna, cable TV coaxial, VHF/UHF) converted to IP multicast by a hardware head-end encoder. From NexVision's perspective, the output is a `stream_udp` channel — the "analog" distinction is at the physical input of the encoder, not in the software.

**Equipment needed**:
- **Head-end encoder** (examples): Amino, Wellav, Dektec, StreamTech, Wellav WMB
- RF input: F-connector (cable), IEC-type (antenna), or composite/HDMI (analog AV)
- Output: UDP multicast on the LAN

**Channel entry** (same as UDP, tagged with analog source for documentation):
```sql
INSERT INTO channels (name, stream_url, channel_type, media_group_id)
VALUES ('Local News (Analog Ch5)', 'udp://@224.2.1.5:5000', 'stream_udp', 2);
```

**Head-end wiring topology**:
```
Antenna / Cable Coax
        │
        ▼
┌──────────────────┐
│  Splitter/       │
│  Distribution    │
│  Amplifier       │
└──────┬───────────┘
       │  RF
       ▼
┌──────────────────┐        UDP Multicast
│  Head-End        │ ─────────────────────► LAN Switch ──► NexVision
│  Encoder         │  224.x.x.x:port                        Server
│  (e.g. 16-ch)    │
└──────────────────┘
```

**When to use**:
- Local free-to-air TV channels
- Government or religious channels available only on terrestrial broadcast
- Hotel locations where IPTV subscription is unavailable or unreliable
- Budget deployments reusing existing coax infrastructure

---

### 2.4 Summary Table

| Type | `channel_type` value | URL prefix | Server bandwidth | Requires head-end | Scales to N TVs |
|------|----------------------|------------|-----------------|-------------------|-----------------|
| UDP Multicast | `stream_udp` | `udp://@` | 0 (direct LAN) | Yes | Yes (multicast) |
| HTTP/M3U Stream | `m3u` | `http://`, `https://`, `rtmp://` | ~4 Mbps/viewer | No | Limited by uplink |
| Analog via encoder | `stream_udp` | `udp://@` | 0 (direct LAN) | Yes (RF encoder) | Yes (multicast) |
| Local VOD / HLS | `vod` | `/vod/hls/` | Nginx sendfile | No | Yes (Nginx) |

---

## 3. Server Requirements

### 3.1 Minimum Specifications

| Resource | Small Hotel (≤50 rooms) | Medium Hotel (50–200 rooms) | Large Hotel (200+ rooms) |
|----------|--------------------------|------------------------------|--------------------------|
| CPU | 2 cores | 4 cores | 8+ cores |
| RAM | 4 GB | 8 GB | 16–32 GB |
| Disk (OS + App) | 50 GB SSD | 100 GB SSD | 200 GB SSD |
| Disk (VOD) | 500 GB HDD | 2 TB HDD | 4–10 TB RAID |
| Network NIC | 1 Gbps | 1 Gbps | 2 × 1 Gbps (bonded) |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |

### 3.2 Software Stack

| Component | Version | Role |
|-----------|---------|------|
| Python | 3.10+ | Application runtime |
| Flask | 3.x | Web framework |
| Gunicorn | 21.x | WSGI server (gevent workers) |
| Nginx | 1.24+ | Reverse proxy, static files, HLS |
| MySQL | 8.0+ | Primary database |
| Redis | 7.x | Cache layer (config stamps, API TTL) |
| FFmpeg | 6.x | VOD transcoding (optional) |

---

## 4. Step-by-Step Server Deployment

### Step 1 — Prepare the OS

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install system dependencies
sudo apt install -y \
  python3 python3-pip python3-venv \
  nginx mysql-server redis-server \
  ffmpeg git curl wget unzip \
  build-essential libssl-dev libffi-dev \
  python3-dev default-libmysqlclient-dev

# Create application user
sudo useradd -r -s /usr/sbin/nologin -d /opt/nexvision nexvision
```

### Step 2 — Create Directory Structure

```bash
sudo mkdir -p /opt/nexvision
sudo mkdir -p /run/nexvision          # Gunicorn socket (volatile)
sudo mkdir -p /var/log/nexvision      # Application logs
sudo mkdir -p /var/cache/nexvision/{hls,api}  # Nginx cache
sudo mkdir -p /opt/nexvision/vod/{hls,thumbnails}
sudo mkdir -p /opt/nexvision/uploads

sudo chown -R nexvision:nexvision /opt/nexvision
sudo chown -R nexvision:www-data /var/log/nexvision
sudo chown -R www-data:www-data /var/cache/nexvision
```

### Step 3 — Clone and Install Application

```bash
cd /opt/nexvision

# Create virtual environment
sudo -u nexvision python3 -m venv venv
sudo -u nexvision venv/bin/pip install --upgrade pip

# Install Python dependencies
sudo -u nexvision venv/bin/pip install -r requirements_prod.txt
```

### Step 4 — Configure Environment Variables

```bash
sudo nano /opt/nexvision/.env
```

```dotenv
# ── Application ────────────────────────────────────────────────────
SECRET_KEY=<generate: python3 -c "import secrets; print(secrets.token_hex(32))">
DEPLOYMENT_MODE=hotel
FLASK_ENV=production
DEBUG=false

# ── Database ───────────────────────────────────────────────────────
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=nexvision
MYSQL_PASSWORD=<strong-password>
MYSQL_DB=nexvision
MYSQL_VOD_DB=nexvision_vod

# ── Redis ─────────────────────────────────────────────────────────
REDIS_URL=redis://127.0.0.1:6379/0

# ── Security ──────────────────────────────────────────────────────
VOD_API_KEY=<generate: python3 -c "import secrets; print(secrets.token_hex(32))">

# ── Media Paths ───────────────────────────────────────────────────
UPLOAD_FOLDER=/opt/nexvision/uploads
VOD_DIR=/opt/nexvision/vod

# ── Gunicorn ──────────────────────────────────────────────────────
GUNICORN_WORKERS=5    # (2 × CPU_cores) + 1
```

```bash
sudo chmod 600 /opt/nexvision/.env
sudo chown nexvision:nexvision /opt/nexvision/.env
```

### Step 5 — Configure MySQL

```bash
sudo mysql -u root -p <<'SQL'
CREATE DATABASE nexvision CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE nexvision_vod CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'nexvision'@'127.0.0.1' IDENTIFIED BY '<strong-password>';
GRANT ALL PRIVILEGES ON nexvision.* TO 'nexvision'@'127.0.0.1';
GRANT ALL PRIVILEGES ON nexvision_vod.* TO 'nexvision'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL
```

### Step 6 — Initialize Database

```bash
cd /opt/nexvision
sudo -u nexvision venv/bin/python run.py --init-db
# or via Flask CLI:
sudo -u nexvision venv/bin/flask --app app.main init-db
```

### Step 7 — Configure Socket Persistence (systemd-tmpfiles)

```bash
sudo tee /etc/tmpfiles.d/nexvision.conf <<'EOF'
d /run/nexvision 0755 nexvision www-data -
EOF

sudo systemd-tmpfiles --create /etc/tmpfiles.d/nexvision.conf
```

### Step 8 — Create systemd Service

```bash
sudo tee /etc/systemd/system/nexvision.service <<'EOF'
[Unit]
Description=NexVision IPTV Gunicorn Service
After=network.target mysql.service redis.service
Requires=mysql.service redis.service

[Service]
Type=notify
User=nexvision
Group=www-data
WorkingDirectory=/opt/nexvision
EnvironmentFile=/opt/nexvision/.env
ExecStart=/opt/nexvision/venv/bin/gunicorn \
    --config /opt/nexvision/app/gunicorn.conf.py \
    app.wsgi:application
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
RuntimeDirectory=nexvision
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable nexvision
sudo systemctl start nexvision
```

### Step 9 — Configure Nginx

```bash
# Install the bundled config
sudo cp /opt/nexvision/nginx/nexvision.conf /etc/nginx/sites-available/nexvision
sudo ln -sf /etc/nginx/sites-available/nexvision /etc/nginx/sites-enabled/nexvision
sudo rm -f /etc/nginx/sites-enabled/default

# Test and reload
sudo nginx -t && sudo systemctl reload nginx
```

**For HTTPS (LetsEncrypt)**:
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-hotel-domain.com
# Certbot auto-patches the Nginx config and sets up auto-renewal
```

### Step 10 — Verify Installation

```bash
# Check all services
sudo systemctl status nexvision nginx mysql redis-server

# Test API
curl -s http://localhost/api/settings | python3 -m json.tool | head -20

# Check logs
sudo journalctl -u nexvision -f
sudo tail -f /var/log/nexvision/error.log
```

---

## 5. Network Configuration

### 5.1 VLAN Design (Recommended)

```
VLAN 10 — IPTV Backbone  (head-end, NexVision server, managed switches)
VLAN 20 — Guest Devices  (TVs, tablets, phones, Cast devices)
VLAN 30 — Management     (admin laptops, PMS server, NexVision admin access)
VLAN 99 — Uplink/WAN     (Internet gateway)
```

Inter-VLAN routing is needed only for:
- Guest devices (VLAN 20) → NexVision server (VLAN 10) on TCP port 80/443
- NexVision server (VLAN 10) → MySQL/Redis if on separate host
- Management (VLAN 30) → NexVision server TCP 80/22

Multicast traffic (UDP) stays within VLAN 10, distributed by the switch to VLAN 20 access ports via IGMP proxy.

### 5.2 Switch Configuration (Cisco IOS example)

```cisco
! Enable IGMP Snooping globally
ip igmp snooping
ip igmp snooping vlan 10
ip igmp snooping vlan 20

! Configure IGMP Querier on VLAN 10 (points to head-end or server IP)
ip igmp snooping querier 192.168.10.1

! Uplink port (trunk) to head-end switch
interface GigabitEthernet0/1
  switchport mode trunk
  switchport trunk allowed vlan 10,20,30

! Room access port (untagged VLAN 20)
interface GigabitEthernet0/24
  switchport mode access
  switchport access vlan 20
  ip igmp snooping max-groups 8    ! limit per port

! Multicast router port (toward head-end / server)
interface GigabitEthernet0/2
  ip igmp snooping mrouter
```

### 5.3 IP Address Plan

| Device | VLAN | IP Range | Notes |
|--------|------|----------|-------|
| Head-end encoder | 10 | 192.168.10.10–.20 | Static IP |
| NexVision server | 10 | 192.168.10.100 | Static IP |
| MySQL (if separate) | 10 | 192.168.10.101 | Static IP |
| Redis (if separate) | 10 | 192.168.10.102 | Static IP |
| TV Room 101 | 20 | 192.168.20.101 | DHCP reservation |
| TV Room 102 | 20 | 192.168.20.102 | DHCP reservation |
| Guest phones/tablets | 20 | 192.168.20.200–.254 | DHCP dynamic |
| PMS server | 30 | 192.168.30.50 | Static IP |

### 5.4 Firewall Rules

```
# On NexVision server (ufw)
sudo ufw allow from 192.168.10.0/24 to any port 80     # internal HTTP
sudo ufw allow from 192.168.10.0/24 to any port 443    # internal HTTPS
sudo ufw allow from 192.168.20.0/24 to any port 80     # guest TV access
sudo ufw allow from 192.168.20.0/24 to any port 443    # guest TV HTTPS
sudo ufw allow from 192.168.30.0/24 to any port 22     # admin SSH
sudo ufw allow from 192.168.30.0/24 to any port 80     # admin panel
sudo ufw deny from any to 192.168.10.0/24 port 3306    # block MySQL from guests
sudo ufw deny from any to 192.168.10.0/24 port 6379    # block Redis from guests
sudo ufw enable
```

### 5.5 Multicast Address Assignment

Reserve a block of multicast addresses for the hotel. Recommended ranges:

| Channel Category | Multicast Range | Example |
|-----------------|----------------|---------|
| News channels | 224.1.1.0/24 | 224.1.1.1–224.1.1.50 |
| Sports channels | 224.1.2.0/24 | 224.1.2.1–224.1.2.50 |
| Entertainment | 224.1.3.0/24 | 224.1.3.1–224.1.3.100 |
| Children | 224.1.4.0/24 | 224.1.4.1–224.1.4.30 |
| Local/Analog | 224.2.0.0/24 | 224.2.0.1–224.2.0.20 |

**Port**: use a single port per channel (e.g., `5000`) or a fixed block (`50000–50999`). Consistent ports simplify firewall ACLs.

### 5.6 Bandwidth Planning

| Stream type | Bitrate per channel | 50 channels | 200 channels |
|-------------|--------------------|-----------  |--------------|
| SD UDP multicast | 2–4 Mbps | 100–200 Mbps | 400–800 Mbps |
| HD UDP multicast | 6–10 Mbps | 300–500 Mbps | 1.2–2 Gbps |
| FHD UDP multicast | 10–20 Mbps | 500 Mbps–1 Gbps | 2–4 Gbps |
| M3U (HTTP, per viewer) | 4–8 Mbps | 200–400 Mbps | 800 Mbps–1.6 Gbps |

> **Key insight**: Multicast bandwidth is constant regardless of viewer count. 200 TVs watching the same UDP channel costs the same as 1 TV. HTTP/M3U streams multiply by viewer count.

---

## 6. Nginx & Gunicorn Tuning

### 6.1 Gunicorn Worker Count

```python
# /opt/nexvision/app/gunicorn.conf.py
workers = (2 × CPU_cores) + 1

# Examples:
# 2-core server  → 5 workers  → 5000 concurrent connections (gevent)
# 4-core server  → 9 workers  → 9000 concurrent connections
# 8-core server  → 17 workers → 17000 concurrent connections
```

Each gevent worker handles **1000 concurrent lightweight connections** (configurable via `worker_connections`). One worker uses ~50–80 MB RAM.

### 6.2 Key Nginx Directives

```nginx
# Upstream: persistent connections to Gunicorn (avoid TCP setup on every request)
upstream nexvision_app {
    server unix:/run/nexvision/gunicorn.sock fail_timeout=0;
    keepalive 64;
}

# HLS playlist cache: 5 second TTL reduces DB hits during rapid .ts segment loads
proxy_cache_valid 200 5s;

# X-Accel-Redirect: Nginx serves .ts video segments at kernel level
# Flask authenticates the request, returns the X-Accel-Redirect header,
# and Nginx serves the file without Python reading a single byte of video data.
location /internal/vod/ {
    internal;
    alias /opt/nexvision/vod/;
}
```

### 6.3 Redis Cache TTLs

| Cache Key Prefix | TTL | Reason |
|-----------------|-----|--------|
| `nv:settings` | 60 s | Hotel settings change rarely |
| `nv:channels` | 30 s | Balance freshness vs. DB load |
| `nv:nav` | 30 s | Navigation menu |
| `nv:slides` | 60 s | Promo slides |
| `nv:rss` | 300 s | RSS news ticker |

Cache is invalidated immediately when admin saves changes via `bump_config_stamp()`.

---

## 7. Hotel Mode Configuration

### 7.1 Set Deployment Mode

Via Admin Panel → Settings → General:
- **Deployment Mode**: `hotel`

Or directly in database:
```sql
UPDATE settings SET value='hotel' WHERE key='deployment_mode';
```

### 7.2 Hotel Identity Settings

```sql
-- Minimum required settings for hotel mode
UPDATE settings SET value='Grand Palace Hotel' WHERE key='hotel_name';
UPDATE settings SET value='Welcome to Grand Palace! Enjoy your stay.' WHERE key='welcome_message';
UPDATE settings SET value='12:00' WHERE key='checkout_time';
UPDATE settings SET value='Dubai' WHERE key='prayer_city';
UPDATE settings SET value='AE' WHERE key='prayer_country';
```

### 7.3 Admin Account Setup

```bash
# First-run creates default admin. Change password immediately.
curl -X POST http://localhost/api/auth/change-password \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your-session>" \
  -d '{"current_password": "admin", "new_password": "<strong-password>"}'
```

---

## 8. Room & Package Setup

### 8.1 Room Types and Their Typical Channel Access

NexVision uses **content packages** to control which channels each room can access. A room can be assigned multiple packages, plus individual VIP channels.

| Room Type | Typical Package | Channel Access |
|-----------|----------------|----------------|
| Standard Room | Basic | Free-to-air local channels, news, SD |
| Superior Room | Basic + Entertainment | + HD entertainment, sports preview |
| Deluxe Room | Standard | + Full sports, HD |
| Suite | Premium | + VIP international, adult (if licensed) |
| Business Suite | Premium + Business | + Business news, Bloomberg, CNBC |
| Lobby / Public | Public | News, tourism channels, no VIP |
| Gym / Spa | Wellness | Sports, music, wellness content |
| Conference Room | Business | News channels, screen sharing |

### 8.2 Create Packages via Admin API

```bash
# Create "Basic" package
curl -X POST http://localhost/api/packages \
  -H "Content-Type: application/json" \
  -d '{"name": "Basic", "description": "Free-to-air + local news", "price": 0}'

# Create "Premium" package
curl -X POST http://localhost/api/packages \
  -d '{"name": "Premium", "description": "Full HD + Sports + International", "price": 15}'
```

### 8.3 Assign Channels to Packages

```bash
# Assign channel ID 1 to package ID 1
curl -X POST http://localhost/api/packages/1/channels \
  -H "Content-Type: application/json" \
  -d '{"channel_id": 1}'
```

### 8.4 Register Rooms and Assign Packages

```bash
# Create room
curl -X POST http://localhost/api/rooms \
  -H "Content-Type: application/json" \
  -d '{
    "room_number": "101",
    "tv_name": "Room 101 Main TV",
    "skin_id": 1
  }'

# Assign package to room (room_id=1, package_id=1)
curl -X POST http://localhost/api/rooms/1/packages \
  -d '{"package_id": 1}'
```

### 8.5 Room Token Distribution

Every room gets a unique `room_token`. The TV client uses this token to authenticate and receive only the channels assigned to that room.

```bash
# Get room token
curl http://localhost/api/rooms/101/token

# TV client uses: http://server/api/channels?room_token=<token>
```

---

## 9. Channel Type Setup Per Room Category

### 9.1 Standard Room (UDP + limited M3U)

```
Channels:
  - 10× local free-to-air (stream_udp, 224.1.1.0/24)
  - 5× news (stream_udp, 224.1.1.50–55)
  - 3× children (stream_udp, 224.1.4.1–3)
Package: Basic
```

### 9.2 Suite / Business Room (All types)

```
Channels:
  - 10× local free-to-air (stream_udp)
  - 20× international HD (m3u, from provider)
  - 5× premium sports (m3u, PPV)
  - 10× business/finance (m3u, Bloomberg/CNBC)
  - VIP: adult/premium (vip_channel_access per room)
Packages: Premium + Business
```

### 9.3 Analog Channels (Legacy / Local Broadcast)

```
Head-end converts RF → UDP multicast:
  - Analog channel 5 → udp://@224.2.0.5:5000  → "Channel 5 Local"
  - Analog channel 8 → udp://@224.2.0.8:5000  → "Channel 8 Government"

In NexVision, these are stored as stream_udp exactly like any other UDP channel.
```

### 9.4 Mixed Deployment (All types simultaneously)

NexVision handles all channel types in a single channel list. The TV client receives a unified list from `/api/channels?room_token=<token>` and plays each stream according to its URL scheme:

```
udp://@224.x.x.x:port  → VLC/ExoPlayer UDP multicast
http(s)://...           → ExoPlayer HTTP stream
/vod/hls/...            → ExoPlayer HLS playlist from NexVision server
```

No special configuration is needed — channel type co-existence is built in.

---

## 10. PMS Integration

NexVision integrates with Property Management Systems (PMS) to automatically populate guest name and check-in/out on the TV welcome screen.

### 10.1 Supported Protocols

| Protocol | Standard | Common PMS |
|----------|---------|------------|
| FIAS/TCP | Oracle Hospitality FIAS | Opera, Micros |
| GRMS | Honeywell / other | Various |
| HTTP REST | Custom | Any modern PMS |

### 10.2 FIAS Integration Endpoint

```
POST /api/pms/fias
Content-Type: application/json

{
  "room_number": "101",
  "guest_name": "John Smith",
  "checkin_time": "2026-05-02 14:00",
  "checkout_time": "2026-05-05 12:00",
  "event": "checkin"   // or "checkout"
}
```

On checkout, NexVision clears guest data and resets the room skin to default.

See [PMS_INTEGRATION.md](PMS_INTEGRATION.md) for full protocol details.

---

## 11. Health Checks & Monitoring

### 11.1 Service Status

```bash
sudo systemctl status nexvision nginx mysql redis-server

# One-liner health check
for svc in nexvision nginx mysql redis; do
  echo -n "$svc: "
  systemctl is-active $svc
done
```

### 11.2 Application Health Endpoints

```bash
# Core API health (should return 200)
curl -s -o /dev/null -w "%{http_code}" http://localhost/api/settings

# Channel list (verifies DB + channel service)
curl -s http://localhost/api/channels | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Channels: {d['total']}\")"

# Room list (verifies room service)
curl -s http://localhost/api/rooms | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"Rooms: {len(d)}\")"
```

### 11.3 Multicast Stream Verification

```bash
# Verify UDP multicast is flowing (requires VLC or ffprobe on same VLAN)
ffprobe -v quiet -print_format json -show_streams "udp://@224.1.1.1:5000" 2>&1 | head -20

# Check multicast group subscriptions on server NIC
netstat -g

# Monitor multicast traffic on interface
sudo tcpdump -i eth0 -n 'multicast' -c 20
```

### 11.4 Log Locations

| Log | Path | Purpose |
|-----|------|---------|
| Nginx access | `/var/log/nginx/nexvision_access.log` | HTTP request log |
| Nginx error | `/var/log/nginx/nexvision_error.log` | Proxy/static errors |
| Gunicorn access | `/var/log/nexvision/access.log` | Flask request log |
| Gunicorn error | `/var/log/nexvision/error.log` | Application errors |
| systemd | `journalctl -u nexvision` | Process lifecycle |

---

## 12. Troubleshooting

### TV shows blank channel list

1. Verify `room_token` is valid: `curl http://server/api/rooms/<id>/token`
2. Verify package is assigned to room: check `room_packages` table
3. Verify channels are active: `SELECT name, active FROM channels WHERE active=1`

### UDP stream not playing on TV

1. Verify multicast traffic reaches TV VLAN: `sudo tcpdump -i eth0 udp`
2. Verify IGMP Snooping is enabled on switch
3. Test on same server: `ffplay udp://@224.1.1.1:5000`
4. Check head-end encoder is running and outputting the multicast group

### M3U import fails

1. Test URL is reachable from server: `curl -I "http://provider/playlist.m3u"`
2. Check Nginx body size limit (set to 4 GB in config for large M3U files)
3. Check error log: `tail -50 /var/log/nexvision/error.log`

### High server load with many M3U viewers

M3U HTTP streams multiply bandwidth by viewer count. If load is high:
1. Switch to UDP multicast for high-demand channels
2. Increase Gunicorn workers: `GUNICORN_WORKERS=<higher>` in `.env`
3. Enable Nginx caching for `.m3u8` playlists (already configured)

### Guest name not showing on TV

1. Verify PMS is sending to correct endpoint
2. Check room token matches the room: `SELECT room_number, room_token, guest_name FROM rooms WHERE room_number='101'`
3. Manually update: `UPDATE rooms SET guest_name='John Smith' WHERE room_number='101'`

---

## Appendix A — Quick Setup Checklist

- [ ] Ubuntu 22.04 installed, updated
- [ ] MySQL, Redis, Nginx, Python 3.10+ installed
- [ ] `/opt/nexvision/.env` configured with secrets
- [ ] MySQL databases created: `nexvision`, `nexvision_vod`
- [ ] Database initialized (`init-db`)
- [ ] systemd tmpfiles for socket persistence
- [ ] `nexvision.service` enabled and running
- [ ] Nginx config installed, tested, reloaded
- [ ] HTTPS configured (LetsEncrypt or internal CA)
- [ ] VLANs created: IPTV backbone, guest, management
- [ ] IGMP Snooping enabled on all switches
- [ ] Multicast address ranges documented and assigned
- [ ] Head-end encoder configured and outputting UDP streams
- [ ] Channels imported (UDP + M3U)
- [ ] Content packages created (Basic, Standard, Premium)
- [ ] Rooms registered with correct packages
- [ ] Admin password changed from default
- [ ] PMS integration tested (if applicable)
- [ ] Health check endpoints returning 200
- [ ] Log rotation configured (`logrotate`)

## Appendix B — Default Ports Reference

| Service | Port | Protocol | Notes |
|---------|------|----------|-------|
| Nginx HTTP | 80 | TCP | All TV and admin traffic |
| Nginx HTTPS | 443 | TCP | Production (LetsEncrypt) |
| Gunicorn socket | `/run/nexvision/gunicorn.sock` | Unix | Internal only |
| MySQL | 3306 | TCP | Bind to 127.0.0.1 |
| Redis | 6379 | TCP | Bind to 127.0.0.1 |
| UDP Multicast | 5000–50999 | UDP | Depends on head-end config |
| SSH | 22 | TCP | Management VLAN only |
