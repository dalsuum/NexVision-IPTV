# NexVision IPTV Platform v8.9

> **Hotel-grade IPTV system** delivering Live TV, Video on Demand, Radio, Guest Messaging, RSS News Ticker, and Promo Slides — to TVs, phones, tablets, and Android APK.

---

## Table of Contents

- [Overview](#overview)
- [Screenshots & Interfaces](#screenshots--interfaces)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start (Development)](#quick-start-development)
- [Production Deployment](#production-deployment)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Android APK](#android-apk)
- [Admin Panel Guide](#admin-panel-guide)
- [Tech Stack](#tech-stack)
- [Documentation](#documentation)
- [Project Structure](#project-structure)

---

## Overview

NexVision IPTV is a full-stack hotel IPTV platform built on **Flask + Python**. It runs on a single server in your hotel network and serves all guest devices — smart TVs, phones, tablets, and a dedicated Android app — with a rich, TV-optimised interface.

Guests connect via hotel WiFi and access the system through their browser or the NexVision Android APK. Hotel staff manage all content through a web-based admin panel.

```
Hotel WiFi/LAN
      │
      ▼
  Nginx :80
  ├── /          → TV Client (guest interface)
  ├── /admin/    → Admin Panel (staff)
  ├── /api/      → REST API  →  Flask (Gunicorn)
  └── /vod/hls/  → HLS Video → X-Accel-Redirect (disk)
```

---

## Features

### Guest Experience
| Feature | Description |
|---|---|
| 📺 **Live TV** | IPTV channels from M3U sources, grouped by category |
| 🎬 **Video on Demand** | Multi-quality HLS streaming (480p / 720p / 1080p) |
| 📻 **Radio** | Internet radio stations with vinyl animation |
| 💬 **Messages** | Room-specific messages + birthday popup notifications |
| 📰 **RSS Ticker** | Scrolling news ticker with custom color, background & opacity |
| 🖼 **Promo Slides** | Full-screen promotional slides with auto-play |
| 🖼 **Gallery** | Hotel photo gallery |
| 📱 **Responsive** | Bottom navigation bar on mobile (≤640px) |
| 📱 **Android APK** | Native app with embedded VLC player |

### Admin Capabilities
| Feature | Description |
|---|---|
| 📡 Channel Management | Import from M3U URL/file, edit, reorder, bulk select |
| 🎬 VOD Management | Upload MP4 → auto-transcoded to HLS by FFmpeg |
| 💬 Messaging | Broadcast to all rooms or specific rooms |
| 🎂 Birthdays | Auto birthday messages injected into guest inbox |
| 📰 RSS Feeds | Add/remove feeds, set global ticker appearance |
| 🖼 Promo Slides | Upload images, set display order and duration |
| 🎨 Navigation | Customise menu items, icons, order |
| ⚙ Settings | Hotel name, logo, feature toggles per room type |
| 🏠 Rooms | Create rooms, assign packages, generate access tokens |
| 📦 Packages | Bundle VOD content into subscription packages |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  CLIENTS                                                  │
│  📺 Smart TV  📱 Phone Browser  📱 Android APK  🔧 Admin  │
└─────────────────────┬────────────────────────────────────┘
                      │ HTTP / HLS / REST
┌─────────────────────▼────────────────────────────────────┐
│  NGINX  (Port 80)                                         │
│  Static files · X-Accel HLS · Proxy to Gunicorn          │
└─────────────────────┬────────────────────────────────────┘
                      │ Unix socket
┌─────────────────────▼────────────────────────────────────┐
│  GUNICORN + FLASK  (gevent workers)                       │
│  Settings · Channels · VOD · Messages · RSS · Slides      │
│  FFmpeg transcoder (MP4 → HLS on upload)                  │
└──────┬─────────────────────────────────────┬─────────────┘
       │                                     │
┌──────▼──────┐  ┌──────────────┐  ┌────────▼────────────┐
│   Redis     │  │ nexvision.db │  │     vod.db          │
│   Cache     │  │  (MySQL prod)│  │  (MySQL prod)       │
└─────────────┘  └──────────────┘  └─────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────────┐
│  DISK STORAGE                                             │
│  /videos/  /hls/  /thumbnails/  /uploads/  /ffmpeg/      │
└──────────────────────────────────────────────────────────┘
```

See full architecture diagram: [`docs/nexvision-architecture.drawio`](docs/nexvision-architecture.drawio)

---

## Quick Start (Development)

### Prerequisites
- Python 3.10+
- FFmpeg (bundled in `ffmpeg/bin/` for Windows)

### 1. Install Dependencies
```bash
cd oneviosn-iptv-v8.9
pip install flask werkzeug feedparser requests
```

### 2. Run the Server
```bash
python app.py
```

### 3. Access the Interfaces
| Interface | URL |
|---|---|
| TV Client (guests) | http://localhost:5000/ |
| Admin Panel (staff) | http://localhost:5000/admin/ |
| VOD Dashboard | http://localhost:5000/vod/ |

> **Default admin PIN:** Check `settings` table in `nexvision.db` after first run.

### 4. From Another Device (Phone/TV)
Find your machine's IP address:
```bash
# Windows
ipconfig

# Linux/Mac
ip a
```

Access from phone/TV: `http://YOUR_IP:5000/`

---

## Production Deployment

For a production environment serving 500+ concurrent users:

```bash
# Full step-by-step guide
docs/Deployment-Procedure.md
```

**Quick summary:**
```bash
# 1. Install system packages
sudo apt install python3 python3-venv nginx redis-server mysql-server ffmpeg -y

# 2. Setup Python environment
python3 -m venv venv
venv/bin/pip install -r requirements_prod.txt

# 3. Configure environment
cp .env.example .env
nano .env    # Set MySQL, Redis, secrets

# 4. Start services
sudo systemctl start nexvision nginx redis mysql
```

**Production stack:**
- **Nginx** — Reverse proxy, static files, X-Accel-Redirect for HLS
- **Gunicorn + gevent** — Async workers (2×CPU+1), 1000 connections/worker
- **Redis** — API response cache (settings 60s, channels 30s, RSS 300s)
- **MySQL** — Production database (replaces SQLite)

---

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```ini
# ── Database ──────────────────────────────
USE_MYSQL=1                          # 0 = SQLite (dev), 1 = MySQL (prod)
MYSQL_HOST=localhost
MYSQL_USER=nexvision
MYSQL_PASSWORD=your_strong_password
MYSQL_DB=nexvision
MYSQL_VOD_DB=nexvision_vod

# ── Cache ─────────────────────────────────
REDIS_URL=redis://localhost:6379/0   # Redis connection URL

# ── Nginx HLS ─────────────────────────────
USE_X_ACCEL=1                        # 0 = Flask serves .ts, 1 = Nginx kernel sendfile

# ── Gunicorn ──────────────────────────────
GUNICORN_WORKERS=5                   # Recommended: 2×CPU_cores + 1

# ── Flask ─────────────────────────────────
SECRET_KEY=generate_with_secrets.token_hex_32
```

### Key Settings (Admin Panel → Settings)
| Setting | Description |
|---|---|
| `hotel_name` | Displayed in TV client header |
| `admin_pin` | Admin panel access PIN |
| `show_slides` | Enable/disable promo slides |
| `show_news_ticker` | Enable/disable RSS ticker |
| `ticker_text_color` | RSS ticker text color (hex) |
| `ticker_bg_color` | RSS ticker background color (hex) |
| `ticker_bg_opacity` | RSS ticker opacity (0.0–1.0) |
| `featured_movie_hero` | Show featured VOD in hero banner |

---

## API Reference

All endpoints return JSON. Guest endpoints require room token header for access-controlled content:
```
X-Room-Token: <room_token>
```

### Core Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/settings` | Hotel settings (cached 60s) |
| `GET` | `/api/channels` | Live TV channels list |
| `GET` | `/api/nav` | Navigation menu items |
| `GET` | `/api/vod` | VOD movie list (stream_url dynamically resolved) |
| `GET` | `/api/vod?featured=1` | Featured movie for hero banner |
| `GET` | `/api/messages/active` | Active messages + birthday injections |
| `GET` | `/api/messages/inbox` | Full message inbox |
| `GET` | `/api/rss/public` | RSS feed items (cached 300s) |
| `GET` | `/api/slides/public` | Promo slides list |
| `POST` | `/api/login` | Room login, returns token |

### HLS Streaming Endpoints
| Endpoint | Served By | Description |
|---|---|---|
| `/vod/hls/{id}/master.m3u8` | Flask | Multi-quality playlist |
| `/vod/hls/{id}/{quality}/index.m3u8` | Flask (Nginx cached) | Quality playlist |
| `/vod/hls/{id}/{quality}/{seg}.ts` | **Nginx** (X-Accel) | Video segment |

### Admin Endpoints (require API key)
| Method | Endpoint | Description |
|---|---|---|
| `GET/POST` | `/api/channels` | Manage channels |
| `POST` | `/api/channels/import` | Import from M3U URL/file |
| `GET/POST` | `/api/vod` | Manage VOD movies |
| `GET/POST` | `/api/messages` | Send/manage messages |
| `GET/POST` | `/api/rss` | Manage RSS feeds |
| `GET/POST` | `/api/slides` | Manage promo slides |
| `GET/POST` | `/api/settings` | Update hotel settings |
| `GET/POST` | `/api/rooms` | Manage hotel rooms |

---

## Android APK

The NexVision Android app is a hotel-branded app that wraps the TV client with a native **libVLC 3.6** video player.

### Building the APK

**Requirements:**
- Java 21+
- Android SDK (command-line tools)
- Gradle 8.4

```bash
cd nexvision-apk

# Set server IP before building
# Edit: app/src/main/java/com/nexvision/iptv/MainActivity.java
# Change: static final String SERVER_URL = "http://YOUR_SERVER_IP";

# Build debug APK
gradle assembleDebug --no-daemon

# Output
app/build/outputs/apk/debug/app-debug.apk   (~86MB)
```

### APK Features
- Full-screen WebView loading the TV client
- **NexVisionBridge** — JavaScript ↔ Java interface
- **VLCPlayerActivity** — native fullscreen video player
  - Hardware decoding with software fallback
  - 5-second network buffer (hotel WiFi optimised)
  - Auto-reconnect on network drops (`--http-reconnect`)
  - Seek bar, play/pause, ±10s skip, close button
  - Auto-hide controls after 4 seconds

### Installing on Devices
1. Transfer `app-debug.apk` to Android device
2. Enable **Install from unknown sources** in Android settings
3. Open the APK file to install
4. Connect to hotel WiFi — app loads automatically

---

## Admin Panel Guide

### First Login
1. Navigate to `http://SERVER_IP/admin/`
2. Enter admin PIN (set in Settings after first run)

### Adding VOD Content
1. **Admin → Movies → Upload Video**
2. Select MP4 file → upload
3. FFmpeg transcodes automatically (480p + 720p + 1080p)
4. Transcoding progress shown live (~5-20 min per hour of video)
5. Movie appears in TV client when complete

### Importing TV Channels
1. **Admin → Channels → Import M3U**
2. Paste M3U URL or upload `.m3u` / `.m3u8` file
3. Channels auto-grouped by category
4. Edit names, logos, order as needed

### Sending Guest Messages
1. **Admin → Messages → New Message**
2. Select: All rooms / Specific room / Room type
3. Set message text, type, expiry time
4. Message appears as popup on guest TV/phone immediately

### Birthday Messages
1. **Admin → Guests / Birthdays → Add Birthday**
2. Enter guest name, room, birth date
3. On the birthday, a message automatically appears in guest inbox + popup

### RSS Ticker
1. **Admin → RSS → Add Feed** — paste any RSS feed URL
2. **Ticker Appearance** — set text color, background color, opacity
3. **Settings → Show News Ticker** — enable/disable globally

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python 3 + Flask | Web application + REST API |
| **WSGI** | Gunicorn + gevent | Async production server |
| **Proxy** | Nginx | Static files, HLS, rate limiting |
| **Cache** | Redis + Flask-Caching | Hot endpoint caching |
| **Database** | SQLite (dev) / MySQL (prod) | All application data |
| **Video** | FFmpeg | MP4 → HLS transcoding |
| **Streaming** | HLS (HTTP Live Streaming) | Adaptive bitrate video delivery |
| **TV Client** | Vanilla JS + CSS | Single-page TV interface |
| **Video Player** | hls.js 1.5 | Browser HLS playback |
| **Mobile Player** | libVLC Android 3.6 | APK native HLS player |
| **Android** | Java + WebView | Android APK wrapper |
| **Build** | Gradle 8.4 + Android SDK 34 | APK compilation |

---

## Documentation

| Document | Location | Description |
|---|---|---|
| **System Operations Book** | [`docs/SOB-System-Operations-Book.md`](docs/SOB-System-Operations-Book.md) | Operations reference, monitoring, incident response |
| **Deployment Procedure** | [`docs/Deployment-Procedure.md`](docs/Deployment-Procedure.md) | Step-by-step production deployment |
| **Server Hardening** | [`docs/Server-Hardening-Procedure.md`](docs/Server-Hardening-Procedure.md) | Security hardening guide |
| **Architecture Diagram** | [`docs/nexvision-architecture.drawio`](docs/nexvision-architecture.drawio) | Full system architecture (draw.io) |
| **VOD Streaming Diagram** | [`docs/vod-streaming-diagram.drawio`](docs/vod-streaming-diagram.drawio) | HLS streaming flow (draw.io) |

---

## Project Structure

```
oneviosn-iptv-v8.9/
│
├── app.py                    # Main Flask application (~8000 lines)
├── db_mysql.py               # MySQL compatibility wrapper (sqlite3 API)
├── cache_setup.py            # Redis/Flask-Caching configuration
├── wsgi.py                   # Gunicorn production entry point
├── gunicorn.conf.py          # Gunicorn worker configuration
├── requirements_prod.txt     # Production Python dependencies
├── .env.example              # Environment variables template
├── nexvision.db              # Main SQLite database (dev only)
├── vod.db                    # VOD SQLite database (dev only)
│
├── tv/
│   └── index.html            # Guest TV client (single-page app)
│
├── admin/
│   └── index.html            # Staff admin panel (single-page app)
│
├── nginx/
│   └── nexvision.conf        # Nginx virtual host configuration
│
├── ffmpeg/
│   └── bin/                  # FFmpeg binaries (Windows dev)
│       ├── ffmpeg.exe
│       ├── ffprobe.exe
│       └── *.dll
│
├── videos/                   # Source MP4 video files
├── hls/                      # Transcoded HLS segments
│   └── {video_id}/
│       ├── master.m3u8
│       ├── 480p/
│       ├── 720p/
│       └── 1080p/
├── thumbnails/               # Auto-generated VOD cover images
├── uploads/                  # Admin-uploaded images (slides, logos)
│
├── docs/
│   ├── SOB-System-Operations-Book.md
│   ├── Deployment-Procedure.md
│   ├── Server-Hardening-Procedure.md
│   ├── nexvision-architecture.drawio
│   └── vod-streaming-diagram.drawio
│
└── nexvision-apk/            # Android APK project
    └── app/src/main/java/com/nexvision/iptv/
        ├── MainActivity.java         # WebView host
        ├── NexVisionBridge.java      # JS ↔ Java interface
        └── VLCPlayerActivity.java    # Native VLC player
```

---

## Quick Troubleshooting

| Problem | Solution |
|---|---|
| VOD won't play on phone/APK | Restart Flask — `stream_url` auto-corrects per request |
| TV client blank screen | Check Flask/Nginx is running |
| HLS buffering | Increase `--network-caching` in VLC or check server disk I/O |
| Birthday not showing | Check server timezone matches hotel timezone |
| RSS ticker not updating | `redis-cli FLUSHALL` to clear stale cache |
| Admin panel 403 | Check admin PIN in Settings |
| APK won't install | Enable "Install from unknown sources" in Android Settings |
| VOD transcoding stuck | Kill stuck FFmpeg: `ps aux \| grep ffmpeg && kill -9 PID` |

---

## 📖 Documentation

For detailed guides, see the [docs/](docs/) directory:

| Guide | Purpose |
|-------|---------|
| [docs/DEPLOYMENT-GUIDE.md](docs/DEPLOYMENT-GUIDE.md) | Production deployment step-by-step |
| [docs/NEXVISION-ARCHITECTURE.md](docs/NEXVISION-ARCHITECTURE.md) | System architecture deep dive |
| [docs/SOB-System-Operations-Book.md](docs/SOB-System-Operations-Book.md) | Operations manual for admins |
| [docs/API-INTEGRATION-CODE.md](docs/APP-INTEGRATION-CODE.md) | Custom API integration examples |
| [docs/STORAGE-QUICK-REFERENCE.md](docs/STORAGE-QUICK-REFERENCE.md) | Storage backend comparison |

---

## 🚀 GitHub Setup

### First-Time Setup (Clone & Run Locally)

```bash
# 1. Clone the repository
git clone https://github.com/your-username/nexvision.git
cd nexvision

# 2. Setup configuration (copy templates and edit)
cp .env.example .env
nano .env  # Add your database and API credentials

cp epg/.env.example epg/.env
nano epg/.env

# 3. Install dependencies
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

pip install -r requirements.txt

# 4. Run the application
python app.py
# Visit: http://localhost:5000
```

### Important Security Notes

- **Never commit `.env` files** - Always use `.env.example` templates
- **See [SECURITY.md](SECURITY.md)** for environment setup and best practices
- Database (`*.db`) and virtual environment (`venv/`) are ignored by `.gitignore`

---

## License

Proprietary — NexVision IPTV Platform.
For hotel internal use only. Not for redistribution.

---

*NexVision IPTV v8.9 — Built with Flask · Nginx · FFmpeg · libVLC*
*Last updated: 2026-03-20*
#   N e x V i s i o n - I P T V 
 
 