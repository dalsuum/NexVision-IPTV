# NexVision IPTV — Developer Guide

> Version: v8.17 — Last updated: 2026-05-01  
> Flask + Gunicorn + Nginx · Blueprint / Service architecture

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Project Structure](#2-project-structure)
3. [Application Factory](#3-application-factory)
4. [Blueprint Layer](#4-blueprint-layer)
5. [Service Layer](#5-service-layer)
6. [Database Layer](#6-database-layer)
7. [Caching Layer](#7-caching-layer)
8. [Authentication & Decorators](#8-authentication--decorators)
9. [Complete API Reference](#9-complete-api-reference)
10. [Database Schema](#10-database-schema)
11. [Configuration Reference](#11-configuration-reference)
12. [Frontend Architecture](#12-frontend-architecture)
13. [Adding New Features](#13-adding-new-features)
14. [Running & Deployment](#14-running--deployment)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  CLIENTS                                                          │
│  📺 TV Browser (guest)  📱 Android APK  🔧 Admin Panel           │
└───────────────────────────────┬──────────────────────────────────┘
                                │ HTTP/HTTPS (port 80/443)
┌───────────────────────────────▼──────────────────────────────────┐
│  NGINX — reverse proxy, static files, HLS cache, rate limiting   │
│  /          → web/tv/        (guest SPA, try_files)              │
│  /admin/    → web/admin/     (staff SPA, try_files)              │
│  /api/      → Gunicorn       (proxied, 120s timeout)             │
│  /vod/      → Gunicorn       (VOD API + HLS, 300s timeout)       │
│  /vod/hls/*/*.ts → X-Accel  (kernel sendfile, 1h cache)         │
│  /uploads/  → disk           (static images, 7d cache)           │
└───────────────────────────────┬──────────────────────────────────┘
                                │ Unix socket /run/nexvision/gunicorn.sock
┌───────────────────────────────▼──────────────────────────────────┐
│  GUNICORN (gevent workers, 1000 conn/worker)                      │
│  Entry: app/wsgi.py → create_app()                               │
│                                                                   │
│  Flask app                                                        │
│  ├── 24 Blueprints (/api/*, /vod/*, /admin/, /, ...)             │
│  │   └── Thin HTTP handlers → call service functions             │
│  └── 24 Services (business logic + SQL queries)                   │
└─────────────────┬───────────────────────────┬────────────────────┘
                  │                           │
┌─────────────────▼──────┐  ┌────────────────▼───────────────────┐
│  Redis (cache, 6379)   │  │  SQLite WAL (dev) / MySQL (prod)   │
│  Prefix: nv:           │  │  nexvision.db + vod/vod.db         │
│  TTLs: 30s – 600s      │  │  33 tables                         │
└────────────────────────┘  └────────────────────────────────────┘
                                           │
┌──────────────────────────────────────────▼─────────────────────┐
│  DISK STORAGE                                                    │
│  uploads/     ← admin-uploaded images, logos, slide images      │
│  vod/videos/  ← source MP4 files                                │
│  vod/hls/     ← transcoded HLS segments (auto-generated)        │
│  vod/thumbnails/ ← VOD thumbnails (auto-generated)              │
└────────────────────────────────────────────────────────────────┘
```

### Request Lifecycle

1. Client sends HTTP request → Nginx
2. Nginx serves static files directly (web/tv/, web/admin/, uploads/)
3. For `/api/*` and `/vod/*`: Nginx proxies to Gunicorn via Unix socket
4. Gunicorn routes to the correct Flask Blueprint
5. Blueprint handler calls one or more service functions
6. Service function checks Redis cache → hit: return cached value / miss: query DB
7. Response flows back through Gunicorn → Nginx → Client

---

## 2. Project Structure

```
/opt/nexvision/
│
├── run.py                        # Dev entry point (python run.py)
├── requirements_prod.txt         # Pinned production dependencies
├── .env                          # Runtime secrets (never commit)
├── nexvision.db                  # SQLite database (dev/WAL mode)
│
├── app/                          # Flask application package
│   ├── __init__.py               # Application factory: create_app()
│   ├── config.py                 # Config class — constants + env vars
│   ├── extensions.py             # get_db(), cache singleton, TTLs
│   ├── decorators.py             # @admin_required, @token_required, @require_api_key
│   ├── hooks.py                  # before_request hooks (presence, TV redirect)
│   ├── main.py                   # DB init/migration helpers
│   ├── wsgi.py                   # Production Gunicorn entry point
│   ├── gunicorn.conf.py          # Gunicorn worker / socket config
│   │
│   ├── blueprints/               # HTTP layer — one file per domain
│   │   ├── __init__.py           # Exports all blueprint objects
│   │   ├── admin_ui.py           # Static UI serving (/admin/, /cast-receiver/, /)
│   │   ├── auth.py               # POST /api/auth/login
│   │   ├── users.py              # /api/users/*
│   │   ├── channels.py           # /api/channels/*
│   │   ├── devices.py            # /api/devices, /api/device/heartbeat
│   │   ├── rooms.py              # /api/rooms/*
│   │   ├── stats.py              # /api/stats/*
│   │   ├── content.py            # /api/content/*
│   │   ├── skins.py              # /api/skins/*, /api/skin
│   │   ├── messages.py           # /api/messages/*
│   │   ├── slides.py             # /api/slides/*
│   │   ├── settings_bp.py        # /api/settings/*
│   │   ├── packages.py           # /api/packages/*, /api/vip/*
│   │   ├── vod_api.py            # /api/vod/* (NexVision catalogue)
│   │   ├── vod_server.py         # /vod/* (HLS streaming + VOD admin)
│   │   ├── birthdays.py          # /api/birthdays/*
│   │   ├── prayer.py             # /api/prayer/*
│   │   ├── radio.py              # /api/radio/*
│   │   ├── rss.py                # /api/rss/*
│   │   ├── nav.py                # /api/nav/*
│   │   ├── epg.py                # /api/epg/*
│   │   ├── cast.py               # /api/cast/*
│   │   ├── uploads.py            # /uploads/, /api/upload, /api/watch-event
│   │   ├── reports.py            # /api/reports/*
│   │   ├── media_groups.py       # /api/groups/*
│   │   ├── services_bp.py        # /api/services/* (guest services)
│   │   └── weather.py            # /api/weather/*
│   │
│   └── services/                 # Business logic — no Flask routing
│       ├── __init__.py           # Exports all service modules
│       ├── auth_service.py
│       ├── channel_service.py
│       ├── content_service.py
│       ├── device_service.py
│       ├── birthday_service.py
│       ├── cast_service.py
│       ├── epg_service.py
│       ├── hotel_service.py
│       ├── media_group_service.py
│       ├── message_service.py
│       ├── nav_service.py
│       ├── package_service.py
│       ├── prayer_service.py
│       ├── radio_service.py
│       ├── report_service.py
│       ├── room_service.py
│       ├── rss_service.py
│       ├── settings_service.py
│       ├── skin_service.py
│       ├── slide_service.py
│       ├── stat_service.py
│       ├── tv_service.py
│       ├── upload_service.py
│       ├── user_service.py
│       ├── vod_server_service.py
│       ├── vod_service.py
│       └── weather_service.py
│
├── db/                           # Database layer
│   ├── db_mysql.py               # MySQL compat wrapper (sqlite3 interface)
│   ├── cache_setup.py            # Redis / Flask-Caching singleton
│   ├── storage_backends.py       # Multi-backend (Local, S3, FTP, Azure)
│   └── vod_storage_admin.py      # VOD storage management UI routes
│
├── web/                          # Frontend (static files — served by Nginx)
│   ├── tv/                       # Guest TV client SPA
│   │   ├── index.html
│   │   ├── tv.css
│   │   ├── tv.js
│   │   ├── sw.js                 # Service worker
│   │   └── manifest.json         # PWA manifest
│   ├── admin/                    # Admin panel SPA
│   │   ├── index.html
│   │   ├── admin.css
│   │   └── admin.js
│   └── cast/                     # Chromecast receiver
│       ├── receiver.html
│       ├── receiver.css
│       └── receiver.js
│
├── nginx/
│   └── nexvision.conf            # Full Nginx configuration
│
├── epg/                          # EPG service (Node.js + PM2)
│   ├── pm2.config.js
│   ├── channels.xml
│   └── public/guide.xml          # Generated XMLTV output
│
├── vod/                          # VOD runtime storage
│   ├── vod.db                    # VOD SQLite database
│   ├── videos/                   # Source MP4 files
│   ├── hls/                      # Transcoded HLS (generated)
│   └── thumbnails/               # Thumbnails (generated)
│
├── uploads/                      # Admin-uploaded images (logos, slides)
└── scripts/
    └── check_m3u_health.py       # GitHub Actions M3U health check
```

---

## 3. Application Factory

`app/__init__.py` exports `create_app(config_class=Config)`.

```python
from app import create_app
app = create_app()
```

What `create_app()` does in order:

1. Instantiates `Flask(__name__)`
2. Loads `Config` class (reads `.env` via `python-dotenv`)
3. Configures CORS (exposes `Content-Range`, `Accept-Ranges` for Cast)
4. Calls `init_cache(app)` to attach Redis cache
5. Imports and registers all 24 blueprints
6. Calls `register_hooks(app)` to attach `before_request` handlers

### Entry Points

| File | Used by | Details |
|---|---|---|
| `run.py` | Development | `python run.py` — debug mode, port 5000, auto-reloader |
| `app/wsgi.py` | Gunicorn | `--config app/gunicorn.conf.py app.wsgi:application` |

`wsgi.py` additionally:
- Acquires a file lock so only one worker runs `init_db()` + `migrate_db()`
- Calls `vod_init_db()` to set up the VOD SQLite schema

---

## 4. Blueprint Layer

### Convention

Every blueprint file follows this pattern:

```python
from flask import Blueprint, request
from ..decorators import admin_required          # or token_required
from ..services import some_service

bp = Blueprint('domain_name', __name__, url_prefix='/api/domain')

@bp.route('', methods=['GET'])
@admin_required
def list_items():
    return some_service.list_items()

@bp.route('/<int:item_id>', methods=['PUT'])
@admin_required
def update_item(item_id):
    return some_service.update_item(item_id, request.json or {})
```

**Rules:**
- Blueprints contain **zero business logic** — only HTTP parsing and dispatch
- No direct DB access in blueprints
- Auth decorators go on the blueprint handler, not in the service
- All request body access via `request.json or {}` (never `request.form` for JSON APIs)

### Blueprint Registration

All blueprints are registered in `app/__init__.py`:

```python
from .blueprints import (
    admin_ui_bp, auth_bp, users_bp, channels_bp, devices_bp,
    rooms_bp, stats_bp, content_bp, skins_bp, messages_bp,
    slides_bp, settings_bp, packages_bp, vod_api_bp, vod_server_bp,
    birthdays_bp, prayer_bp, radio_bp, rss_bp, nav_bp, epg_bp,
    cast_bp, uploads_bp, reports_bp, media_groups_bp,
    services_bp, weather_bp
)

for bp in [admin_ui_bp, auth_bp, users_bp, ...]:
    app.register_blueprint(bp)
```

---

## 5. Service Layer

### Convention

Every service file is a flat module — plain functions, no classes:

```python
# app/services/example_service.py
from flask import jsonify
from ..extensions import get_db, invalidate_something

def list_items():
    conn = get_db()
    rows = conn.execute("SELECT * FROM items ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

def create_item(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO items (name, active) VALUES (?,?)",
        (d['name'], d.get('active', 1))
    )
    conn.commit()
    item = dict(conn.execute("SELECT * FROM items WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    invalidate_something()
    return jsonify(item), 201
```

**Rules:**
- Services return `flask.jsonify(...)` responses (or tuples with status code)
- Always close DB connections with `conn.close()` in a finally block or immediately after use
- Call cache invalidation helpers after any write operation
- Use `?` placeholders — never f-strings or `.format()` with user data

### Service → Blueprint import pattern

```python
# In blueprints/__init__.py
from . import channels            # Imports the blueprint module
from ..services import channel_service   # Used inside the module

# In blueprints/channels.py
from ..services import channel_service

@bp.route('', methods=['GET'])
def list_channels():
    # Extract query params, pass to service
    group_id = request.args.get('group_id', type=int)
    return channel_service.list_channels(group_id=group_id)
```

---

## 6. Database Layer

### 6.1 Connection Helper

`app/extensions.py` exports two connection factories:

```python
from app.extensions import get_db, get_vod_db

conn = get_db()          # Main DB (nexvision.db or MySQL)
conn = get_vod_db()      # VOD DB (vod/vod.db or MySQL nexvision_vod)
```

Both return a connection object with a `Row` factory (rows accessible as `dict(row)`).
SQLite connections use WAL mode for concurrent reads.

### 6.2 SQLite vs MySQL

Controlled by `USE_MYSQL=1` in `.env`. The MySQL wrapper (`db/db_mysql.py`)
translates SQLite syntax:

| SQLite syntax | MySQL equivalent |
|---|---|
| `?` placeholder | `%s` |
| `datetime('now')` | `NOW()` |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `INT AUTO_INCREMENT PRIMARY KEY` |
| `PRAGMA journal_mode=WAL` | `SELECT 1` (no-op) |

**Always write SQLite-style SQL** (`?` placeholders, `datetime()` for timestamps).
The wrapper handles the translation automatically.

### 6.3 Writing Queries

```python
conn = get_db()
try:
    # Read
    row = conn.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    # Write
    conn.execute(
        "UPDATE rooms SET room_number=?, tv_name=? WHERE id=?",
        (d['room_number'], d.get('tv_name', ''), rid)
    )
    conn.commit()
finally:
    conn.close()
```

### 6.4 DB Initialization

`app/main.py` contains:
- `init_db(conn)` — Creates all tables with `CREATE TABLE IF NOT EXISTS`
- `migrate_db(conn)` — Adds columns that were added after initial deploy
- `vod_init_db()` — Creates VOD database tables

These run automatically on startup via `wsgi.py`.

---

## 7. Caching Layer

### 7.1 Cache TTLs

| Cache | Key pattern | TTL | Invalidated on |
|---|---|---|---|
| Settings | `nv:settings` | 60s | Any `POST /api/settings` |
| Channels | `nv:channels*` | 30s | Channel create/update/delete |
| VOD | `nv:vod*` | 60s | VOD create/update/delete |
| Nav items | `nv:nav` | 120s | Nav create/update/delete/reorder |
| Slides | `nv:slides` | 60s | Slide create/update/delete |
| RSS | `nv:rss` | 300s | RSS feed create/update/delete |
| Weather | `nv:weather*` | 600s | N/A (external API, time-based) |

### 7.2 Using the Cache

```python
from ..extensions import cache, invalidate_channels, TTL_CHANNELS

# Cache a response
@cache.cached(timeout=TTL_CHANNELS, key_prefix='nv:channels')
def get_channel_list():
    ...

# Invalidate after a write
def delete_channel(cid):
    conn = get_db()
    conn.execute("DELETE FROM channels WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    invalidate_channels()   # <-- always call after write
    return jsonify({'ok': True})
```

### 7.3 Manual Cache Flush

```bash
# Flush all NexVision cache keys
redis-cli KEYS "nv:*" | xargs redis-cli DEL

# Flush a specific key
redis-cli DEL nv:settings
```

---

## 8. Authentication & Decorators

### 8.1 Available Decorators

| Decorator | File | Requires | Sets |
|---|---|---|---|
| `@admin_required` | decorators.py | JWT Bearer token, role admin/operator | `request.user` |
| `@token_required` | decorators.py | JWT Bearer token (any role) | `request.user` |
| `@require_api_key` | decorators.py | `X-API-Key` or `?api_key=` | — |

### 8.2 How Auth Works

**Admin JWT flow:**
```
POST /api/auth/login  {username, password}
  → auth_service.login()
  → bcrypt.verify(password, stored_hash)
  → jwt.encode({id, username, role, exp: now+24h}, SECRET_KEY, HS256)
  → {token: "eyJ..."}
```

All subsequent admin requests:
```
GET /api/channels
Authorization: Bearer eyJ...
  → @admin_required
  → jwt.decode(token, SECRET_KEY)
  → request.user = {id, username, role}
  → channel_service.list_channels()
```

**Room token flow:**
```
POST /api/rooms/register  {room_number: "101"}
  → room_service.room_register()
  → SELECT room_token FROM rooms WHERE room_number=?
  → {token: "3f8a2b9c-..."}
```

All subsequent guest requests:
```
GET /api/messages/active
X-Room-Token: 3f8a2b9c-...
  → message_service.get_active(room_token)
  → SELECT room_id FROM rooms WHERE room_token=?
  → Filter messages for this room
```

**VOD API key:**
```
POST /vod/api/upload
X-API-Key: <VOD_API_KEY from .env>
  → @require_api_key
  → Compare header/param against Config.VOD_API_KEY
```

### 8.3 Accessing the Authenticated User in a Handler

```python
from flask import request

@bp.route('/some-endpoint', methods=['POST'])
@admin_required
def my_handler():
    user = request.user   # {'id': 1, 'username': 'admin', 'role': 'admin'}
    # Use user.username for audit logging, etc.
```

### 8.4 Getting the Room Token in a Service

```python
from flask import request

def get_active(room_token: str):
    conn = get_db()
    room = conn.execute(
        "SELECT id FROM rooms WHERE room_token=?", (room_token,)
    ).fetchone()
    if not room:
        return jsonify([])
    # ... filter by room['id']
```

The blueprint passes `request.headers.get('X-Room-Token', '')` to the service:

```python
# In blueprints/messages.py
@bp.route('/active', methods=['GET'])
def get_active():
    room_token = request.headers.get('X-Room-Token', '')
    return message_service.get_active(room_token)
```

---

## 9. Complete API Reference

### Auth

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | None | Login with username/password → JWT |

**Request:** `{"username": "admin", "password": "..."}`  
**Response:** `{"token": "eyJ...", "role": "admin", "username": "admin"}`

---

### Users

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/users` | Admin | List all users |
| `POST` | `/api/users` | Admin | Create user |
| `DELETE` | `/api/users/<id>` | Admin | Delete user |

**Create user body:** `{"username": "...", "password": "...", "role": "operator"}`

---

### Channels

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/channels` | Room Token | List channels (paginated, filtered) |
| `GET` | `/api/channels/<id>` | Room Token | Get single channel |
| `POST` | `/api/channels` | Admin | Create channel |
| `PUT` | `/api/channels/<id>` | Admin | Update channel |
| `DELETE` | `/api/channels/<id>` | Admin | Delete channel |
| `POST` | `/api/channels/preview-m3u` | Admin | Preview M3U import |
| `POST` | `/api/channels/import-m3u` | Admin | Import from M3U |
| `GET` | `/api/channels/export-m3u` | None | Export active channels as M3U |
| `POST` | `/api/channels/bulk-delete` | Admin | Delete multiple channels |
| `POST` | `/api/channels/bulk-import-csv` | Admin | Bulk import from CSV |

**List query params:**
- `?group_id=<int>` — filter by media group
- `?active=1` — active channels only
- `?search=<string>` — filter by name
- `?limit=<int>&offset=<int>` — pagination

**Create/Update body:**
```json
{
  "name": "BBC News",
  "stream_url": "http://...",
  "logo": "https://...",
  "tvg_id": "bbc.news",
  "media_group_id": 1,
  "direct_play_num": 101,
  "active": 1,
  "channel_type": "m3u",
  "temporarily_unavailable": 0,
  "is_vip": 0
}
```

**Import M3U body:**
```json
{
  "url": "http://provider.com/playlist.m3u",
  "mode": "replace",
  "groups": ["News", "Sports"]
}
```

---

### Media Groups

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/groups` | Room Token | List media groups |
| `POST` | `/api/groups` | Admin | Create group |
| `PUT` | `/api/groups/<id>` | Admin | Update group |
| `DELETE` | `/api/groups/<id>` | Admin | Delete group |

---

### Rooms

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/rooms` | Admin | List rooms (paginated, searchable) |
| `POST` | `/api/rooms` | Admin | Create room |
| `PUT` | `/api/rooms/<id>` | Admin | Update room |
| `DELETE` | `/api/rooms/<id>` | Admin | Delete room |
| `POST` | `/api/rooms/<id>/token` | Admin | Regenerate room token |
| `GET` | `/api/rooms/setup/<token>` | None | Room setup info by token |
| `POST` | `/api/rooms/register` | None | Register TV by room number → token |
| `GET` | `/api/rooms/<id>/packages` | Room Token | Get room's packages |
| `POST` | `/api/rooms/<id>/packages` | Admin | Set room's packages |
| `GET` | `/api/rooms/packages-map` | Admin | Room-package relationship map |
| `POST` | `/api/rooms/bulk-delete` | Admin | Delete multiple rooms |
| `POST` | `/api/rooms/bulk-add` | Admin | Bulk create rooms |

**Register body:** `{"room_number": "101"}`  
**Response:** `{"token": "uuid", "room_id": 1, "tv_name": "Room 101 TV"}`

---

### Devices

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/device/heartbeat` | None | TV box heartbeat (updates online status) |
| `GET` | `/api/devices` | Admin | List registered devices |

**Heartbeat body:**
```json
{
  "room_token": "uuid",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "device_name": "Room 101 Box",
  "app_version": "2.1.0"
}
```

---

### Messages

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/messages` | Admin | List all messages |
| `POST` | `/api/messages` | Admin | Create message |
| `PUT` | `/api/messages/<id>` | Admin | Update message |
| `DELETE` | `/api/messages/<id>` | Admin | Delete message |
| `GET` | `/api/messages/active` | Room Token | Active messages for this room |
| `GET` | `/api/messages/inbox` | Room Token | Full inbox with read status |
| `GET` | `/api/messages/unread-count` | Room Token | Unread count |
| `POST` | `/api/messages/<id>/dismiss` | Room Token | Dismiss a message |
| `POST` | `/api/messages/<id>/read` | Room Token | Mark as read |
| `POST` | `/api/messages/mark-all-read` | Room Token | Mark all read |

**Create body:**
```json
{
  "title": "Welcome!",
  "body": "Enjoy your stay.",
  "type": "info",
  "target": "all",
  "room_ids": [],
  "expires_at": "2026-12-31 23:59:00"
}
```

---

### Birthdays

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/birthdays` | Admin | List all birthdays |
| `GET` | `/api/birthdays/today` | None | Today's birthdays |
| `POST` | `/api/birthdays` | Admin | Create birthday |
| `PUT` | `/api/birthdays/<id>` | Admin | Update birthday |
| `DELETE` | `/api/birthdays/<id>` | Admin | Delete birthday |

---

### Navigation Menu

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/nav` | Room Token | Get nav items + position/style (TV client) |
| `GET` | `/api/nav/items` | Admin | Get nav items + position/style (admin) |
| `POST` | `/api/nav/items` | Admin | Create custom nav item |
| `PUT` | `/api/nav/items/<id>` | Admin | Update nav item |
| `POST` | `/api/nav/items/<id>/toggle` | Admin | Toggle enable/disable |
| `DELETE` | `/api/nav/items/<id>` | Admin | Delete custom item |
| `POST` | `/api/nav/reorder` | Admin | Reorder nav items |
| `POST` | `/api/nav/position` | Admin | Set menu position and style |

**Nav items response:**
```json
{
  "items": [
    {"id": 1, "key": "home", "label": "Home", "icon": "🏠", "enabled": 1, "sort_order": 0, "is_system": 1}
  ],
  "position": "bottom",
  "style": "pill"
}
```

**Reorder body:** `{"ids": [3, 1, 2, 5, 4]}`  
**Position body:** `{"position": "bottom", "style": "pill"}`

Built-in nav keys: `home`, `tv`, `vod`, `radio`, `weather`, `info`, `services`, `prayers`, `messages`

---

### Settings

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/settings` | Room Token | All settings (Redis cached 60s) |
| `GET` | `/api/settings/stamp` | None | Settings modification timestamp |
| `POST` | `/api/settings` | Admin | Save settings (key-value map) |
| `GET` | `/api/admin/editor-config` | Admin | Editor configuration |

**Save body:** `{"hotel_name": "Grand Hotel", "show_news_ticker": "1", ...}`

**Key settings:**

| Key | Type | Description |
|---|---|---|
| `hotel_name` | string | Hotel name shown in TV header |
| `hotel_logo` | url | Logo URL |
| `welcome_message` | html | Home screen welcome text |
| `admin_pin` | string | Legacy admin PIN (deprecated — use JWT) |
| `show_news_ticker` | `0`/`1` | Enable RSS ticker |
| `ticker_text_color` | hex | RSS ticker text color |
| `ticker_bg_color` | hex | RSS ticker background |
| `ticker_bg_opacity` | `0.0`–`1.0` | RSS ticker opacity |
| `navbar_position` | `top`/`bottom` | TV app nav position |
| `navbar_style` | `pill`/`flat`/`boxed`/`icon` | Nav button style |
| `home_show_slides` | `0`/`1` | Show promo slides on home |
| `home_show_welcome` | `0`/`1` | Show welcome banner on home |
| `home_show_channels` | `0`/`1` | Show channel grid on home |
| `home_show_vod` | `0`/`1` | Show featured VOD on home |
| `deployment_mode` | `hotel`/`commercial` | Affects sidebar labels |
| `prayer_enabled` | `0`/`1` | Enable prayer times feature |
| `prayer_lat` / `prayer_lon` | float | Prayer location |

---

### Promo Slides

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/slides/public` | Room Token | Active slides (public) |
| `GET` | `/api/slides/all` | Admin | All slides |
| `POST` | `/api/slides` | Admin | Create slide |
| `PUT` | `/api/slides/<id>` | Admin | Update slide |
| `DELETE` | `/api/slides/<id>` | Admin | Delete slide |
| `POST` | `/api/slides/reorder` | Admin | Reorder slides |

---

### Content Pages (Hotel Info)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/content` | Room Token | List pages |
| `GET` | `/api/content/<id>` | Room Token | Page with items and gallery |
| `POST` | `/api/content` | Admin | Create page |
| `PUT` | `/api/content/<id>` | Admin | Update page |
| `DELETE` | `/api/content/<id>` | Admin | Delete page |
| `GET` | `/api/content/<id>/items` | Room Token | List items (basic) |
| `GET` | `/api/content/<id>/items/full` | Room Token | Items with gallery images |
| `POST` | `/api/content/<id>/items` | Admin | Create item |
| `PUT` | `/api/content/items/<id>` | Admin | Update item |
| `DELETE` | `/api/content/items/<id>` | Admin | Delete item |
| `POST` | `/api/content/items/<id>/upload` | Admin | Upload item thumbnail |
| `GET` | `/api/content/items/<id>/gallery` | Room Token | Item gallery images |
| `POST` | `/api/content/items/<id>/gallery` | Admin | Add gallery image by URL |
| `POST` | `/api/content/items/<id>/gallery/upload` | Admin | Upload gallery image |
| `DELETE` | `/api/content/item-images/<id>` | Admin | Delete gallery image |
| `PATCH` | `/api/content/item-images/<id>` | Admin | Update image position/fit |

---

### Content Packages & VIP Access

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/packages` | Admin | List packages with content counts |
| `POST` | `/api/packages` | Admin | Create package |
| `PUT` | `/api/packages/<id>` | Admin | Update package |
| `DELETE` | `/api/packages/<id>` | Admin | Delete package |
| `GET` | `/api/my-packages` | Room Token | Room's subscribed packages |
| `GET` | `/api/vip/channels` | Admin | VIP channel grants |
| `POST` | `/api/vip/access` | Admin | Grant VIP channel access |
| `DELETE` | `/api/vip/access` | Admin | Revoke VIP channel access |
| `GET` | `/api/vip/my-channels` | Room Token | Room's VIP channels |
| `GET` | `/api/vip/vod` | Admin | VIP VOD grants |
| `POST` | `/api/vip/vod-access` | Admin | Grant VIP VOD access |
| `DELETE` | `/api/vip/vod-access` | Admin | Revoke VIP VOD access |
| `GET` | `/api/vip/my-vod` | Room Token | Room's VIP VOD |

---

### Radio

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/radio` | Room Token | List radio stations |
| `GET` | `/api/radio/countries` | None | Available countries |
| `POST` | `/api/radio` | Admin | Create station |
| `PUT` | `/api/radio/<id>` | Admin | Update station |
| `DELETE` | `/api/radio/<id>` | Admin | Delete station |
| `POST` | `/api/radio/bulk-delete` | Admin | Delete multiple |
| `POST` | `/api/radio/bulk-add` | Admin | Bulk create stations |

---

### RSS Feeds

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/rss` | Admin | List all feeds |
| `GET` | `/api/rss/public` | None | Active feeds with items (cached 5min) |
| `POST` | `/api/rss` | Admin | Create feed |
| `PUT` | `/api/rss/<id>` | Admin | Update feed |
| `DELETE` | `/api/rss/<id>` | Admin | Delete feed |

---

### Prayer Times

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/prayer` | None | Get prayer times (Aladhan API, cached 1hr) |
| `POST` | `/api/prayer/settings` | Admin | Save prayer location settings |

**Query params:** `?lat=21.39&lon=39.85&method=4` or `?city=Mecca&country=SA`

---

### Weather

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/weather` | None | Get weather (external API, cached 10min) |

---

### Skins & Themes

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/skins` | Admin | List all skins |
| `POST` | `/api/skins` | Admin | Create skin |
| `GET` | `/api/skin` | Room Token | Get room's active skin |
| `PUT` | `/api/skins/<id>` | Admin | Update skin |
| `DELETE` | `/api/skins/<id>` | Admin | Delete skin |

---

### EPG / Programme Guide

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/epg/<channel_id>` | Room Token | Programme entries for channel |
| `POST` | `/api/epg/sync-now` | Admin | Sync EPG from XMLTV URL |
| `GET` | `/api/epg/status` | Admin | Sync status and last run |
| `POST` | `/api/epg/generate-guide` | Admin | Generate guide.xml for EPG service |

---

### Cast (Chromecast)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/cast/session` | None | Start cast session |
| `PATCH` | `/api/cast/session/<id>` | None | End cast session |

---

### File Uploads

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/api/upload` | Admin | Upload image file → `/uploads/` URL |
| `POST` | `/api/watch-event` | None | Record watch history (channel/VOD/radio) |
| `GET` | `/uploads/<filename>` | None | Serve uploaded file (static, via Nginx) |

**Upload response:** `{"url": "/uploads/abc123.jpg"}`

---

### Stats & Reports

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/api/stats/overview` | Admin | Dashboard stats (rooms, channels, VOD) |
| `GET` | `/api/stats/channels` | Admin | Top channels by view count |
| `GET` | `/api/stats/rooms` | Admin | Top rooms by activity |
| `GET` | `/api/reports/rooms` | Admin | Full rooms report |
| `GET` | `/api/reports/channels` | Admin | Channels with view counts |
| `GET` | `/api/reports/vod` | Admin | VOD with watch counts |
| `GET` | `/api/reports/radio` | Admin | Radio with listen counts |
| `GET` | `/api/reports/pages` | Admin | Content pages with item counts |
| `GET` | `/api/reports/summary` | Admin | Top content by date range |
| `GET` | `/api/reports/devices` | Admin | Device registry |

---

### VOD Server (HLS Streaming)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `GET` | `/vod/hls/<id>/master.m3u8` | None | HLS master playlist |
| `GET` | `/vod/hls/<id>/<quality>/index.m3u8` | None | Quality playlist |
| `GET` | `/vod/hls/<id>/<quality>/<segment>.ts` | None | TS segment (X-Accel served) |
| `GET` | `/vod/thumbnails/<filename>` | None | Thumbnail image |
| `GET` | `/vod/api/videos` | None | Video catalogue |
| `GET` | `/vod/api/videos/<id>` | None | Video metadata |
| `PUT` | `/vod/api/videos/<id>` | API Key | Update metadata |
| `DELETE` | `/vod/api/videos/<id>` | API Key | Delete video |
| `POST` | `/vod/api/upload` | API Key | Upload MP4 file |
| `POST` | `/vod/api/import` | API Key | Import from URL |
| `GET` | `/vod/api/videos/<id>/progress` | None | Transcode progress |
| `GET` | `/vod/api/videos/<id>/progress/stream` | None | Progress SSE stream |
| `POST` | `/vod/api/videos/<id>/retranscode` | API Key | Retranscode video |
| `POST` | `/vod/api/videos/<id>/thumbnail` | API Key | Regenerate thumbnail |
| `POST` | `/vod/api/videos/<id>/push-nexvision` | API Key | Push to NexVision catalogue |
| `GET` | `/vod/api/jobs` | None | Active transcode jobs |
| `POST` | `/vod/api/jobs/<id>/cancel` | API Key | Cancel transcode |
| `GET` | `/vod/api/health` | None | Health check |
| `GET` | `/vod/api/analytics` | API Key | Usage analytics |

---

### Static UI Routes

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | TV client SPA (index.html) |
| `GET` | `/<path>` | TV client SPA (all non-API paths fall back to index.html) |
| `GET` | `/admin/` | Admin panel (index.html) |
| `GET` | `/admin/<path>` | Admin static files (css, js) |
| `GET` | `/cast-receiver/` | Chromecast receiver HTML |
| `GET` | `/cast-receiver/<path>` | Cast receiver static files |

---

## 10. Database Schema

### Core Tables

```sql
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT UNIQUE NOT NULL,
    password    TEXT NOT NULL,          -- bcrypt hash
    role        TEXT DEFAULT 'operator', -- 'admin' | 'operator' | 'viewer'
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE rooms (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    room_number  TEXT NOT NULL,
    tv_name      TEXT,
    device_id    TEXT,
    skin_id      INTEGER,
    online       INTEGER DEFAULT 0,
    last_seen    TEXT,
    room_token   TEXT UNIQUE,          -- UUID v4
    user_agent   TEXT
);

CREATE TABLE devices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mac_address TEXT UNIQUE,
    room_number TEXT,
    device_name TEXT,
    last_seen   TEXT,
    app_version TEXT,
    status      TEXT DEFAULT 'active',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

### Content Tables

```sql
CREATE TABLE channels (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    name                  TEXT NOT NULL,
    stream_url            TEXT,
    logo                  TEXT,
    tvg_id                TEXT,
    tvg_logo_url          TEXT,
    group_title           TEXT,
    media_group_id        INTEGER,
    direct_play_num       INTEGER,
    active                INTEGER DEFAULT 1,
    temporarily_unavailable INTEGER DEFAULT 0,
    channel_type          TEXT DEFAULT 'stream_udp',
    is_vip                INTEGER DEFAULT 0,
    created_at            TEXT DEFAULT (datetime('now')),
    external_id           TEXT,
    source                TEXT
);

CREATE TABLE media_groups (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    image   TEXT,
    active  INTEGER DEFAULT 1
);

CREATE TABLE vod_movies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    genre       TEXT,
    year        INTEGER,
    language    TEXT,
    runtime     INTEGER,
    rating      REAL,
    poster      TEXT,             -- thumbnail/poster URL
    backdrop    TEXT,
    stream_url  TEXT,             -- /vod/hls/<id>/master.m3u8
    price       REAL DEFAULT 0,
    active      INTEGER DEFAULT 1
);

CREATE TABLE nav_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT UNIQUE NOT NULL,  -- 'home', 'tv', 'vod', etc.
    label       TEXT NOT NULL,
    icon        TEXT,                  -- emoji
    enabled     INTEGER DEFAULT 1,
    sort_order  INTEGER DEFAULT 0,
    is_system   INTEGER DEFAULT 0,     -- 1 = built-in, cannot be deleted
    target_url  TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);
```

### Packages & Access Control

```sql
CREATE TABLE content_packages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    active      INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE room_packages   (room_id INTEGER, package_id INTEGER, PRIMARY KEY (room_id, package_id));
CREATE TABLE package_channels(package_id INTEGER, channel_id INTEGER, PRIMARY KEY (package_id, channel_id));
CREATE TABLE package_vod     (package_id INTEGER, vod_id INTEGER, PRIMARY KEY (package_id, vod_id));
CREATE TABLE package_radio   (package_id INTEGER, radio_id INTEGER, PRIMARY KEY (package_id, radio_id));

CREATE TABLE vip_channel_access (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  INTEGER,
    room_id     INTEGER,
    granted_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(channel_id, room_id)
);

CREATE TABLE vip_vod_access (video_id INTEGER, room_id INTEGER, PRIMARY KEY (video_id, room_id));
```

---

## 11. Configuration Reference

### Environment Variables (.env)

```ini
# ── Flask ─────────────────────────────────────────────────────────
SECRET_KEY=                    # REQUIRED — HS256 JWT signing key (hex 64 chars)

# ── Database ──────────────────────────────────────────────────────
USE_MYSQL=0                    # 0 = SQLite (dev), 1 = MySQL (prod)
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=nexvision
MYSQL_PASSWORD=
MYSQL_DB=nexvision
MYSQL_VOD_DB=nexvision_vod

# ── Cache ─────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── Gunicorn ──────────────────────────────────────────────────────
GUNICORN_WORKERS=5             # Recommended: (2 × CPU_cores) + 1

# ── VOD ───────────────────────────────────────────────────────────
VOD_API_KEY=                   # REQUIRED — protects VOD write endpoints
VOD_NEXVISION_URL=http://localhost:5000
VOD_NEXVISION_TOKEN=

# ── Nginx ─────────────────────────────────────────────────────────
USE_X_ACCEL=1                  # 1 = Nginx X-Accel-Redirect for HLS .ts files
```

### Config Class (app/config.py)

| Attribute | Default | Source |
|---|---|---|
| `SECRET_KEY` | (insecure default) | `SECRET_KEY` env |
| `APP_VERSION` | `'8.10'` | `APP_VERSION` env |
| `ONLINE_MINUTES` | `10` | Hard-coded |
| `VOD_API_KEY` | `'nexvision-vod-key-2024'` | `VOD_API_KEY` env |
| `MAX_UPLOAD_MB` | `10000` | Hard-coded |
| `HLS_SEGMENT_SECS` | `4` | Hard-coded |
| `ALLOWED_IMAGE_EXTS` | `{png,jpg,jpeg,gif,webp,svg}` | Hard-coded |

### Gunicorn (app/gunicorn.conf.py)

| Setting | Value | Notes |
|---|---|---|
| `bind` | `unix:/run/nexvision/gunicorn.sock` | Unix socket |
| `worker_class` | `gevent` | Async, 1000 conn/worker |
| `workers` | `(2×CPU)+1` | From `GUNICORN_WORKERS` env |
| `timeout` | `120` | Allows RSS fetches, FFmpeg |
| `max_requests` | `5000` | Auto-restart after N requests |
| `accesslog` | `/var/log/nexvision/access.log` | |
| `errorlog` | `/var/log/nexvision/error.log` | |

---

## 12. Frontend Architecture

### TV Client (web/tv/)

Single-page application served by Nginx. Falls back to `index.html` for all
non-file paths (client-side routing).

Key globals in `tv.js`:
- `API` — base URL: `window.location.origin + '/api'`
- `ROOM_TOKEN` — loaded from `localStorage`, sent as `X-Room-Token` header
- `window._settings` — cached settings object fetched on load
- `_vodSearchQ` — current VOD search query string (live-filter state)
- `_vodActiveGenre` — currently selected genre chip (`null` = All)
- `_vodShowFavs` — whether the Favourites filter chip is active
- `_vodFavs` — `Set<number>` of favourited movie IDs, persisted as `localStorage['nv_fav_movies']`

Boot sequence:
1. Check `localStorage` for `room_token`
2. If missing → show registration screen (numpad entry of room number)
3. `POST /api/rooms/register` → save token
4. Fetch settings, nav items, skin
5. Render home screen

#### VOD Search & Favourites (v8.17+)

The VOD screen renders a `vod-header` bar containing the title, an inline search input
(`.vod-search`), and genre/favourites filter chips (`.filter-chip`, `.fav-chip`).

Search and filter state is kept in module-level variables (`_vodSearchQ`,
`_vodActiveGenre`, `_vodShowFavs`). Typing in the search box calls `renderVoD()` which
applies all three filters in combination client-side against `allMovies`.

Favourites are toggled via the heart button (`.mt-fav-btn`) on each movie tile. The Set
is serialised to `localStorage` on every toggle so it survives page reloads.

#### `api()` error handling

The shared `api(path, opts)` helper returns `null` (not a thrown error) for any non-2xx
HTTP response. Callers should guard with `|| []` / `|| {}` as appropriate.

### Admin Panel (web/admin/)

Single-page application. JWT stored in `localStorage` as `nv_jwt`.

Key globals in `admin.js`:
- `API` — `window.location.origin + '/api'`
- `jwt` — Bearer token from `localStorage`
- `pages` — Object mapping page names to async render functions
- `go(page)` — Navigate to a section, calls `pages[page]()`

The `req(path, opts)` helper wraps all API calls with the JWT header and
handles `401` by calling `logout()`.

### Cast Receiver (web/cast/)

Chromecast CAF (Cast Application Framework) receiver. Uses hls.js for HLS
playback. App ID: `CC1AD845` (registered on Google Cast console).

---

## 13. Adding New Features

### Step 1 — Create the service

```python
# app/services/my_service.py
from flask import jsonify
from ..extensions import get_db

def list_items():
    conn = get_db()
    rows = conn.execute("SELECT * FROM my_table ORDER BY id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

def create_item(d: dict):
    if not d.get('name'):
        return jsonify({'error': 'name required'}), 400
    conn = get_db()
    cur = conn.execute("INSERT INTO my_table (name) VALUES (?)", (d['name'],))
    conn.commit()
    item = dict(conn.execute("SELECT * FROM my_table WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(item), 201
```

### Step 2 — Create the blueprint

```python
# app/blueprints/my_feature.py
from flask import Blueprint, request
from ..decorators import admin_required
from ..services import my_service

my_feature_bp = Blueprint('my_feature', __name__, url_prefix='/api/my-feature')

@my_feature_bp.route('', methods=['GET'])
@admin_required
def list_items():
    return my_service.list_items()

@my_feature_bp.route('', methods=['POST'])
@admin_required
def create_item():
    return my_service.create_item(request.json or {})
```

### Step 3 — Export from blueprints/__init__.py

```python
# app/blueprints/__init__.py
from .my_feature import my_feature_bp
```

### Step 4 — Register in app/__init__.py

```python
from .blueprints import ..., my_feature_bp

app.register_blueprint(my_feature_bp)
```

### Step 5 — Add the DB table to app/main.py

```python
# In init_db():
conn.execute("""
    CREATE TABLE IF NOT EXISTS my_table (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        name    TEXT NOT NULL,
        active  INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    )
""")
```

### Step 6 — Add to the admin panel sidebar (optional)

In `web/admin/index.html`, add to the appropriate `<nav>` section:
```html
<div class="ni" id="ni-my-feature" onclick="go('myFeature')">
    <span class="ic">🔧</span>My Feature
</div>
```

In `web/admin/admin.js`:
```javascript
// Add to TITLES
const TITLES = { ..., myFeature: 'My Feature' };

// Add page renderer
pages.myFeature = async function() {
    const data = await req('/my-feature');
    if (!data) return;
    document.getElementById('content').innerHTML = `
        <div class="sec-hdr">
            <div class="sec-title">My Feature</div>
        </div>
        <!-- render data.map(...) -->
    `;
};
```

---

## 14. Running & Deployment

### Development

```bash
cd /opt/nexvision
python3 -m venv venv
source venv/bin/activate
pip install -r requirements_prod.txt

cp .env.example .env
# Edit .env — set SECRET_KEY and VOD_API_KEY at minimum

python run.py
# API: http://localhost:5000/api/
# Admin: http://localhost:5000/admin/
# TV: http://localhost:5000/
```

### Production

```bash
# 1. System dependencies
sudo apt install python3 python3-venv nginx redis-server mysql-server ffmpeg -y

# 2. Application user
sudo useradd --system --no-create-home --shell /usr/sbin/nologin nexvision

# 3. Python environment
python3 -m venv /opt/nexvision/venv
/opt/nexvision/venv/bin/pip install -r requirements_prod.txt

# 4. Environment
cp .env.example .env
# Set: SECRET_KEY, VOD_API_KEY, MYSQL_PASSWORD, USE_MYSQL=1, REDIS_URL

# 5. Nginx
sudo cp nginx/nexvision.conf /etc/nginx/sites-available/nexvision
sudo ln -s /etc/nginx/sites-available/nexvision /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 6. Systemd socket dir
sudo mkdir -p /run/nexvision
sudo chown nexvision:www-data /run/nexvision
echo "d /run/nexvision 0755 nexvision www-data -" | sudo tee /etc/tmpfiles.d/nexvision.conf

# 7. Start services
sudo systemctl enable --now nexvision redis-server mysql nginx
```

> **Multi-worker init safety (v8.17+):** `app/wsgi.py` uses `fcntl.LOCK_EX` on
> `/tmp/nexvision_init.lock` so that when Gunicorn spawns multiple gevent workers at
> startup, only one worker runs `init_db()` at a time. The lock is released immediately
> after init so it has no effect on steady-state throughput.

### Useful Commands

```bash
# Restart application
sudo systemctl restart nexvision

# Watch application logs
sudo journalctl -u nexvision -f

# Watch Nginx access log
sudo tail -f /var/log/nexvision/access.log

# Check health
curl http://localhost/api/settings | python3 -m json.tool

# Flush all cache
redis-cli KEYS "nv:*" | xargs redis-cli DEL

# Check DB table counts
sqlite3 /opt/nexvision/nexvision.db \
  "SELECT 'channels', COUNT(*) FROM channels UNION ALL
   SELECT 'rooms', COUNT(*) FROM rooms UNION ALL
   SELECT 'messages', COUNT(*) FROM messages;"
```

---

## 15. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `500` on any `/api/` route | Python error | `sudo journalctl -u nexvision -n 50` |
| Admin panel "Invalid token" | JWT expired or `SECRET_KEY` rotated | Re-login; if rotated, all users must re-login |
| Nav menu shows no items (admin) | Was a bug pre-v8.16 | Update to v8.17; `sudo systemctl restart nexvision` |
| TV client blank screen | Nginx or Flask not running | `systemctl status nexvision nginx` |
| VOD won't play on phone | `stream_url` host mismatch | Restart Flask — URL is generated per-request from `request.host` |
| HLS buffering | Disk I/O or missing X-Accel | Check `USE_X_ACCEL=1` in `.env`; verify `/internal/vod/` Nginx alias |
| RSS ticker not updating | Stale Redis cache | `redis-cli DEL nv:rss` |
| EPG sync fails: DB locked | SQLite WAL conflict | `sudo systemctl reload nexvision` (graceful restart) |
| Birthday not showing | Server timezone mismatch | `date` on server must match hotel timezone |
| `502 Bad Gateway` | Gunicorn not running or socket missing | `systemctl restart nexvision`; check socket: `ls -la /run/nexvision/` |
| `403` on admin panel | Nginx IP restriction (if configured) | Whitelist your management IP |
| `413 Request Entity Too Large` | `client_max_body_size` in Nginx | Increase for VOD upload location |

---

*NexVision IPTV Developer Guide — v8.16*  
*Architecture: Flask Blueprints + Service Layer + Redis + SQLite/MySQL + Nginx/Gunicorn*
