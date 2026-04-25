# NexVision IPTV Platform v8.10

> **Hotel-grade IPTV system** delivering Live TV, Video on Demand, Radio, Guest Messaging, RSS News Ticker, and Promo Slides — to TVs, phones, tablets, and Android APK.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start (Development)](#quick-start-development)
- [Quick Start (Docker)](#quick-start-docker)
- [Production Deployment](#production-deployment)
- [Automation & Monitoring](#automation--monitoring)
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
- FFmpeg
  - **Linux:** `sudo apt install ffmpeg -y`
  - **Windows:** bundled in `ffmpeg/bin/` (included in repo)

### 1. Install Dependencies
```bash
cd nexvision-iptv
pip install flask werkzeug feedparser requests
```

### 2. Run the Server
```bash
python run.py
```

### 3. Access the Interfaces
| Interface | URL |
|---|---|
| TV Client (guests) | http://localhost/ |
| Admin Panel (staff) | http://localhost/admin/ |
| VOD Dashboard | http://localhost/vod/ |

> **Default admin PIN:** Check `settings` table in `nexvision.db` after first run.

### 4. From Another Device (Phone/TV)
Find your machine's IP address:
```bash
# Windows
ipconfig

# Linux/Mac
ip a
```

Access from phone/TV: `http://YOUR_IP/`

---

## Quick Start (Docker)

If you want one-command local deployment:

1. Ensure Docker and Docker Compose are installed.
2. Create your environment file:

```bash
cp .env.example .env
```

3. Build and run:

```bash
docker compose up -d --build
```

4. Open:
- TV Client: http://localhost/
- Admin Panel: http://localhost/admin/
- VOD Dashboard: http://localhost/vod/

Container files:
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

---

## Production Deployment

For a production environment serving 500+ concurrent users:

```bash
# Full step-by-step guide
docs/DEPLOYMENT-GUIDE.md
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

## Automation & Monitoring

### Daily M3U Health Check (GitHub Actions)

This repository includes a scheduled workflow:
- Workflow file: `.github/workflows/m3u-health-check.yml`
- Script: `scripts/check_m3u_health.py`
- Status output: `monitoring/m3u-last-checked.json`

Schedule:
- Runs daily at 02:15 UTC
- Can also be started manually from the Actions tab

Required repository secret:
- `M3U_HEALTHCHECK_URL` (your M3U playlist URL)

### HLS Playback Optimization

The TV player includes adaptive HLS handling with improved resilience:
- Uses hls.js adaptive quality selection for compatible browsers
- Adds network/media error recovery before declaring fatal playback failure
- Falls back to native HLS where available (for example, Safari/iOS)

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
| `POST` | `/api/rooms/register` | Register device by room/screen number, returns room token |
| `GET` | `/api/auth/login` | Admin login (username + password), returns JWT — **admin panel only** |

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

The NexVision Android app is a native Kotlin IPTV client with a **libVLC 3.6** video player. It connects directly to the NexVision REST API — no WebView, no hardcoded server URLs.

### Building the APK

**Option 1 — Android Studio (recommended, on your PC/Mac)**
1. Install [Android Studio](https://developer.android.com/studio)
2. Open the `nexvision-apk/` folder
3. Wait for Gradle sync → **Build → Build APK(s)**
4. Output: `app/build/outputs/apk/debug/app-debug.apk`

**Option 2 — Command line on the Linux server**

The Android SDK is already installed on the server at `/home/a13/android-sdk`.

```bash
cd nexvision-apk

# Build debug APK (SDK path is set in local.properties)
ANDROID_HOME=/home/a13/android-sdk ./gradlew assembleDebug

# Output (~91MB)
app/build/outputs/apk/debug/app-debug.apk
```

To avoid typing `ANDROID_HOME` every time, add to `~/.bashrc`:

```bash
export ANDROID_HOME=/home/a13/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools
```

**Setting up Android SDK from scratch (if needed)**

```bash
# 1. Download command-line tools
mkdir -p ~/android-sdk/cmdline-tools
cd /tmp
curl -O https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
unzip commandlinetools-linux-11076708_latest.zip -d /tmp/cmdtools-extract
mv /tmp/cmdtools-extract/cmdline-tools ~/android-sdk/cmdline-tools/latest

# 2. Set environment
export ANDROID_HOME=~/android-sdk
export PATH=$PATH:$ANDROID_HOME/cmdline-tools/latest/bin

# 3. Accept licenses and install SDK components
yes | sdkmanager --licenses
sdkmanager "platforms;android-34" "build-tools;34.0.0" "platform-tools"

# 4. Tell Gradle where the SDK is
echo "sdk.dir=$HOME/android-sdk" > /opt/nexvision/nexvision-apk/local.properties

# 5. Build
cd /opt/nexvision/nexvision-apk
./gradlew assembleDebug
```

> **Note:** `local.properties` is gitignored — each machine needs its own copy with the correct `sdk.dir` path.

### APK Features
- **Room/Screen registration** — enter server URL + room number (e.g. `101`), same as the browser TV client — no username or password needed
- **Auto mode detection** — detects hotel vs commercial mode from `/api/settings`, labels show "Room 101" or "Screen 101" accordingly
- **Channel list** — fetches live channels from `/api/channels` via `X-Room-Token` header, with live search/filter
- **VLCPlayerActivity** — native fullscreen video player (libVLC 3.6)
  - Hardware-accelerated decoding
  - 1.5-second network buffer
  - Sensor-based screen orientation
- **Session persistence** — room token stored in SharedPreferences, auto-reconnects on relaunch
- **Dark theme** — full black UI optimised for TV screens

### First-Time Use
1. Install the APK and open it
2. Enter your **Server URL** (e.g. `http://192.168.1.100`) and **Room/Screen number** (e.g. `101`)
3. Tap **Connect** — app registers with the server and loads channels automatically
4. Tap any channel to play it full-screen
5. On next launch, the app reconnects automatically — no re-entry needed

### Installing on Devices
1. Transfer `app-debug.apk` to Android device
2. Enable **Install from unknown sources** in Android settings
3. Open the APK file to install

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
| **Storage** | Multi-backend (Local, S3, etc.) | Flexible video/image storage |
| **Video** | FFmpeg | MP4 → HLS transcoding |
| **Streaming** | HLS (HTTP Live Streaming) | Adaptive bitrate video delivery |
| **TV Client** | Vanilla JS + CSS | Single-page TV interface |
| **Video Player** | hls.js 1.5 | Browser HLS playback |
| **Mobile Player** | libVLC Android 3.6 | APK native HLS player |
| **Android** | Kotlin + RecyclerView | Android APK native client |
| **Build** | Gradle 8.4 + Android SDK 34 | APK compilation |

## Core Application Files

| File | Layer | Lines | Purpose |
|---|---|---|---|
| `web/tv/index.html` | Web | ~500 | Guest TV client interface |
| `web/admin/index.html` | Web | ~2000 | Admin panel single-page app |
| `app/main.py` | App | ~8000 | Main Flask application with all routes and business logic |
| `app/wsgi.py` | App | ~50 | Gunicorn production entry point |
| `app/gunicorn.conf.py` | App | ~100 | Gunicorn worker and server configuration |
| `db/db_mysql.py` | DB | ~500 | MySQL compatibility layer providing sqlite3-like API |
| `db/cache_setup.py` | DB | ~200 | Redis caching configuration and utilities |
| `db/storage_backends.py` | DB | ~600 | Multi-storage backend implementation (Local, S3, FTP, etc.) |
| `db/vod_storage_admin.py` | DB | ~500 | VOD storage administration and management interface |

---

## Documentation

| Document | Location | Description |
|---|---|---|
| **System Operations Book** | [`docs/SOB-System-Operations-Book.md`](docs/SOB-System-Operations-Book.md) | Operations reference, monitoring, incident response |
| **Deployment Guide** | [`docs/DEPLOYMENT-GUIDE.md`](docs/DEPLOYMENT-GUIDE.md) | Step-by-step production deployment |
| **Server Hardening** | [`docs/Server-Hardening-Procedure.md`](docs/Server-Hardening-Procedure.md) | Security hardening guide |
| **Architecture Overview** | [`docs/NEXVISION-ARCHITECTURE.md`](docs/NEXVISION-ARCHITECTURE.md) | System architecture deep dive |
| **Storage Implementation** | [`docs/STORAGE-IMPLEMENTATION-README.md`](docs/STORAGE-IMPLEMENTATION-README.md) | Multi-storage backend details |
| **Storage Integration** | [`docs/STORAGE-INTEGRATION-GUIDE.md`](docs/STORAGE-INTEGRATION-GUIDE.md) | Storage backend setup and configuration |
| **Storage Quick Reference** | [`docs/STORAGE-QUICK-REFERENCE.md`](docs/STORAGE-QUICK-REFERENCE.md) | Storage backend comparison |
| **VOD Server Architecture** | [`docs/VOD-SERVER-ARCHITECTURE.md`](docs/VOD-SERVER-ARCHITECTURE.md) | VOD streaming architecture |
| **EPG Service** | [`docs/EPG-SERVICE.md`](docs/EPG-SERVICE.md) | Electronic Program Guide integration |
| **App Integration Code** | [`docs/APP-INTEGRATION-CODE.md`](docs/APP-INTEGRATION-CODE.md) | Custom API integration examples |
| **Architecture Diagram** | [`docs/nexvision-architecture.drawio`](docs/nexvision-architecture.drawio) | Full system architecture (draw.io) |
| **VOD Streaming Diagram** | [`docs/vod-server-architecture.drawio`](docs/vod-server-architecture.drawio) | HLS streaming flow (draw.io) |

---

## Project Structure

```
nexvision-iptv/
│
├── run.py                    # Development entry point
├── requirements_prod.txt     # Production Python dependencies
├── .env.example              # Environment variables template
├── nexvision.db              # Main SQLite database (dev only)
├── vod.db                    # VOD SQLite database (dev only)
│
├── web/                      # Frontend layer (static files)
│   ├── tv/
│   │   └── index.html        # Guest TV client
│   └── admin/
│       └── index.html        # Admin panel
│
├── app/                      # Application layer (Flask API)
│   ├── __init__.py
│   ├── main.py               # Main Flask application
│   ├── wsgi.py               # Gunicorn entry point
│   └── gunicorn.conf.py      # Gunicorn configuration
│
├── db/                       # Database layer
│   ├── __init__.py
│   ├── db_mysql.py           # MySQL compatibility wrapper
│   ├── cache_setup.py        # Redis caching configuration
│   ├── storage_backends.py   # Multi-storage backend implementation
│   └── vod_storage_admin.py  # VOD storage administration
│
├── videos/                   # Source MP4 video files
├── hls/                      # Transcoded HLS segments (generated)
├── thumbnails/               # VOD thumbnails (generated)
├── uploads/                  # Admin-uploaded images
├── nginx/
│   └── nexvision.conf        # Nginx configuration
├── scripts/                  # Utility scripts
├── docs/                     # Documentation
└── nexvision-apk/            # Android APK source
```
    ├── build.gradle
    └── app/src/main/
        ├── AndroidManifest.xml
        ├── kotlin/com/nexvision/iptv/
        │   ├── MainActivity.kt       # Login + channel list + search
        │   ├── VLCPlayerActivity.kt  # Native fullscreen VLC player
        │   ├── ChannelAdapter.kt     # RecyclerView adapter
        │   └── ApiClient.kt         # REST API calls (login, channels)
        └── res/layout/
            ├── activity_main.xml
            ├── activity_vlcplayer.xml
            ├── item_channel.xml
            └── dialog_server_config.xml
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
| [docs/APP-INTEGRATION-CODE.md](docs/APP-INTEGRATION-CODE.md) | Custom API integration examples |
| [docs/STORAGE-QUICK-REFERENCE.md](docs/STORAGE-QUICK-REFERENCE.md) | Storage backend comparison |

---

## 🚀 GitHub Setup

### First-Time Setup (Clone & Run Locally)

```bash
# 1. Clone the repository
git clone https://github.com/dalsuum/NexVision-IPTV.git
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
# Visit: http://localhost
```

### Important Security Notes

- **Never commit `.env` files** - Always use `.env.example` templates
- **See [SECURITY.md](SECURITY.md)** for environment setup and best practices
- Database (`*.db`) and virtual environment (`venv/`) are ignored by `.gitignore`

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

> The NexVision IPTV platform is intended for hotel/commercial internal use.
> Third-party components (libVLC, FFmpeg, Flask, etc.) retain their own respective licenses.

---

*NexVision IPTV v8.9 — Built with Flask · Nginx · FFmpeg · libVLC*
*Last updated: 2026-04-01*
