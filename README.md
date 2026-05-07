# NexVision IPTV Platform v8.22

> **Hotel-grade IPTV system** delivering Live TV, Video on Demand, Radio, Guest Messaging, RSS News Ticker, and Promo Slides — to TVs, phones, tablets, and Android APK.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start (Development)](#quick-start-development)
- [Production Deployment](#production-deployment)
- [Automation & Monitoring](#automation--monitoring)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Admin Panel Guide](#admin-panel-guide)
- [Android TV Box & Cast](#android-tv-box--cast)
- [Tech Stack](#tech-stack)
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
| 📅 **EPG / Programme Guide** | Current & upcoming programme info while watching live TV |
| 🎬 **Video on Demand** | Multi-quality HLS streaming (480p / 720p / 1080p) with inline search and favourites |
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
| 📅 EPG Management | Sync XMLTV guide from any URL, auto-match channels by tvg_id |
| 🎬 VOD Management | Upload MP4 → auto-transcoded to HLS by FFmpeg |
| 💬 Messaging | Broadcast to all rooms or specific rooms |
| 🎂 Birthdays | Auto birthday messages injected into guest inbox |
| 📰 RSS Feeds | Add/remove feeds, set global ticker appearance |
| 🖼 Promo Slides | Upload images, set display order and duration |
| 📢 **Ads Manager** | Pre-roll ads (image/video) before Live TV and VOD; skip-after timer, placement targeting |
| 🌍 **World Clock** | Multi-timezone clock screen; IANA timezone chips configured by admin |
| ⏰ **Alarms** | Hotel-wide alarm scheduler — fires on all active TV screens at scheduled time with sound |
| 🏨 **PMS Integration** | Connect to hotel PMS (Oracle FIAS, GRMS, third-party); guest welcome overlay with name, check-in/out times and welcome music — see [PMS_INTEGRATION.md](PMS_INTEGRATION.md) |
| 🎨 Navigation | Customise menu items, icons, order |
| ⚙ Settings | Hotel name, logo, feature toggles per room type |
| 🏠 Rooms | Create rooms, assign packages, generate access tokens |
| 📦 Packages | Bundle VOD content into subscription packages |

---

## Changelog

### v8.22 (2026-05-03)
- **New:** Series Favourites — heart button on every series tile and in the series detail view; favourites persisted to `localStorage` (`nv_fav_series`); state restored on page load
- **Fix:** Cast VOD — tapping the cast button while no Chromecast session is active now correctly queues the VOD (`_pendingVod`) and casts it as soon as the session connects, instead of auto-casting the currently playing live channel; new `CastMgr.requestSessionForVod()` method added

### v8.21 (2026-05-01)
- **New:** PMS Integration — admin can enable a hotel PMS connection (Oracle FIAS, GRMS, or third-party); settings include PMS host, port, username, password
- **New:** Guest Info fields on rooms — `guest_name`, `checkin_time`, `checkout_time` stored per room; editable in Rooms admin panel; returned by `POST /api/rooms/register`
- **New:** Guest Welcome overlay — on first load after registration, a full-screen welcome screen shows hotel name, guest name, and check-in/out times; auto-dismisses after 12 seconds or on any key/tap; shown once per browser session (`sessionStorage`)
- **New:** Welcome music — optional audio URL played during the guest welcome overlay; configurable in Settings → Guest Info & PMS
- **Fix:** Home screen EPG cards — when EPG entries reference channel IDs not in the initial channel list (e.g. large playlists > 3000 channels), missing channels are now fetched individually so EPG "Now/Next" cards always render

### v8.20 (2026-05-01)
- **New:** World Clock TV screen — multi-timezone card display; admin configures IANA timezone chips via Clock & Alarm panel; city names and day/night indicator per card
- **New:** Alarm Manager — admin creates alarms (label, time HH:MM, days: daily or weekday selection, sound type); alarms fire on all active TV screens simultaneously via a full-screen overlay with dismiss button; Web Audio engine, no extra hardware required
- **New:** `app/blueprints/clock_alarm.py` + `app/services/clock_alarm_service.py` — `/api/alarms/*`
- **New:** `alarms` table added to DB; `worldclock_zones` and `alarm_enabled` settings keys
- **New:** `clock` / "World Clock" added as a system nav item (disabled by default, orderable in Navigation Menu)
- **Improved:** EPG API — `?hours=N` param controls look-ahead window (default 48h); response now includes `channel_name` via JOIN; upcoming-entries filter applied by default when no `date` is given
- **Improved:** Packages API — `select_all_channels` flag assigns every channel in one query; response now includes `channel_ids`, `vod_ids`, `radio_ids` arrays and `radio_count`
- **Fix:** Bulk-delete responses across channel, vod, radio, room services now return consistent `{"ok": true, "deleted": N}` shape
- **Fix:** `weather_city` setting added to `init_db()` defaults
- **New:** Admin Settings page — dedicated Weather section with city input

### v8.19 (2026-05-01)
- **New:** Cast QR — admin toggle, configurable corner/display mode (home, screensaver, both); QR badge on TV home screen and screensaver

### v8.18 (2026-05-01)
- **New:** Ads Manager — admin panel section for managing pre-roll advertisement overlays
  - Image ads auto-dismiss after a configurable duration; video ads play to completion
  - Configurable skip-after timer (0 = unskippable)
  - Placement targeting: VOD player only, Live TV only, or Both
  - Click-action URL per ad (opens hotel page or external link)
  - Card-based admin UI with image preview, status/placement badges
- **New:** TV client pre-roll ad overlay — `showAdOverlay(placement)` shown before Live TV (HTTP streams only) and VOD playback; ads fetched and cached in `_adsCache` on startup
- **New:** Per-user city/region weather — guests can pick their city from a world-city dropdown; preference stored per room token
- **New:** `ads` table added to `nexvision.db` schema via `init_db()` / `migrate_db()` in `app/main.py`
- **New:** `app/blueprints/ads.py` — REST handlers for `/api/ads/*`
- **New:** `app/services/ad_service.py` — CRUD + reorder logic for ads

### v8.17 (2026-05-01)
- **New:** VOD Search — inline live-search box in the VOD header; results filter in real time as the guest types
- **New:** VOD Favourites — heart button on every movie tile; favourites persisted to `localStorage` (`nv_fav_movies`); filterable via "Favourites" chip next to genre filters
- **Fix:** `app/wsgi.py` — wrapped `init_db()` in an `fcntl.LOCK_EX` file lock so only one Gunicorn worker initialises the database when multiple workers start simultaneously (prevents race-condition corruption on restart)
- **Fix:** `app/hooks.py` — room-token heartbeat `UPDATE` wrapped in `try/except`; a transient DB error no longer aborts the entire request
- **Fix:** `api()` in `tv.js` — non-2xx HTTP responses now return `null` instead of throwing a JSON parse error, preventing unhandled promise rejections across the TV client
- **Style:** Dark color palette slightly lightened (`--bg` #09090f → #0b0b14 etc.) for better contrast on OLED displays
- **Style:** Extensive light-mode CSS overhaul — elements outside `.screen` (screensaver, header buttons, nav) now correctly inherit light-mode variables; removed hardcoded dark overrides that were leaking into light theme

### v8.16 (2026-05-01)
- **Fix:** Navigation Menu admin panel was always rendering an empty list after the blueprint migration
  - `list_items_admin()` was returning a plain array but the admin JS expected `{items, position, style}` — so `data.items` was always `undefined`
  - Fixed: service now returns the full object shape (items + navbar position + navbar style) to match what the UI consumes
- **Fix:** "Save Order" on the Navigation Menu page was silently failing
  - JS was sending `{order: [{id, sort_order}]}` but the API expected `{ids: [1,2,3]}` — mismatch left sort order unchanged
  - Fixed: payload now sends the plain ID array the service iterates over

### v8.15 (2026-05-01)
- **Refactor:** Split monolithic `app.py` into modular blueprint + service architecture
  - `app/blueprints/` — one file per domain (auth, channels, vod, messages, birthdays, devices, cast, packages, rooms, reports, stats, …)
  - `app/services/` — business logic and DB queries isolated from HTTP layer
  - `app/config.py`, `app/extensions.py`, `app/decorators.py`, `app/hooks.py` — shared utilities
- **Bug fixes after refactor:**
  - `birthday_service`: fixed column names (`guest_name`, `message` — was `name`, `note`)
  - `cast_service`: fixed insert to use `channel_id`; removed non-existent `bytes_sent` / `content_type` / `content_id`
  - `device_service`: fixed heartbeat INSERT and `list_devices` query to match actual `devices` schema (no `room_id`/`ip_address`)
  - `package_service`: fixed all queries from `packages` → `content_packages` (correct table name)
  - `room_service`: removed non-existent `active` column from INSERT; fixed `packages` → `content_packages` in package queries
  - `vod_service`: fixed column names (`poster`, `stream_url` — was `poster_url`, `video_url`)
  - `report_service`: fixed `devices_report` to query actual `devices` columns without bad JOIN

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

### Application Code Structure (v8.15+)
```
app/
├── __init__.py          # Application factory (create_app)
├── config.py            # Config class + filesystem paths
├── extensions.py        # get_db(), get_vod_db(), cache singleton
├── decorators.py        # @admin_required, @token_required, @require_api_key
├── hooks.py             # before_request hooks (room presence, TV redirect)
├── main.py              # init_db(), migrate_db(), vod_init_db() helpers
├── wsgi.py              # Production Gunicorn entry point
├── blueprints/          # One file per HTTP domain
│   ├── auth.py          # POST /api/auth/login
│   ├── channels.py      # /api/channels/*
│   ├── vod_api.py       # /api/vod/*
│   ├── messages.py      # /api/messages/*
│   ├── birthdays.py     # /api/birthdays/*
│   ├── devices.py       # /api/devices, /api/device/heartbeat
│   ├── cast.py          # /api/cast/*
│   ├── packages.py      # /api/packages/*, /api/vip/*
│   ├── rooms.py         # /api/rooms/*
│   ├── stats.py         # /api/stats/*
│   ├── reports.py       # /api/reports/*
│   ├── ads.py           # /api/ads/*
│   ├── clock_alarm.py   # /api/alarms/*
│   └── …               # radio, rss, slides, nav, settings, epg, prayer, …
└── services/            # Business logic + SQL — no Flask imports except jsonify
    ├── auth_service.py
    ├── channel_service.py
    ├── vod_service.py
    ├── message_service.py
    ├── birthday_service.py
    ├── device_service.py
    ├── cast_service.py
    ├── package_service.py
    ├── room_service.py
    ├── stat_service.py
    ├── report_service.py
    ├── ad_service.py
    ├── clock_alarm_service.py
    └── …
```

See [`nginx/nexvision.conf`](nginx/nexvision.conf) for the full Nginx configuration.

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
pip install -r requirements_prod.txt
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

## Production Deployment

For a production environment serving 500+ concurrent users:

```bash
# Full step-by-step guide
MULTICLOUD_DEPLOYMENT.md
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

# 4. Configure Nginx
sudo cp nginx/nexvision.conf /etc/nginx/sites-available/nexvision
sudo ln -s /etc/nginx/sites-available/nexvision /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 5. Start services (DB is initialised automatically on first start)
sudo systemctl enable --now nexvision redis-server mysql nginx
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
| `GET` | `/api/ads` | Active ads for a placement (`?placement=vod\|live\|both`) |
| `GET` | `/api/alarms/active` | Active alarms for TV client alarm checker |
| `GET` | `/api/epg/<channel_id>` | EPG entries (`?hours=48` window, includes `channel_name`) |
| `POST` | `/api/rooms/register` | Register device; response includes `guest_name`, `checkin_time`, `checkout_time` |
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
| `GET/POST/PUT/DELETE` | `/api/ads` | Manage ads (Ads Manager) |
| `GET/POST/PUT/DELETE` | `/api/alarms` | Manage alarms (Clock & Alarm) |
| `GET/POST` | `/api/settings` | Update hotel settings |
| `GET/POST` | `/api/rooms` | Manage hotel rooms |

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

## Android TV Box & Cast

### Registering an Android TV Box

Before a TV box can show the guest interface, the room must exist in the admin panel.

**Step 1 — Admin: create the room**
1. Go to **Admin Panel → Rooms**
2. Click **Add Room**, enter the room number (e.g. `101`) and optionally a TV name
3. Save — the room is now ready to accept a device

**Step 2 — TV box: open the NexVision TV app**

| Client | How to open |
|---|---|
| **Browser (any device)** | Navigate to `http://<server-ip>/` on the TV browser |
| **Android APK** | Install the NexVision APK and launch it |
| **Android TV / Google TV** | Install the APK via sideload or open in TV browser |

**Step 3 — Enter room number on the registration screen**

The app shows a full-screen registration prompt with an on-screen numpad the first time it runs (or after the token is cleared).

1. Use the numpad (or remote/keyboard) to type the room number
2. Press **Confirm**
3. The app registers with the server and immediately loads the guest interface

> The token is saved in the device's local storage. The TV will not need to re-register unless you clear the browser data or reinstall the APK.

**Step 4 — Verify in admin**

Go to **Admin Panel → Rooms** — the room will show as **Online** within a few seconds.

---

### Android APK

The NexVision Android APK provides a native experience with these differences from the browser:

| Feature | APK behaviour |
|---|---|
| **VOD playback** | Handed off to the built-in VLC player for smooth hardware-decoded video |
| **Live TV** | Played in-browser via hls.js (same as web) |
| **Registration** | Same numpad flow as browser |
| **Stream URLs** | Auto-corrected to the server IP at request time — no manual config needed |

---

### Using Cast (Chromecast)

NexVision supports casting Live TV channels to any Chromecast device on the same network.

**Requirements**
- A **Chromecast** or **Chromecast-enabled TV** on the same WiFi as the server
- The guest must be using **Chrome browser** or the **Android app** (Cast SDK only loads in these)

**How to cast a Live TV channel**
1. Open the TV app at `http://<server-ip>/` in Chrome or the Android app
2. Start playing any Live TV channel
3. A **cast button** (📡) appears in the player controls when a Chromecast is detected on the network
4. Tap the cast button → a device picker appears
5. Select your Chromecast — the stream starts playing on the TV within a few seconds
6. To stop casting, tap the cast button again and select **Stop casting**

**How to cast a VOD movie**
1. Open any movie in the VOD player
2. Tap the **cast button** (📡) in the player controls
3. If no session is active, a device picker opens — the movie is queued and starts on the Chromecast as soon as you connect
4. If a session is already active, the movie starts immediately on the Chromecast

**Cast receiver app ID:** `CC1AD845`
> This is the registered Google Cast receiver ID for NexVision. It is already built into the app — no configuration needed.

**Limitations**
- UDP/multicast IPTV streams cannot be cast (HLS streams only)
- Cast requires the Chrome browser or Android app — it does not work in Safari, Firefox, or the TV's built-in browser
- The Chromecast and server must be on the same network segment

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend** | Python 3 + Flask | Web application + REST API |
| **WSGI** | Gunicorn + gevent | Async production server |
| **Proxy** | Nginx | Static files, HLS, rate limiting |
| **Cache** | Redis + Flask-Caching | Hot endpoint caching |
| **Database** | SQLite WAL (dev) / MySQL (prod) | All application data |
| **Storage** | Multi-backend (Local, S3, etc.) | Flexible video/image storage |
| **Video** | FFmpeg | MP4 → HLS transcoding |
| **Streaming** | HLS (HTTP Live Streaming) | Adaptive bitrate video delivery |
| **EPG** | Node.js + PM2 (iptv-org/epg) | Programme guide grabber & XML server |
| **TV Client** | Vanilla JS + CSS | Single-page TV interface |
| **Video Player** | hls.js 1.5 | Browser HLS playback |

## Core Application Files

| File | Layer | Lines | Purpose |
|---|---|---|---|
| `web/tv/index.html` | Web | ~380 | Guest TV client (HTML structure) |
| `web/tv/tv.css` | Web | ~1480 | Guest TV client styles |
| `web/tv/tv.js` | Web | ~4290 | Guest TV client application logic |
| `web/tv/sw-cleanup.js` | Web | ~30 | Service worker cleanup on VOD paths |
| `web/admin/index.html` | Web | ~92 | Admin panel (HTML structure) |
| `web/admin/admin.css` | Web | ~261 | Admin panel styles |
| `web/admin/admin.js` | Web | ~3841 | Admin panel application logic |
| `web/cast/receiver.html` | Web | ~77 | Chromecast receiver (HTML structure) |
| `web/cast/receiver.css` | Web | ~194 | Cast receiver styles |
| `web/cast/receiver.js` | Web | ~254 | Cast receiver HLS + CAF logic |
| `app/main.py` | App | ~700 | Flask init, DB helpers (create_app, init_db, migrate_db) |
| `app/wsgi.py` | App | ~50 | Gunicorn production entry point |
| `app/gunicorn.conf.py` | App | ~100 | Gunicorn worker and server configuration |
| `db/db_mysql.py` | DB | ~500 | MySQL compatibility layer providing sqlite3-like API |
| `db/cache_setup.py` | DB | ~200 | Redis caching configuration and utilities |
| `db/storage_backends.py` | DB | ~600 | Multi-storage backend implementation (Local, S3, FTP, etc.) |
| `db/vod_storage_admin.py` | DB | ~500 | VOD storage administration and management interface |

---

## Project Structure

```
nexvision-iptv/
│
├── run.py                    # Development entry point
├── requirements_prod.txt     # Production Python dependencies
├── .env.example              # Environment variables template
├── nexvision.db              # Main SQLite database (dev only)
│
├── web/                      # Frontend layer (static files)
│   ├── tv/
│   │   ├── index.html        # Guest TV client (HTML structure)
│   │   ├── tv.css            # TV client styles
│   │   ├── tv.js             # TV client application logic
│   │   ├── sw-cleanup.js     # Service worker cleanup on VOD paths
│   │   ├── manifest.json     # PWA manifest
│   │   └── sw.js             # Service worker
│   ├── admin/
│   │   ├── index.html        # Admin panel (HTML structure)
│   │   ├── admin.css         # Admin panel styles
│   │   └── admin.js          # Admin panel application logic
│   └── cast/
│       ├── receiver.html     # Chromecast receiver (HTML structure)
│       ├── receiver.css      # Cast receiver styles
│       └── receiver.js       # Cast receiver HLS + CAF logic
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
├── vod/                      # VOD storage
│   ├── vod.db                # VOD SQLite database (dev only)
│   ├── videos/               # Source MP4 video files
│   ├── hls/                  # Transcoded HLS segments (generated)
│   ├── thumbnails/           # VOD thumbnails (generated)
│   ├── uploads/              # VOD-uploaded videos (staging)
│   └── data/                 # Storage backend state
│
├── uploads/                  # Admin-uploaded images (logos, slides)
├── epg/                      # EPG service (Node.js + PM2)
│   ├── pm2.config.js         # PM2 process config (serve + grab)
│   ├── channels.xml          # Channel list for iptv-org grabber
│   └── public/
│       └── guide.xml         # Generated XMLTV output (served on :3000)
├── android/                  # Android TV client source
├── nginx/
│   └── nexvision.conf        # Nginx configuration
├── scripts/
│   └── check_m3u_health.py   # Daily M3U health check
└── monitoring/
    └── m3u-last-checked.json # Latest health check result
```

---

## EPG / Programme Guide

The EPG service is a Node.js process (PM2) that serves `guide.xml` on port 3000. The Flask app syncs EPG data from any XMLTV source into the database.

### Architecture

```
External XMLTV URL  ──→  Flask /api/epg/sync-now  ──→  nexvision.db (epg_entries)
                                                              │
                         Flask /api/epg/generate-guide  ──→  epg/public/guide.xml
                                                              │
                         PM2 epg-serve  ──────────────→  :3000/guide.xml  (TV clients)
```

### Setup (first time)

```bash
# 1. Start the EPG service
cd /opt/nexvision/epg
npx pm2 start pm2.config.js
npx pm2 save

# 2. Enable PM2 on system boot
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u $USER --hp $HOME
# Run the output command

# 3. In Admin → EPG / Schedule:
#    - Enter your IPTV provider's XMLTV URL in "EPG Source URL"
#    - Click "Sync Now"  → imports EPG entries into the database
#    - Click "Generate guide.xml"  → exports to epg/public/guide.xml
```

### EPG Source URL

Use your IPTV provider's XMLTV feed (typically provided alongside the M3U URL):
```
http://your-provider.com/xmltv.php?username=xxx&password=xxx
```

The sync matches channels by **tvg_id** first (most accurate), then by display name. Channels in the database must have `tvg_id` values matching the channel IDs in the XMLTV file.

### PM2 Process Summary

| Process | Purpose | Schedule |
|---|---|---|
| `epg-serve` | Static file server on :3000 | Always on |
| `epg-grab` | Grabs EPG via iptv-org grabber | Every 6 hours (requires `channels.xml` with `site` attributes) |
| `epg-grab-startup` | One-shot grab on startup | Once |

> **Note:** `epg-grab` only works if `epg/channels.xml` has `site` and `site_id` attributes configured per channel. For most setups, using the "Sync Now" button with an external XMLTV URL is simpler.

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
| VOD transcoding stuck | Kill stuck FFmpeg: `ps aux \| grep ffmpeg && kill -9 PID` |
| EPG "Sync failed: database is locked" | Fixed in v8.12 — SQLite WAL mode + batch inserts. Run `sudo systemctl reload nexvision` |
| EPG Sync Now does nothing | The EPG Source URL must be an external XMLTV URL from your provider, not `localhost:3000/guide.xml` |
| EPG service not running | `cd /opt/nexvision/epg && npx pm2 start pm2.config.js && npx pm2 save` |
| EPG 0 matches after sync | Channel `tvg_id` values in the DB must match channel IDs in the XMLTV file |
| VOD page logo not showing custom branding | Fixed in v8.13 — corrected element IDs so `applyPublicBranding()` can target the logo and badge on `/vod/` |
| Cast receiver CSS/JS not loading | Ensure `sudo systemctl restart nexvision` has been run after v8.14 upgrade — the new `/cast-receiver/<filename>` static route must be active |

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

pip install -r requirements_prod.txt

# 4. Run the application
python run.py
# Visit: http://localhost:5000
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

*NexVision IPTV v8.22 — Built with Flask · Nginx · FFmpeg · hls.js · Node.js EPG*
*Last updated: 2026-05-07*
