"""
NexVision IPTV Platform  —  Unified Server
Combines the main IPTV platform (app.py) and the VOD streaming server (vod_server.py).

Main routes:   http://HOST:PORT/          (TV client)
Admin CMS:     http://HOST:PORT/admin/
API:           http://HOST:PORT/api/

VOD Dashboard: http://HOST:PORT/vod/
VOD API:       http://HOST:PORT/vod/api/videos  etc.
HLS streams:   http://HOST:PORT/vod/hls/<id>/master.m3u8
"""

import re
import os
import json
import time
import uuid
import socket
import random
import logging
import hashlib
import sqlite3                          # kept for VOD SQLite fallback only

# ── Production: MySQL + Redis ─────────────────────────────────────────────────
_USE_MYSQL = os.getenv('USE_MYSQL', '0') == '1'
if _USE_MYSQL:
    from db.db_mysql import get_mysql_db, get_vod_mysql_db, add_column_if_missing
    from db.cache_setup import cache, init_cache, TTL_SETTINGS, TTL_CHANNELS, \
        TTL_VOD, TTL_NAV, TTL_SLIDES, TTL_RSS, \
        invalidate_settings, invalidate_channels, invalidate_vod, \
        invalidate_nav, invalidate_slides, invalidate_rss
import threading
import subprocess
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import (
    Flask, request, jsonify, send_from_directory,
    Response, stream_with_context, abort, make_response, redirect
)
from flask_cors import CORS
from db.vod_storage_admin import StorageConfig, STORAGE_ADMIN_HTML, create_storage_admin_routes

# Resolve paths relative to this file, so it works regardless of working directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_DIR = os.path.join(BASE_DIR, 'web', 'admin')
TV_DIR    = os.path.join(BASE_DIR, 'web', 'tv')
CAST_DIR  = os.path.join(BASE_DIR, 'web', 'cast')
DB_PATH   = os.path.join(BASE_DIR, 'nexvision.db')

app = Flask(__name__, static_folder=ADMIN_DIR, static_url_path='/admin')
CORS(
    app,
    origins='*',
    # Cast sender SDK and ExoPlayer send Range as a non-simple header, which
    # triggers an OPTIONS preflight. It must appear in Allow-Headers or the
    # browser/Cast runtime blocks the request before a single byte is fetched.
    allow_headers=[
        'Range', 'Origin', 'Accept', 'X-Requested-With',
        'Content-Type', 'Authorization', 'X-Room-Token',
    ],
    # Players need to read these response headers to track progress and seek.
    # Non-safelisted headers are invisible to JS/Cast unless explicitly exposed.
    expose_headers=['Content-Length', 'Content-Range', 'Accept-Ranges'],
    methods=['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
    max_age=600,
)
app.config['SECRET_KEY'] = 'nexvision-iptv-secure-secret-key-2024-x7k9'
APP_VERSION = os.getenv('NEXVISION_VERSION', '8.10')


# Online threshold: a room is considered online if seen within this many minutes
ONLINE_MINUTES = 10

def _safe_int(val, default=0):
    try: return int(val)
    except (ValueError, TypeError): return default


# ─── Database ────────────────────────────────────────────────────────────────

def get_db():
    if _USE_MYSQL:
        return get_mysql_db()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def migrate_db(conn):
    """Add columns that might not exist in older databases."""
    cols_to_add = [
        ("channels",       "channel_type",  "TEXT DEFAULT 'stream_udp'"),
        ("channels",       "is_vip",        "INTEGER DEFAULT 0"),
        ("content_items",  "content_html",  "TEXT DEFAULT ''"),
        ("content_items",  "photo_url",     "TEXT DEFAULT ''"),
        ("nav_items",      "target_url",    "TEXT DEFAULT ''"),
        ("promo_slides",   "video_url",     "TEXT DEFAULT ''"),
        ("promo_slides",   "media_type",    "TEXT DEFAULT 'image'"),
        ("rss_feeds",      "text_color",    "TEXT DEFAULT '#ffffff'"),
        ("rss_feeds",      "bg_color",      "TEXT DEFAULT '#09090f'"),
        ("rss_feeds",      "bg_opacity",    "INTEGER DEFAULT 92"),
        ("watch_history",  "device_type",   "TEXT DEFAULT 'browser'"),
    ]
    for table, col, typedef in cols_to_add:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            conn.commit()
        except Exception:
            pass  # Column already exists
    # Create multi-image gallery table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS content_item_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            position TEXT DEFAULT 'center center',
            fit TEXT DEFAULT 'cover',
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES content_items(id)
        )
    """)
    # Add new columns to existing table if upgrading
    for col, defval in [("position", "'center center'"), ("fit", "'cover'")]:
        try:
            conn.execute(f"ALTER TABLE content_item_images ADD COLUMN {col} TEXT DEFAULT {defval}")
        except Exception:
            pass
    # Ensure deployment_mode exists for existing installs
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('deployment_mode', 'hotel')")
    # VIP VOD access table (v8.9)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vip_vod_access (
            video_id TEXT NOT NULL,
            room_id  INTEGER NOT NULL,
            PRIMARY KEY (video_id, room_id),
            FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
        )
    """)
    # Content packages (v8.9)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS content_packages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT DEFAULT '',
            active      INTEGER DEFAULT 1,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS package_channels (
            package_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (package_id, channel_id),
            FOREIGN KEY (package_id) REFERENCES content_packages(id) ON DELETE CASCADE,
            FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS package_vod (
            package_id INTEGER NOT NULL,
            vod_id     INTEGER NOT NULL,
            PRIMARY KEY (package_id, vod_id),
            FOREIGN KEY (package_id) REFERENCES content_packages(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS package_radio (
            package_id INTEGER NOT NULL,
            radio_id   INTEGER NOT NULL,
            PRIMARY KEY (package_id, radio_id),
            FOREIGN KEY (package_id) REFERENCES content_packages(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS room_packages (
            room_id    INTEGER NOT NULL,
            package_id INTEGER NOT NULL,
            PRIMARY KEY (room_id, package_id),
            FOREIGN KEY (room_id)    REFERENCES rooms(id)            ON DELETE CASCADE,
            FOREIGN KEY (package_id) REFERENCES content_packages(id) ON DELETE CASCADE
        )
    """)
    # Cast session tracking
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cast_sessions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id          INTEGER,
            channel_id       INTEGER,
            started_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at         TIMESTAMP,
            duration_seconds INTEGER,
            sender_platform  TEXT DEFAULT '',
            FOREIGN KEY (room_id)    REFERENCES rooms(id)    ON DELETE SET NULL,
            FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE SET NULL
        )
    """)
    # Android TV box device registry (heartbeat tracking)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            mac_address TEXT NOT NULL UNIQUE,
            room_number TEXT DEFAULT '',
            device_name TEXT DEFAULT '',
            last_seen   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            app_version TEXT DEFAULT '',
            status      TEXT DEFAULT 'active',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()


def _bump_stamp(conn):
    """Bump config_stamp so TV clients auto-refresh after any content change."""
    import time as _t
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('config_stamp',?,CURRENT_TIMESTAMP)",
        (str(int(_t.time())),))

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'viewer',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS media_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        image TEXT,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        stream_url TEXT NOT NULL,
        logo TEXT DEFAULT '',
        tvg_id TEXT DEFAULT '',
        tvg_logo_url TEXT DEFAULT '',
        group_title TEXT DEFAULT '',
        media_group_id INTEGER DEFAULT 1,
        direct_play_num INTEGER,
        active INTEGER DEFAULT 1,
        temporarily_unavailable INTEGER DEFAULT 0,
        channel_type TEXT DEFAULT 'stream_udp',
        is_vip INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (media_group_id) REFERENCES media_groups(id)
    );

    CREATE TABLE IF NOT EXISTS vod_movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        genre TEXT DEFAULT '',
        year INTEGER,
        language TEXT DEFAULT 'English',
        runtime INTEGER DEFAULT 0,
        rating REAL DEFAULT 0,
        poster TEXT DEFAULT '',
        backdrop TEXT DEFAULT '',
        stream_url TEXT DEFAULT '',
        price REAL DEFAULT 0,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS vod_packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        price REAL DEFAULT 0,
        duration_hours INTEGER DEFAULT 24,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS radio_stations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        country TEXT DEFAULT '',
        genre TEXT DEFAULT '',
        stream_url TEXT NOT NULL,
        logo TEXT DEFAULT '',
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS content_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        group_name TEXT DEFAULT 'Hotel',
        template TEXT DEFAULT 'Default',
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS content_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        page_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        image TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        FOREIGN KEY (page_id) REFERENCES content_pages(id)
    );

    CREATE TABLE IF NOT EXISTS skins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        template TEXT DEFAULT 'Default Skin',
        background_image TEXT DEFAULT '',
        is_default INTEGER DEFAULT 0,
        theme_data TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_number TEXT NOT NULL UNIQUE,
        tv_name TEXT DEFAULT '',
        device_id TEXT DEFAULT '',
        skin_id INTEGER DEFAULT 1,
        online INTEGER DEFAULT 0,
        last_seen TIMESTAMP,
        room_token TEXT UNIQUE,
        user_agent TEXT DEFAULT '',
        FOREIGN KEY (skin_id) REFERENCES skins(id)
    );

    CREATE TABLE IF NOT EXISTS watch_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id INTEGER,
        channel_id INTEGER,
        movie_id INTEGER,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        duration_minutes INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS vod_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_id INTEGER NOT NULL,
        movie_id INTEGER,
        package_id INTEGER,
        amount REAL DEFAULT 0,
        purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP
    );
    """)

    # Migrate existing DB — add new columns if missing
    for col, defval in [('tvg_id', "''"), ('tvg_logo_url', "''"), ('group_title', "''")]:
        try:
            cur.execute(f"ALTER TABLE channels ADD COLUMN {col} TEXT DEFAULT {defval}")
        except Exception:
            pass  # column already exists

    # Migrate existing DB columns
    for _col in ['tvg_id', 'tvg_logo_url', 'group_title']:
        try:
            cur.execute(f"ALTER TABLE channels ADD COLUMN {_col} TEXT DEFAULT ''")
        except Exception:
            pass

    # Migrate rooms table — add token columns if missing
    for col, defval in [('room_token', 'NULL'), ('user_agent', "''")]:
        try:
            cur.execute(f"ALTER TABLE rooms ADD COLUMN {col} TEXT DEFAULT {defval}")
        except Exception:
            pass

    # Generate tokens for any rooms that don't have one yet
    cur.execute("SELECT id FROM rooms WHERE room_token IS NULL")
    for row in cur.fetchall():
        cur.execute("UPDATE rooms SET room_token=? WHERE id=?",
                    (str(uuid.uuid4()), row[0]))

    # Seed admin user
    cur.execute("SELECT id FROM users WHERE username='admin'")
    if not cur.fetchone():
        pw = hashlib.sha256('NexVis!0n'.encode()).hexdigest()
        cur.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)", ('admin', pw, 'admin'))
        cur.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)",
                    ('operator', hashlib.sha256('NexVis!0n'.encode()).hexdigest(), 'operator'))

    # Seed default skin
    cur.execute("SELECT id FROM skins WHERE name='Default Skin'")
    if not cur.fetchone():
        cur.execute("INSERT INTO skins (name, is_default) VALUES ('Default Skin', 1)")

    # Seed media groups
    cur.execute("SELECT id FROM media_groups WHERE name='All Channels'")
    if not cur.fetchone():
        for g in ['All Channels', 'Sports', 'News', 'Entertainment', 'Kids', 'Movies']:
            cur.execute("INSERT INTO media_groups (name) VALUES (?)", (g,))

    # Seed demo channels
    cur.execute("SELECT COUNT(*) FROM channels")
    if cur.fetchone()[0] == 0:
        demo_channels = [
            ('BBC World News', 'udp://@224.1.1.1:50000', 'bbc_world', 1, 1),
            ('CNN International', 'udp://@224.1.1.2:50000', 'cnn', 1, 2),
            ('Al Jazeera English', 'udp://@224.1.1.3:50000', 'aljazeera', 2, 3),
            ('ESPN', 'udp://@224.1.1.4:50000', 'espn', 2, 4),
            ('Discovery Channel', 'udp://@224.1.1.5:50000', 'discovery', 4, 5),
            ('National Geographic', 'udp://@224.1.1.6:50000', 'natgeo', 4, 6),
            ('Cartoon Network', 'udp://@224.1.1.7:50000', 'cartoon', 5, 7),
            ('Disney Channel', 'udp://@224.1.1.8:50000', 'disney', 5, 8),
            ('HBO', 'udp://@224.1.1.9:50000', 'hbo', 6, 9),
            ('Netflix Preview', 'udp://@224.1.1.10:50000', 'netflix', 6, 10),
        ]
        for ch in demo_channels:
            try:
                cur.execute("INSERT INTO channels (name, stream_url, logo, media_group_id, direct_play_num) VALUES (?,?,?,?,?)", ch)
            except Exception:
                pass

    # Seed demo VoD movies
    cur.execute("SELECT COUNT(*) FROM vod_movies")
    if cur.fetchone()[0] == 0:
        movies = [
            ('The Grand Budapest Hotel', 'A quirky story of a legendary hotel concierge.', 'Comedy/Drama', 2014, 'English', 99, 8.1, '', '', 15.0),
            ('Inception', 'A thief enters dreams to plant an idea.', 'Sci-Fi/Thriller', 2010, 'English', 148, 8.8, '', '', 12.0),
            ('The Dark Knight', 'Batman faces the Joker in a battle for Gotham.', 'Action', 2008, 'English', 152, 9.0, '', '', 12.0),
            ('Parasite', 'A poor family schemes to become employed by a wealthy family.', 'Drama/Thriller', 2019, 'Korean', 132, 8.5, '', '', 10.0),
            ('Dune', 'A noble family becomes embroiled in a war for a desert planet.', 'Sci-Fi', 2021, 'English', 155, 8.0, '', '', 15.0),
            ('The Lion King', 'A young lion prince flees his kingdom.', 'Animation', 1994, 'English', 88, 8.5, '', '', 8.0),
            ('Avatar: The Way of Water', 'Jake Sully lives a new life on Pandora.', 'Sci-Fi/Action', 2022, 'English', 192, 7.6, '', '', 18.0),
            ('Top Gun: Maverick', 'After 30+ years, Maverick serves as a top instructor.', 'Action', 2022, 'English', 130, 8.3, '', '', 15.0),
        ]
        for m in movies:
            cur.execute("INSERT INTO vod_movies (title, description, genre, year, language, runtime, rating, poster, backdrop, price) VALUES (?,?,?,?,?,?,?,?,?,?)", m)

    # Seed demo packages
    cur.execute("SELECT COUNT(*) FROM vod_packages")
    if cur.fetchone()[0] == 0:
        pkgs = [
            ('24-Hour Pass', 'All movies for 24 hours', 19.99, 24),
            ('Kids Package', 'Family & Kids movies for 48h', 14.99, 48),
            ('Weekend Package', 'All movies for 72 hours', 29.99, 72),
            ('Stay Package', 'All movies for your entire stay', 49.99, 720),
        ]
        for p in pkgs:
            cur.execute("INSERT INTO vod_packages (name, description, price, duration_hours) VALUES (?,?,?,?)", p)

    # Content packages tables
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS content_packages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            description TEXT DEFAULT '',
            active      INTEGER DEFAULT 1,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS package_channels (
            package_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (package_id, channel_id),
            FOREIGN KEY (package_id) REFERENCES content_packages(id) ON DELETE CASCADE,
            FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS package_vod (
            package_id INTEGER NOT NULL,
            vod_id     INTEGER NOT NULL,
            PRIMARY KEY (package_id, vod_id),
            FOREIGN KEY (package_id) REFERENCES content_packages(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS package_radio (
            package_id INTEGER NOT NULL,
            radio_id   INTEGER NOT NULL,
            PRIMARY KEY (package_id, radio_id),
            FOREIGN KEY (package_id) REFERENCES content_packages(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS room_packages (
            room_id    INTEGER NOT NULL,
            package_id INTEGER NOT NULL,
            PRIMARY KEY (room_id, package_id),
            FOREIGN KEY (room_id)    REFERENCES rooms(id)            ON DELETE CASCADE,
            FOREIGN KEY (package_id) REFERENCES content_packages(id) ON DELETE CASCADE
        );
    """)

    # Seed demo radio stations
    cur.execute("SELECT COUNT(*) FROM radio_stations")
    if cur.fetchone()[0] == 0:
        stations = [
            ('BBC Radio 1', 'UK', 'Pop/Rock', 'http://stream.live.vc.bbcmedia.co.uk/bbc_radio_one', ''),
            ('Jazz FM', 'UK', 'Jazz', 'http://edge-bauerse03.sharp-stream.com/jazzfm.mp3', ''),
            ('NRJ Paris', 'France', 'Pop', 'http://cdn.nrjaudio.fm/adwz2/fr/30001/mp3_128.mp3?origine=fluxradios', ''),
            ('Classic FM', 'UK', 'Classical', 'http://media-ice.musicradio.com/ClassicFMMP3', ''),
            ('Radio Dubai', 'UAE', 'Mixed', 'http://stream.radiodubai.ae/radiodubai128', ''),
            ('Lounge FM', 'Austria', 'Lounge', 'http://lounge.moe:8000/stream', ''),
        ]
        for s in stations:
            cur.execute("INSERT INTO radio_stations (name, country, genre, stream_url, logo) VALUES (?,?,?,?,?)", s)

    # Seed content pages
    cur.execute("SELECT COUNT(*) FROM content_pages")
    if cur.fetchone()[0] == 0:
        pages = [
            ('Hotel Highlights', 'Hotel', 'Default'),
            ('Spa & Wellness', 'Hotel', 'Default'),
            ('Dining & Restaurants', 'F&B', 'Default'),
            ('Room Service Menu', 'F&B', 'Default'),
            ('Local Attractions', 'Activities', 'Default'),
            ('Hotel Map', 'Hotel', 'Map'),
        ]
        for p in pages:
            cur.execute("INSERT INTO content_pages (name, group_name, template) VALUES (?,?,?)", p)

    # Seed demo rooms
    cur.execute("SELECT COUNT(*) FROM rooms")
    if cur.fetchone()[0] == 0:
        for i in range(1, 21):
            floor = (i - 1) // 5 + 1
            room_num = f"{floor}{(i-1)%5+1:02d}"
            cur.execute(
                "INSERT INTO rooms (room_number, tv_name, device_id, online, room_token) VALUES (?,?,?,?,?)",
                (room_num, f"TV-{room_num}", '', 0, str(uuid.uuid4()))
            )

    # Seed watch history
    cur.execute("SELECT COUNT(*) FROM watch_history")
    if cur.fetchone()[0] == 0:
        for _ in range(200):
            room_id = random.randint(1, 20)
            channel_id = random.randint(1, 10)
            duration = random.randint(5, 180)
            cur.execute("INSERT INTO watch_history (room_id, channel_id, duration_minutes) VALUES (?,?,?)",
                        (room_id, channel_id, duration))


    # ── RSS Feeds ──────────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS rss_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            type TEXT DEFAULT 'normal',
            active INTEGER DEFAULT 1,
            refresh_minutes INTEGER DEFAULT 15,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Messages ────────────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            type TEXT DEFAULT 'normal',
            target TEXT DEFAULT 'all',
            room_ids TEXT DEFAULT '',
            scheduled_at TIMESTAMP,
            expires_at TIMESTAMP,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1,
            created_by INTEGER DEFAULT 1,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    ''')

    # ── Birthdays ───────────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS birthdays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_name TEXT NOT NULL,
            room_id INTEGER,
            room_number TEXT DEFAULT '',
            birth_date TEXT NOT NULL,
            message TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
    ''')

    # ── Guest Services ─────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS guest_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            icon TEXT DEFAULT '📞',
            phone TEXT DEFAULT '',
            description TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )
    ''')

    # ── EPG Entries ──────────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS epg_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP NOT NULL,
            category TEXT DEFAULT '',
            FOREIGN KEY (channel_id) REFERENCES channels(id)
        )
    ''')

    # ── System Settings ──────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Default settings ─────────────────────────────────────────────────────────
    defaults = [
        ('hotel_name',       'Grand Hotel'),
        ('hotel_logo',       ''),
        ('welcome_message',  'Welcome to our hotel. Enjoy your stay!'),
        ('screensaver_delay','120'),
        ('screensaver_type', 'clock'),
        ('checkout_time',    '12:00'),
        ('currency',         'USD'),
        ('language',         'en'),
        ('support_phone',    '0'),
        ('wifi_name',        ''),
        ('wifi_password',    ''),
        ('prayer_enabled',   '0'),
        ('prayer_city',      'Dubai'),
        ('prayer_country',   'AE'),
        ('prayer_method',    '4'),
        ('prayer_notify',    '1'),
    ]
    for k, v in defaults:
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))

    # ── Message Reads (per-room read tracking) ──────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS message_reads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            room_id INTEGER NOT NULL,
            read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (message_id) REFERENCES messages(id),
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            UNIQUE(message_id, room_id)
        )
    ''')

    # ── Promo / Marketing Slides ──────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS promo_slides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT DEFAULT '',
            subtitle TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            video_url TEXT DEFAULT '',
            media_type TEXT DEFAULT 'image',
            link_action TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            duration_seconds INTEGER DEFAULT 5,
            active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Home screen display settings ───────────────────────────────────────────
    # home_show_featured: 1/0  home_show_slides: 1/0  home_slides_style: full/side/side
    home_defaults = [
        ('home_show_featured', '1'),
        ('home_show_slides',   '1'),
        ('home_slides_style',  'full'),
        ('home_show_welcome',  '0'),
        ('home_welcome_type',  'text'),
        ('home_welcome_text',  'Welcome! We hope you enjoy your stay.'),
        ('home_welcome_photo', ''),
        ('welcome_image',      ''),
        ('welcome_style',      'text'),
        # v8.2 — custom ticker messages & auto-sync stamp
        ('ticker_custom',      ''),
        ('config_stamp',       '0'),
        # v8.9 — deployment mode: hotel | commercial
        ('deployment_mode',    'hotel'),
        # v8.11 — home section visibility
        ('home_show_channels', '1'),
        ('home_show_vod',      '1'),
    ]
    for k, v in home_defaults:
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))

    # ── Navigation Items ──────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nav_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL,
            icon TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            is_system INTEGER DEFAULT 1,
            target_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Default nav items — messages enabled by default ────────────────────────────
    nav_defaults = [
        ('home',     'Home',       '🏠', 1, 0,  1),
        ('tv',       'Live TV',    '📺', 1, 1,  1),
        ('vod',      'Movies',     '🎬', 1, 2,  1),
        ('radio',    'Radio',      '📻', 1, 3,  1),
        ('weather',  'Weather',    '🌤', 1, 4,  1),
        ('info',     'Hotel Info', '📋', 1, 5,  1),
        ('services', 'Services',   '🛎', 1, 6,  1),
        ('prayers',  'Prayer',     '🕌', 0, 7,  1),
        ('messages', 'Messages',   '💬', 1, 8,  1),  # enabled by default
    ]
    for key, label, icon, enabled, sort_order, is_sys in nav_defaults:
        conn.execute(
            "INSERT OR IGNORE INTO nav_items (key, label, icon, enabled, sort_order, is_system) VALUES (?,?,?,?,?,?)",
            (key, label, icon, enabled, sort_order, is_sys))

    # ── navbar_position default ────────────────────────────────────────────────────
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('navbar_position','top')")
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('navbar_style','pill')")

    # ── Default guest services ────────────────────────────────────────────────────
    svc_defaults = [
        ('Front Desk',        'Reception', '🏨', '0',    'Available 24/7', 1),
        ('Room Service',      'F&B',       '🍽',  '1',   'Order food & beverages', 2),
        ('Housekeeping',      'Rooms',     '🛎',  '2',   'Cleaning & laundry', 3),
        ('Concierge',         'Reception', '🗺',  '3',   'Tours & recommendations', 4),
        ('Maintenance',       'Facilities','🔧',  '4',   'Technical support', 5),
        ('Spa & Wellness',    'Leisure',   '💆',  '5',   'Book spa treatments', 6),
        ('Business Center',   'Business',  '💼',  '6',   'Printing & conferencing', 7),
        ('Airport Transfer',  'Transport', '✈',   '7',   'Book a transfer', 8),
    ]
    for row in svc_defaults:
        conn.execute("INSERT OR IGNORE INTO guest_services (name,category,icon,phone,description,sort_order) SELECT ?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM guest_services WHERE name=?)",
            (*row, row[0]))

    # ── VIP Channel Access ──────────────────────────────────────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS vip_channel_access (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            room_id INTEGER NOT NULL,
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (channel_id) REFERENCES channels(id),
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            UNIQUE(channel_id, room_id)
        )
    ''')

    conn.commit()
    conn.close()


# ─── Passive Presence Middleware ─────────────────────────────────────────────

@app.before_request
def track_room_presence():
    """
    Every API request that carries X-Room-Token passively updates
    last_seen for that room. No extra endpoint needed.
    """
    token = request.headers.get('X-Room-Token', '').strip()
    if not token:
        return  # not a room client — admin or unregistered
    ua = request.headers.get('User-Agent', '')[:200]
    conn = get_db()
    conn.execute(
        """UPDATE rooms
           SET last_seen = CURRENT_TIMESTAMP,
               user_agent = ?,
               online = 1
           WHERE room_token = ?""",
        (ua, token)
    )

    conn.commit()
    conn.close()


# ─── TV Platform Redirect ─────────────────────────────────────────────────────

_TV_UA_SIGNALS = ('TV', 'CrKey', 'Chromecast')

@app.before_request
def redirect_tv_clients():
    # Skip non-page paths — API calls, VOD routes, admin, and the /tv destination
    # itself (prevents redirect loop). Only redirect HTML page navigations.
    if request.path.startswith(('/api/', '/vod/', '/admin', '/tv', '/internal/')):
        return
    ua = request.headers.get('User-Agent', '')
    if 'Android' in ua and any(sig in ua for sig in _TV_UA_SIGNALS):
        return redirect('/tv?platform=tv', 302)


# ─── Auth ─────────────────────────────────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user = data
        except:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            if data.get('role') not in ['admin', 'operator']:
                return jsonify({'error': 'Admin required'}), 403
            request.user = data
        except:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated


# Register storage admin JSON API endpoints used by /vod/admin/storage.
# Keep these unwrapped here because the storage UI does not use JWT admin auth.
create_storage_admin_routes(app)


# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    pw = hashlib.sha256(data.get('password', '').encode()).hexdigest()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
                        (data.get('username'), pw)).fetchone()
    conn.close()
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    token = jwt.encode({
        'id': user['id'], 'username': user['username'], 'role': user['role'],
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, app.config['SECRET_KEY'], algorithm='HS256')
    return jsonify({'token': token, 'user': {'id': user['id'], 'username': user['username'], 'role': user['role']}})

@app.route('/api/auth/me', methods=['GET'])
@token_required
def me():
    return jsonify(request.user)


# ─── Channels ─────────────────────────────────────────────────────────────────

@app.route('/api/channels', methods=['GET'])
def get_channels():
    conn = get_db()
    group_id    = request.args.get('group_id')
    active_only = request.args.get('active', '1')
    search      = request.args.get('search', '').strip()
    limit       = _safe_int(request.args.get('limit'), 500)
    offset      = _safe_int(request.args.get('offset'), 0)
    room_token  = request.headers.get('X-Room-Token', '').strip()

    # Resolve room token → room_id for package filtering
    room_id = None
    if room_token:
        room_row = conn.execute("SELECT id FROM rooms WHERE room_token=?", (room_token,)).fetchone()
        if room_row:
            room_id = room_row['id']

    # Build WHERE clauses
    wheres = []
    params = []

    if active_only == '1':
        wheres.append('c.active = 1')
    if group_id:
        wheres.append('c.media_group_id = ?')
        params.append(int(group_id))
    if search:
        wheres.append('(c.name LIKE ? OR c.logo LIKE ?)')
        params += [f'%{search}%', f'%{search}%']

    # Package access filter: if room token provided, only return channels
    # the room has access to via packages OR VIP grant. No packages = no access.
    if room_id is not None:
        wheres.append("""(
            EXISTS (
                SELECT 1 FROM package_channels pc
                JOIN room_packages rp ON rp.package_id=pc.package_id
                WHERE pc.channel_id=c.id AND rp.room_id=?
            )
            OR EXISTS (
                SELECT 1 FROM vip_channel_access vca
                WHERE vca.channel_id=c.id AND vca.room_id=?
            )
        )""")
        params.append(room_id)
        params.append(room_id)

    base = (
        "SELECT c.*, mg.name as group_name "
        "FROM channels c "
        "LEFT JOIN media_groups mg ON c.media_group_id = mg.id"
    )
    where_clause = (' WHERE ' + ' AND '.join(wheres)) if wheres else ''
    order_clause = ' ORDER BY COALESCE(c.direct_play_num, 9999), c.id'

    q = base + where_clause + order_clause + ' LIMIT ? OFFSET ?'
    rows = conn.execute(q, params + [limit, offset]).fetchall()
    channels = [dict(r) for r in rows]
    conn.close()

    # Support both flat-array consumers (TV frontend) and
    # paginated-object consumers (admin) via ?envelope=1
    if request.args.get('envelope') == '1':
        conn2 = get_db()
        total = conn2.execute('SELECT COUNT(*) FROM channels c' + where_clause, params).fetchone()[0]
        conn2.close()
        return jsonify({'channels': channels, 'total': total, 'limit': limit, 'offset': offset})
    return jsonify(channels)

@app.route('/api/channels/<int:cid>', methods=['GET'])
def get_channel(cid):
    conn = get_db()
    ch = conn.execute("SELECT c.*, mg.name as group_name FROM channels c LEFT JOIN media_groups mg ON c.media_group_id=mg.id WHERE c.id=?", (cid,)).fetchone()
    conn.close()
    if not ch:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(ch))

@app.route('/api/channels', methods=['POST'])
@admin_required
def create_channel():
    d = request.json
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO channels (name, stream_url, logo, tvg_id, tvg_logo_url, group_title, media_group_id, direct_play_num, active, channel_type) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (d['name'], d['stream_url'], d.get('logo',''), d.get('tvg_id',''), d.get('tvg_logo_url',''),
         d.get('group_title',''), d.get('media_group_id',1), d.get('direct_play_num'), d.get('active',1),
         d.get('channel_type','stream_udp')))
    conn.commit()
    ch = dict(conn.execute("SELECT * FROM channels WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(ch), 201

@app.route('/api/channels/<int:cid>', methods=['PUT'])
@admin_required
def update_channel(cid):
    d = request.json
    conn = get_db()
    conn.execute(
        "UPDATE channels SET name=?, stream_url=?, logo=?, tvg_id=?, tvg_logo_url=?, group_title=?, media_group_id=?, direct_play_num=?, active=?, temporarily_unavailable=?, channel_type=? WHERE id=?",
        (d['name'], d['stream_url'], d.get('logo',''), d.get('tvg_id',''), d.get('tvg_logo_url',''),
         d.get('group_title',''), d.get('media_group_id',1), d.get('direct_play_num'),
         d.get('active',1), d.get('temporarily_unavailable',0), d.get('channel_type','stream_udp'), cid))
    conn.commit()
    ch = dict(conn.execute("SELECT * FROM channels WHERE id=?", (cid,)).fetchone())
    conn.close()
    return jsonify(ch)

@app.route('/api/channels/<int:cid>', methods=['DELETE'])
@admin_required
def delete_channel(cid):
    conn = get_db()
    conn.execute("DELETE FROM channels WHERE id=?", (cid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


# ─── M3U Import / Export ──────────────────────────────────────────────────────

import re as _re

def _parse_m3u(text):
    """Parse M3U text into list of channel dicts."""
    channels = []
    lines = text.replace('\r\n', '\n').replace('\r', '\n').splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF'):
            tvg_id    = (_re.search(r'tvg-id="([^"]*)"'    , line) or _re.Match.__new__(_re.Match)) 
            tvg_logo  = _re.search(r'tvg-logo="([^"]*)"',   line)
            group     = _re.search(r'group-title="([^"]*)"', line)
            name_m    = _re.search(r',(.+)$',               line)
            url = lines[i+1].strip() if i+1 < len(lines) else ''
            if url and not url.startswith('#'):
                channels.append({
                    'name':         name_m.group(1).strip()  if name_m  else 'Unknown',
                    'tvg_id':       (_re.search(r'tvg-id="([^"]*)"',  line) or type('x',(object,),{'group':lambda s,n:''})()).group(1),
                    'tvg_logo_url': tvg_logo.group(1) if tvg_logo else '',
                    'group_title':  group.group(1)    if group    else 'Undefined',
                    'stream_url':   url,
                })
            i += 2
        else:
            i += 1
    return channels
# ─── M3U Import / Export ──────────────────────────────────────────────────────

import re as _re
from collections import Counter as _Counter

def _parse_m3u(text):
    """Parse M3U/M3U8 playlist text into list of channel dicts."""
    results = []
    lines   = text.replace('\r\n', '\n').replace('\r', '\n').splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF'):
            m_id   = _re.search(r'tvg-id="([^"]*)"',     line)
            m_logo = _re.search(r'tvg-logo="([^"]*)"',   line)
            m_grp  = _re.search(r'group-title="([^"]*)"',line)
            m_name = _re.search(r',(.+)$',               line)
            url    = lines[i+1].strip() if i+1 < len(lines) else ''
            if url and not url.startswith('#'):
                results.append({
                    'name':         (m_name.group(1).strip() if m_name  else 'Unknown'),
                    'tvg_id':       (m_id.group(1)           if m_id    else ''),
                    'tvg_logo_url': (m_logo.group(1)         if m_logo  else ''),
                    'group_title':  (m_grp.group(1)          if m_grp   else 'Undefined'),
                    'stream_url':   url,
                })
            i += 2
        else:
            i += 1
    return results


@app.route('/api/channels/preview-m3u', methods=['POST'])
@admin_required
def preview_m3u():
    """Return group summary of an M3U without importing."""
    if request.content_type and 'multipart' in request.content_type:
        f    = request.files.get('file')
        text = f.read().decode('utf-8', errors='replace') if f else ''
    else:
        text = (request.json or {}).get('m3u', '')
    parsed = _parse_m3u(text)
    groups = _Counter()
    for ch in parsed:
        for g in ch['group_title'].split(';'):
            groups[g.strip()] += 1
    return jsonify({
        'total':  len(parsed),
        'groups': [{'name': k, 'count': v}
                   for k, v in sorted(groups.items(), key=lambda x: -x[1])]
    })


@app.route('/api/channels/import-m3u', methods=['POST'])
@admin_required
def import_m3u():
    """
    Import channels from M3U.
    Accepts:
      - JSON {url, m3u, mode, group_filter, max_channels, channel_type}
      - multipart form (field: file)
    mode: append (default) | replace
    """
    import urllib.request as _urlreq

    if request.content_type and 'multipart' in request.content_type:
        f            = request.files.get('file')
        text         = f.read().decode('utf-8', errors='replace') if f else ''
        mode         = request.form.get('mode', 'append')
        group_filter = request.form.get('group_filter', '').strip()
        max_ch       = _safe_int(request.form.get('max_channels'), 0)
        ctype        = request.form.get('channel_type', 'm3u')
    else:
        body         = request.json or {}
        text         = body.get('m3u', '')
        url          = body.get('url', '').strip()
        mode         = body.get('mode', 'append')
        group_filter = body.get('group_filter', '').strip()
        max_ch       = int(body.get('max_channels', 0) or 0)
        ctype        = body.get('channel_type', 'm3u')

        # Fetch from remote URL if provided
        if url and not text:
            try:
                req2 = _urlreq.Request(url, headers={'User-Agent': 'NexVision/1.0'})
                with _urlreq.urlopen(req2, timeout=30) as resp:
                    text = resp.read().decode('utf-8', errors='replace')
            except Exception as e:
                return jsonify({'error': f'Failed to fetch M3U from URL: {e}'}), 400

        # Use bundled server file if nothing provided
        if not text:
            server_m3u = os.path.join(BASE_DIR, 'iptv-org-channels.m3u')
            if os.path.exists(server_m3u):
                with open(server_m3u, encoding='utf-8', errors='replace') as mf:
                    text = mf.read()
            else:
                return jsonify({'error': 'No M3U content provided. Supply a URL, paste text, or place iptv-org-channels.m3u next to app.py'}), 400

    parsed = _parse_m3u(text)

    if group_filter:
        wanted = {g.strip().lower() for g in group_filter.split(',')}
        parsed = [c for c in parsed
                  if any(w in g.lower()
                         for g in c['group_title'].split(';')
                         for w in wanted)]

    if max_ch and max_ch > 0:
        parsed = parsed[:max_ch]

    conn = get_db()
    cur  = conn.cursor()

    if mode == 'replace':
        cur.execute("DELETE FROM channels")
        try:
            cur.execute("DELETE FROM sqlite_sequence WHERE name='channels'")
        except Exception:
            pass

    # Build group map
    existing = {r['name']: r['id']
                for r in conn.execute("SELECT id,name FROM media_groups").fetchall()}
    gmap = dict(existing)
    groups_created = 0

    inserted = 0
    skipped  = 0
    for ch in parsed:
        primary = ch['group_title'].split(';')[0].strip() or 'Undefined'
        if primary not in gmap:
            gid = cur.execute(
                "INSERT INTO media_groups (name, active) VALUES (?,1)", (primary,)
            ).lastrowid
            gmap[primary] = gid
            groups_created += 1
        try:
            cur.execute(
                "INSERT INTO channels "
                "(name, stream_url, tvg_id, tvg_logo_url, group_title, media_group_id, active, channel_type) "
                "VALUES (?,?,?,?,?,?,1,?)",
                (ch['name'], ch['stream_url'], ch['tvg_id'],
                 ch['tvg_logo_url'], ch['group_title'], gmap[primary], ctype)
            )
            inserted += 1
        except Exception:
            skipped += 1

    conn.commit()
    conn.close()
    return jsonify({'imported': inserted, 'skipped': skipped,
                    'total_parsed': len(parsed), 'groups_created': groups_created})



@app.route('/api/channels/export-m3u', methods=['GET'])
def export_m3u():
    """Download all active channels as an M3U playlist."""
    conn     = get_db()
    channels = conn.execute(
        "SELECT * FROM channels WHERE active=1 ORDER BY id"
    ).fetchall()
    conn.close()

    lines = ['#EXTM3U']
    for ch in channels:
        num  = ch['direct_play_num'] or ch['id']
        logo = ch['tvg_logo_url'] or ch['logo'] or ''
        tid  = ch['tvg_id']       or ''
        grp  = ch['group_title']  or 'Undefined'
        lines.append(
            f'#EXTINF:-1 tvg-id="{tid}" tvg-logo="{logo}" '
            f'group-title="{grp}" tvg-chno="{num}",{ch["name"]}'
        )
        lines.append(ch['stream_url'])

    from flask import Response
    return Response(
        '\n'.join(lines),
        mimetype='application/x-mpegurl',
        headers={'Content-Disposition': 'attachment; filename="nexvision.m3u"'}
    )


# ─── Media Groups ─────────────────────────────────────────────────────────────

@app.route('/api/media-groups', methods=['GET'])
def get_media_groups():
    conn = get_db()
    groups = [dict(r) for r in conn.execute("SELECT mg.*, COUNT(c.id) as channel_count FROM media_groups mg LEFT JOIN channels c ON c.media_group_id=mg.id GROUP BY mg.id").fetchall()]
    conn.close()
    return jsonify(groups)

@app.route('/api/media-groups', methods=['POST'])
@admin_required
def create_media_group():
    d = request.json
    conn = get_db()
    cur = conn.execute("INSERT INTO media_groups (name, active) VALUES (?,?)", (d['name'], d.get('active',1)))
    conn.commit()
    g = dict(conn.execute("SELECT * FROM media_groups WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(g), 201

@app.route('/api/media-groups/<int:gid>', methods=['DELETE'])
@admin_required
def delete_media_group(gid):
    conn = get_db()
    conn.execute("DELETE FROM media_groups WHERE id=?", (gid,))

    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ─── VoD ──────────────────────────────────────────────────────────────────────

@app.route('/api/vod', methods=['GET'])
def get_vod():
    conn = get_db()
    genre  = request.args.get('genre')
    year   = request.args.get('year')
    lang   = request.args.get('language')
    search = request.args.get('search')
    room_token = request.headers.get('X-Room-Token', '').strip()

    # Resolve room token → room_id for package filtering
    room_id = None
    if room_token:
        room_row = conn.execute("SELECT id FROM rooms WHERE room_token=?", (room_token,)).fetchone()
        if room_row:
            room_id = room_row['id']

    q = "SELECT * FROM vod_movies WHERE active=1"
    params = []
    if genre:
        q += " AND genre LIKE ?"
        params.append(f'%{genre}%')
    if year:
        q += " AND year=?"
        params.append(year)
    if lang:
        q += " AND language=?"
        params.append(lang)
    if search:
        q += " AND title LIKE ?"
        params.append(f'%{search}%')
    # ?featured=1 — skip package filter, return top movie for hero banner
    featured = request.args.get('featured') == '1'
    if room_id is not None and not featured:
        q += """ AND EXISTS (
            SELECT 1 FROM package_vod pv
            JOIN room_packages rp ON rp.package_id=pv.package_id
            WHERE pv.vod_id=vod_movies.id AND rp.room_id=?
        )"""
        params.append(room_id)
    q += " ORDER BY rating DESC"
    if featured:
        q += " LIMIT 1"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    # Rebuild stream_url host dynamically so phone/APK clients on WiFi
    # receive the correct server IP instead of the hardcoded localhost address
    req_host = request.host_url.rstrip('/')
    movies = []
    for r in rows:
        m = dict(r)
        su = m.get('stream_url') or ''
        if su and '/vod/hls/' in su:
            path = su[su.index('/vod/hls/'):]
            m['stream_url'] = req_host + path
        movies.append(m)
    return jsonify(movies)

@app.route('/api/vod/<int:mid>', methods=['GET'])
def get_movie(mid):
    conn = get_db()
    m = conn.execute("SELECT * FROM vod_movies WHERE id=?", (mid,)).fetchone()
    conn.close()
    if not m:
        return jsonify({'error': 'Not found'}), 404
    mv = dict(m)
    su = mv.get('stream_url') or ''
    if su and '/vod/hls/' in su:
        path = su[su.index('/vod/hls/'):]
        mv['stream_url'] = request.host_url.rstrip('/') + path
    return jsonify(mv)

@app.route('/api/vod', methods=['POST'])
@admin_required
def create_movie():
    d = request.json
    conn = get_db()
    cur = conn.execute("INSERT INTO vod_movies (title, description, genre, year, language, runtime, rating, poster, backdrop, stream_url, price) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (d['title'], d.get('description',''), d.get('genre',''), d.get('year'), d.get('language','English'),
         d.get('runtime',0), d.get('rating',0), d.get('poster',''), d.get('backdrop',''), d.get('stream_url',''), d.get('price',0)))
    conn.commit()
    m = dict(conn.execute("SELECT * FROM vod_movies WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(m), 201

@app.route('/api/vod/<int:mid>', methods=['PUT'])
@admin_required
def update_movie(mid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE vod_movies SET title=?, description=?, genre=?, year=?, language=?, runtime=?, rating=?, poster=?, backdrop=?, stream_url=?, price=?, active=? WHERE id=?",
        (d['title'], d.get('description',''), d.get('genre',''), d.get('year'), d.get('language','English'),
         d.get('runtime',0), d.get('rating',0), d.get('poster',''), d.get('backdrop',''), d.get('stream_url',''), d.get('price',0), d.get('active',1), mid))
    conn.commit()
    m = dict(conn.execute("SELECT * FROM vod_movies WHERE id=?", (mid,)).fetchone())
    conn.close()
    return jsonify(m)

@app.route('/api/vod/<int:mid>', methods=['DELETE'])
@admin_required
def delete_movie(mid):
    conn = get_db()
    conn.execute("DELETE FROM vod_movies WHERE id=?", (mid,))

    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/vod/genres', methods=['GET'])
def get_genres():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT genre FROM vod_movies WHERE active=1 AND genre!=''").fetchall()
    genres = list(set(g for r in rows for g in r['genre'].split('/')))
    conn.close()
    return jsonify(sorted(genres))

@app.route('/api/vod/packages', methods=['GET'])
def get_packages():
    conn = get_db()
    pkgs = [dict(r) for r in conn.execute("SELECT * FROM vod_packages WHERE active=1").fetchall()]
    conn.close()
    return jsonify(pkgs)


# ─── Radio ────────────────────────────────────────────────────────────────────

@app.route('/api/radio', methods=['GET'])
def get_radio():
    conn = get_db()
    country = request.args.get('country')
    room_token = request.headers.get('X-Room-Token', '').strip()

    room_id = None
    if room_token:
        room_row = conn.execute("SELECT id FROM rooms WHERE room_token=?", (room_token,)).fetchone()
        if room_row:
            room_id = room_row['id']

    q = "SELECT * FROM radio_stations WHERE active=1"
    params = []
    if country:
        q += " AND country=?"
        params.append(country)
    if room_id is not None:
        q += """ AND EXISTS (
            SELECT 1 FROM package_radio pr
            JOIN room_packages rp ON rp.package_id=pr.package_id
            WHERE pr.radio_id=radio_stations.id AND rp.room_id=?
        )"""
        params.append(room_id)
    q += " ORDER BY name"
    stations = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return jsonify(stations)

@app.route('/api/radio/countries', methods=['GET'])
def get_radio_countries():
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT country FROM radio_stations WHERE active=1 ORDER BY country").fetchall()
    conn.close()
    return jsonify([r['country'] for r in rows])

@app.route('/api/radio', methods=['POST'])
@admin_required
def create_station():
    d = request.json
    conn = get_db()
    cur = conn.execute("INSERT INTO radio_stations (name, country, genre, stream_url, logo) VALUES (?,?,?,?,?)",
        (d['name'], d.get('country',''), d.get('genre',''), d['stream_url'], d.get('logo','')))
    conn.commit()
    s = dict(conn.execute("SELECT * FROM radio_stations WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(s), 201

@app.route('/api/radio/<int:sid>', methods=['DELETE'])
@admin_required
def delete_station(sid):
    conn = get_db()
    conn.execute("DELETE FROM radio_stations WHERE id=?", (sid,))

    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ─── Content Pages ────────────────────────────────────────────────────────────

@app.route('/api/content', methods=['GET'])
def get_content_pages():
    conn = get_db()
    pages = [dict(r) for r in conn.execute("SELECT * FROM content_pages WHERE active=1 ORDER BY group_name, name").fetchall()]
    conn.close()
    return jsonify(pages)

@app.route('/api/content/<int:pid>', methods=['GET'])
def get_content_page(pid):
    conn = get_db()
    page = conn.execute("SELECT * FROM content_pages WHERE id=?", (pid,)).fetchone()
    if not page:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    # Return ALL fields including photo_url and content_html for TV display
    items = [dict(r) for r in conn.execute(
        "SELECT id, page_id, title, description, content_html, photo_url, image, active, sort_order "
        "FROM content_items WHERE page_id=? AND active=1 ORDER BY sort_order", (pid,)).fetchall()]
    # Attach gallery images to each item
    for item in items:
        item['images'] = [dict(r) for r in conn.execute(
            "SELECT id, url, position, fit, sort_order FROM content_item_images WHERE item_id=? ORDER BY sort_order, id",
            (item['id'],)).fetchall()]
    conn.close()
    return jsonify({**dict(page), 'items': items})

@app.route('/api/content', methods=['POST'])
@admin_required
def create_content_page():
    d = request.json
    conn = get_db()
    cur = conn.execute("INSERT INTO content_pages (name, group_name, template, active) VALUES (?,?,?,?)",
        (d['name'], d.get('group_name','Hotel'), d.get('template','Default'), d.get('active',1)))
    pid = cur.lastrowid
    for item in d.get('items', []):
        conn.execute("INSERT INTO content_items (page_id, title, description, image) VALUES (?,?,?,?)",
            (pid, item['title'], item.get('description',''), item.get('image','')))
    conn.commit()
    page = dict(conn.execute("SELECT * FROM content_pages WHERE id=?", (pid,)).fetchone())
    conn.close()
    return jsonify(page), 201

@app.route('/api/content/<int:pid>', methods=['DELETE'])
@admin_required
def delete_content_page(pid):
    conn = get_db()
    conn.execute("DELETE FROM content_items WHERE page_id=?", (pid,))
    conn.execute("DELETE FROM content_pages WHERE id=?", (pid,))

    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ─── Rooms / Devices ─────────────────────────────────────────────────────────

@app.route('/api/rooms', methods=['GET'])
@admin_required
def get_rooms():
    conn = get_db()
    rows = conn.execute("""
        SELECT r.*, s.name as skin_name,
               CASE
                 WHEN r.last_seen IS NULL THEN 0
                 WHEN (strftime('%s','now') - strftime('%s', r.last_seen)) <= ?
                 THEN 1 ELSE 0
               END AS online
        FROM rooms r LEFT JOIN skins s ON r.skin_id=s.id
        ORDER BY r.room_number
    """, (ONLINE_MINUTES * 60,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/rooms', methods=['POST'])
@admin_required
def create_room():
    d = request.json
    room_num = d.get('room_number', '').strip()
    if not room_num:
        return jsonify({'error': 'room_number required'}), 400
    token = str(uuid.uuid4())
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO rooms (room_number, tv_name, skin_id, online, room_token) VALUES (?,?,?,0,?)",
            (room_num, d.get('tv_name', f'TV-{room_num}'), d.get('skin_id', 1), token)
        )
        conn.commit()
        room = dict(conn.execute("SELECT * FROM rooms WHERE id=?", (cur.lastrowid,)).fetchone())
        conn.close()
        return jsonify(room), 201
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 409


@app.route('/api/rooms/<int:rid>', methods=['DELETE'])
@admin_required
def delete_room(rid):
    conn = get_db()
    conn.execute("DELETE FROM rooms WHERE id=?", (rid,))

    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/rooms/<int:rid>/token', methods=['POST'])
@admin_required
def regenerate_token(rid):
    """Regenerate the room token (e.g. when a device is replaced)."""
    new_token = str(uuid.uuid4())
    conn = get_db()
    conn.execute("UPDATE rooms SET room_token=?, last_seen=NULL, online=0 WHERE id=?",
                 (new_token, rid))
    conn.commit()
    room = dict(conn.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone())
    conn.close()
    return jsonify(room)

@app.route('/api/rooms/<int:rid>', methods=['PUT'])
@admin_required
def update_room(rid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE rooms SET tv_name=?, skin_id=?, online=? WHERE id=?",
        (d.get('tv_name',''), d.get('skin_id',1), d.get('online',0), rid))
    _bump_stamp(conn)  # notify TV clients when room skin assignment changes
    conn.commit()
    r = dict(conn.execute("SELECT * FROM rooms WHERE id=?", (rid,)).fetchone())
    conn.close()
    return jsonify(r)

@app.route('/api/rooms/setup/<token>', methods=['GET'])
def room_setup(token):
    """Returns room info for a given setup token — called once during device setup."""
    conn = get_db()
    room = conn.execute("SELECT * FROM rooms WHERE room_token=?", (token,)).fetchone()
    conn.close()
    if not room:
        return jsonify({'error': 'Invalid token'}), 404
    return jsonify({'room_number': room['room_number'], 'tv_name': room['tv_name'],
                    'token': token, 'status': 'ok'})


@app.route('/api/rooms/register', methods=['POST'])
def room_register():
    """
    TV/STB self-registration by room number.
    The technician types the room number on the device — no UUID needed.
    Returns the room token so the client can store it in localStorage.
    """
    d = request.json or {}
    room_number = str(d.get('room_number', '')).strip()
    if not room_number:
        return jsonify({'error': 'room_number required'}), 400

    conn = get_db()
    room = conn.execute(
        "SELECT * FROM rooms WHERE LOWER(room_number) = LOWER(?)", (room_number,)
    ).fetchone()

    if not room:
        conn.close()
        return jsonify({'error': f'Room {room_number} not found. Ask admin to create it first.'}), 404

    # Ensure room has a token (generate if missing)
    token = room['room_token']
    if not token:
        token = str(__import__('uuid').uuid4())
        conn.execute("UPDATE rooms SET room_token=? WHERE id=?", (token, room['id']))
        conn.commit()

    # Log the registration event
    ua = request.headers.get('User-Agent', '')[:200]
    conn.execute(
        "UPDATE rooms SET last_seen=CURRENT_TIMESTAMP, user_agent=?, online=1 WHERE id=?",
        (ua, room['id'])
    )

    conn.commit()
    conn.close()

    return jsonify({
        'status': 'ok',
        'room_number': room['room_number'],
        'tv_name': room['tv_name'] or f"TV-{room['room_number']}",
        'token': token
    })



# ─── Media Groups PUT ─────────────────────────────────────────────────────────

@app.route('/api/media-groups/<int:gid>', methods=['PUT'])
@admin_required
def update_media_group(gid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE media_groups SET name=?, active=? WHERE id=?",
                 (d['name'], d.get('active', 1), gid))
    conn.commit()
    g = dict(conn.execute("SELECT mg.*, COUNT(c.id) as channel_count FROM media_groups mg LEFT JOIN channels c ON c.media_group_id=mg.id WHERE mg.id=? GROUP BY mg.id", (gid,)).fetchone())
    conn.close()
    return jsonify(g)


# ─── Radio PUT ────────────────────────────────────────────────────────────────

@app.route('/api/radio/<int:sid>', methods=['PUT'])
@admin_required
def update_station(sid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE radio_stations SET name=?, country=?, genre=?, stream_url=?, logo=?, active=? WHERE id=?",
        (d['name'], d.get('country',''), d.get('genre',''), d['stream_url'],
         d.get('logo',''), d.get('active',1), sid))
    conn.commit()
    s = dict(conn.execute("SELECT * FROM radio_stations WHERE id=?", (sid,)).fetchone())
    conn.close()
    return jsonify(s)


# ─── Content Pages PUT + Items CRUD ──────────────────────────────────────────

@app.route('/api/content/<int:pid>', methods=['PUT'])
@admin_required
def update_content_page(pid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE content_pages SET name=?, group_name=?, template=?, active=? WHERE id=?",
        (d['name'], d.get('group_name','Hotel'), d.get('template','Default'), d.get('active',1), pid))
    _bump_stamp(conn)
    conn.commit()
    page = dict(conn.execute("SELECT * FROM content_pages WHERE id=?", (pid,)).fetchone())
    conn.close()
    return jsonify(page)

@app.route('/api/content/<int:pid>/items', methods=['GET'])
def get_content_items(pid):
    conn = get_db()
    items = [dict(r) for r in conn.execute(
        "SELECT * FROM content_items WHERE page_id=? ORDER BY sort_order, id", (pid,)).fetchall()]
    for item in items:
        item['images'] = [dict(r) for r in conn.execute(
            "SELECT id, url, position, fit, sort_order FROM content_item_images WHERE item_id=? ORDER BY sort_order, id",
            (item['id'],)).fetchall()]
    conn.close()
    return jsonify(items)

@app.route('/api/content/<int:pid>/items', methods=['POST'])
@admin_required
def create_content_item(pid):
    d = request.json
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO content_items (page_id, title, description, image, content_html, photo_url, active, sort_order) VALUES (?,?,?,?,?,?,?,?)",
        (pid, d['title'], d.get('description',''), d.get('image',''),
         d.get('content_html',''), d.get('photo_url', d.get('image','')),
         d.get('active',1), d.get('sort_order',0)))
    _bump_stamp(conn)
    conn.commit()
    item = dict(conn.execute("SELECT * FROM content_items WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(item), 201

@app.route('/api/content/items/<int:iid>', methods=['PUT'])
@admin_required
def update_content_item(iid):
    d = request.json
    conn = get_db()
    conn.execute(
        "UPDATE content_items SET title=?, description=?, image=?, content_html=?, photo_url=?, active=?, sort_order=? WHERE id=?",
        (d['title'], d.get('description',''), d.get('image',''),
         d.get('content_html',''), d.get('photo_url', d.get('image','')),
         d.get('active',1), d.get('sort_order',0), iid))
    _bump_stamp(conn)
    conn.commit()
    item = dict(conn.execute("SELECT * FROM content_items WHERE id=?", (iid,)).fetchone())
    conn.close()
    return jsonify(item)

@app.route('/api/content/items/<int:iid>', methods=['DELETE'])
@admin_required
def delete_content_item(iid):
    conn = get_db()
    conn.execute("DELETE FROM content_items WHERE id=?", (iid,))

    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ─── VoD Packages CRUD ───────────────────────────────────────────────────────

@app.route('/api/vod/packages', methods=['POST'])
@admin_required
def create_package():
    d = request.json
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO vod_packages (name, description, price, duration_hours, active) VALUES (?,?,?,?,?)",
        (d['name'], d.get('description',''), d.get('price',0), d.get('duration_hours',24), d.get('active',1)))
    conn.commit()
    p = dict(conn.execute("SELECT * FROM vod_packages WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(p), 201

@app.route('/api/vod/packages/<int:pid>', methods=['PUT'])
@admin_required
def update_package(pid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE vod_packages SET name=?, description=?, price=?, duration_hours=?, active=? WHERE id=?",
        (d['name'], d.get('description',''), d.get('price',0), d.get('duration_hours',24), d.get('active',1), pid))
    conn.commit()
    p = dict(conn.execute("SELECT * FROM vod_packages WHERE id=?", (pid,)).fetchone())
    conn.close()
    return jsonify(p)

@app.route('/api/vod/packages/<int:pid>', methods=['DELETE'])
@admin_required
def delete_package(pid):
    conn = get_db()
    conn.execute("DELETE FROM vod_packages WHERE id=?", (pid,))

    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/vod/packages/all', methods=['GET'])
@admin_required
def get_all_packages():
    conn = get_db()
    pkgs = [dict(r) for r in conn.execute("SELECT * FROM vod_packages ORDER BY id").fetchall()]
    conn.close()
    return jsonify(pkgs)


# ─── Skins PUT / DELETE ───────────────────────────────────────────────────────

# ─── Skins ────────────────────────────────────────────────────────────────────

@app.route('/api/skins', methods=['GET'])
@admin_required
def get_skins():
    conn = get_db()
    skins = [dict(r) for r in conn.execute("SELECT * FROM skins").fetchall()]
    conn.close()
    return jsonify(skins)

@app.route('/api/skins', methods=['POST'])
@admin_required
def create_skin():
    d = request.json
    conn = get_db()
    cur = conn.execute("INSERT INTO skins (name, template, background_image, is_default, theme_data) VALUES (?,?,?,?,?)",
        (d['name'], d.get('template','Default Skin'), d.get('background_image',''), 0, json.dumps(d.get('theme_data',{}))))
    _bump_stamp(conn)
    conn.commit()
    s = dict(conn.execute("SELECT * FROM skins WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(s), 201


# ─── Skins PUT / DELETE ───────────────────────────────────────────────────────

@app.route('/api/skin', methods=['GET'])
def get_room_skin():
    """Returns the skin assigned to this room (via X-Room-Token header), or the default skin."""
    token = request.headers.get('X-Room-Token', '')
    conn = get_db()
    row = None
    if token:
        row = conn.execute("""
            SELECT s.* FROM rooms r
            JOIN skins s ON r.skin_id = s.id
            WHERE r.room_token = ?
        """, (token,)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM skins WHERE is_default=1").fetchone()
    conn.close()
    if not row:
        return jsonify({'background_image': '', 'theme_data': '{}', 'name': 'Default'})
    return jsonify(dict(row))


@app.route('/api/skins/<int:sid>', methods=['PUT'])
@admin_required
def update_skin(sid):
    d = request.json
    conn = get_db()
    if d.get('is_default'):
        conn.execute("UPDATE skins SET is_default=0")
        conn.execute("UPDATE skins SET is_default=1 WHERE id=?", (sid,))
    conn.execute("UPDATE skins SET name=?, template=?, background_image=? WHERE id=?",
        (d['name'], d.get('template','Default Skin'), d.get('background_image',''), sid))
    _bump_stamp(conn)   # notify TV clients that skin changed
    conn.commit()
    s = dict(conn.execute("SELECT * FROM skins WHERE id=?", (sid,)).fetchone())
    conn.close()
    return jsonify(s)

@app.route('/api/skins/<int:sid>', methods=['DELETE'])
@admin_required
def delete_skin(sid):
    conn = get_db()
    sk = conn.execute("SELECT * FROM skins WHERE id=?", (sid,)).fetchone()
    if not sk:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    if sk['is_default']:
        conn.close()
        return jsonify({'error': 'Cannot delete the default skin'}), 400
    conn.execute("UPDATE rooms SET skin_id=1 WHERE skin_id=?", (sid,))
    conn.execute("DELETE FROM skins WHERE id=?", (sid,))
    _bump_stamp(conn)  # notify TV clients after skin delete/remap

    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ─── Android TV Device Heartbeat ─────────────────────────────────────────────

@app.route('/api/device/heartbeat', methods=['POST'])
def device_heartbeat():
    d = request.json or {}
    mac = (d.get('mac_address') or '').strip().upper()
    if not mac:
        return jsonify({'error': 'mac_address required'}), 400
    app_version = (d.get('app_version') or '').strip()[:50]
    room_number = (d.get('room_number') or '').strip()[:50]
    device_name = (d.get('device_name') or '').strip()[:100]
    conn = get_db()
    conn.execute("""
        INSERT INTO devices (mac_address, room_number, device_name, app_version, last_seen, status)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'active')
        ON CONFLICT(mac_address) DO UPDATE SET
            last_seen    = CURRENT_TIMESTAMP,
            app_version  = excluded.app_version,
            room_number  = CASE WHEN excluded.room_number != '' THEN excluded.room_number ELSE room_number END,
            device_name  = CASE WHEN excluded.device_name != '' THEN excluded.device_name ELSE device_name END,
            status       = 'active'
    """, (mac, room_number, device_name, app_version))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


@app.route('/api/devices', methods=['GET'])
@admin_required
def get_devices():
    conn = get_db()
    rows = conn.execute("""
        SELECT *,
               CASE
                 WHEN last_seen IS NULL THEN 0
                 WHEN (strftime('%s','now') - strftime('%s', last_seen)) <= 600
                 THEN 1 ELSE 0
               END AS online
        FROM devices
        ORDER BY last_seen DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ─── Reports ─────────────────────────────────────────────────────────────────

@app.route('/api/reports/rooms', methods=['GET'])
@admin_required
def report_rooms():
    days = _safe_int(request.args.get('days'), 30)
    conn = get_db()
    rows = conn.execute("""
        SELECT r.room_number, r.tv_name,
               COUNT(wh.id)               AS sessions,
               COALESCE(SUM(wh.duration_minutes),0) AS total_minutes,
               MAX(wh.started_at)         AS last_activity,
               r.last_seen, r.online
        FROM rooms r
        LEFT JOIN watch_history wh
               ON wh.room_id = r.id
              AND wh.started_at >= datetime('now', ?)
        GROUP BY r.id
        ORDER BY total_minutes DESC
    """, (f'-{days} days',)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/reports/channels', methods=['GET'])
@admin_required
def report_channels():
    days = _safe_int(request.args.get('days'), 30)
    conn = get_db()
    rows = conn.execute("""
        SELECT c.id, c.name, c.logo, mg.name AS group_name,
               COUNT(wh.id)               AS sessions,
               COALESCE(SUM(wh.duration_minutes),0) AS total_minutes,
               COUNT(DISTINCT wh.room_id) AS unique_rooms
        FROM channels c
        LEFT JOIN media_groups mg ON mg.id = c.media_group_id
        LEFT JOIN watch_history wh
               ON wh.channel_id = c.id
              AND wh.started_at >= datetime('now', ?)
        WHERE c.active = 1
        GROUP BY c.id
        ORDER BY total_minutes DESC
    """, (f'-{days} days',)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/reports/vod', methods=['GET'])
@admin_required
def report_vod():
    days = _safe_int(request.args.get('days'), 30)
    conn = get_db()
    rows = conn.execute("""
        SELECT m.id, m.title, m.genre, m.year, m.rating, m.price,
               COUNT(wh.id)               AS sessions,
               COALESCE(SUM(wh.duration_minutes),0) AS total_minutes,
               COUNT(DISTINCT wh.room_id) AS unique_rooms
        FROM vod_movies m
        LEFT JOIN watch_history wh
               ON wh.movie_id = m.id
              AND wh.started_at >= datetime('now', ?)
        WHERE m.active = 1
        GROUP BY m.id
        ORDER BY sessions DESC
    """, (f'-{days} days',)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/reports/radio', methods=['GET'])
@admin_required
def report_radio():
    days = _safe_int(request.args.get('days'), 30)
    conn = get_db()
    # radio uses channel_id field with negative IDs as convention OR a separate table
    # For now return stations ordered by name with zero stats (extend when radio history added)
    rows = conn.execute("""
        SELECT rs.id, rs.name, rs.country, rs.genre,
               0 AS sessions, 0 AS total_minutes
        FROM radio_stations rs WHERE rs.active=1
        ORDER BY rs.name
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/reports/pages', methods=['GET'])
@admin_required
def report_pages():
    conn = get_db()
    rows = conn.execute("""
        SELECT cp.id, cp.name, cp.group_name, cp.template,
               COUNT(ci.id) AS item_count
        FROM content_pages cp
        LEFT JOIN content_items ci ON ci.page_id = cp.id AND ci.active=1
        WHERE cp.active=1
        GROUP BY cp.id
        ORDER BY cp.group_name, cp.name
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/reports/summary', methods=['GET'])
@admin_required
def report_summary():
    """Combined summary for the reports dashboard."""
    days = _safe_int(request.args.get('days'), 30)
    conn = get_db()
    since = f'-{days} days'

    top_channels = conn.execute("""
        SELECT c.name, COUNT(wh.id) AS sessions,
               COALESCE(SUM(wh.duration_minutes),0) AS total_minutes,
               COUNT(DISTINCT wh.room_id) AS unique_rooms
        FROM watch_history wh
        JOIN channels c ON c.id = wh.channel_id
        WHERE wh.channel_id IS NOT NULL
          AND wh.started_at >= datetime('now', ?)
        GROUP BY c.id ORDER BY total_minutes DESC LIMIT 10
    """, (since,)).fetchall()

    top_rooms = conn.execute("""
        SELECT r.room_number, COUNT(wh.id) AS sessions,
               COALESCE(SUM(wh.duration_minutes),0) AS total_minutes
        FROM watch_history wh
        JOIN rooms r ON r.id = wh.room_id
        WHERE wh.started_at >= datetime('now', ?)
        GROUP BY r.id ORDER BY total_minutes DESC LIMIT 10
    """, (since,)).fetchall()

    top_vod = conn.execute("""
        SELECT m.title, COUNT(wh.id) AS sessions,
               COALESCE(SUM(wh.duration_minutes),0) AS total_minutes
        FROM watch_history wh
        JOIN vod_movies m ON m.id = wh.movie_id
        WHERE wh.movie_id IS NOT NULL
          AND wh.started_at >= datetime('now', ?)
        GROUP BY m.id ORDER BY sessions DESC LIMIT 10
    """, (since,)).fetchall()

    hourly = conn.execute("""
        SELECT strftime('%H', started_at) AS hour,
               COUNT(*) AS sessions,
               COALESCE(SUM(duration_minutes),0) AS total_minutes
        FROM watch_history
        WHERE started_at >= datetime('now', ?)
        GROUP BY hour ORDER BY hour
    """, (since,)).fetchall()

    daily = conn.execute("""
        SELECT strftime('%Y-%m-%d', started_at) AS day,
               COUNT(*) AS sessions,
               COALESCE(SUM(duration_minutes),0) AS total_minutes
        FROM watch_history
        WHERE started_at >= datetime('now', ?)
        GROUP BY day ORDER BY day
    """, (since,)).fetchall()

    online_count = conn.execute("""
        SELECT COUNT(*) FROM rooms
        WHERE last_seen IS NOT NULL
          AND (strftime('%s','now') - strftime('%s', last_seen)) <= ?
    """, (10*60,)).fetchone()[0]

    by_device = conn.execute("""
        SELECT COALESCE(device_type, 'browser') AS device_type,
               COUNT(*)                         AS sessions,
               COALESCE(SUM(duration_minutes), 0) AS total_minutes
        FROM watch_history
        WHERE started_at >= datetime('now', ?)
        GROUP BY device_type
        ORDER BY sessions DESC
    """, (since,)).fetchall()

    conn.close()
    return jsonify({
        'top_channels': [dict(r) for r in top_channels],
        'top_rooms':    [dict(r) for r in top_rooms],
        'top_vod':      [dict(r) for r in top_vod],
        'hourly':       [dict(r) for r in hourly],
        'daily':        [dict(r) for r in daily],
        'by_device':    [dict(r) for r in by_device],
        'online_rooms': online_count,
        'days':         days
    })


@app.route('/api/watch-event', methods=['POST'])
def record_watch_event():
    """
    Called by TV/browser clients to log a completed watch session.
    Body (JSON): { room_id, channel_id?, movie_id?, duration_minutes }
    device_type is auto-detected from the User-Agent header.
    """
    d = request.json or {}
    room_id          = d.get('room_id')
    channel_id       = d.get('channel_id')
    movie_id         = d.get('movie_id')
    duration_minutes = _safe_int(d.get('duration_minutes'), 0)

    if not room_id or (not channel_id and not movie_id):
        return jsonify({'error': 'room_id and one of channel_id / movie_id required'}), 400

    ua          = request.headers.get('User-Agent', '')[:200]
    device_type = _detect_device_type(ua)

    conn = get_db()
    conn.execute(
        """INSERT INTO watch_history (room_id, channel_id, movie_id, duration_minutes, device_type)
           VALUES (?, ?, ?, ?, ?)""",
        (room_id, channel_id, movie_id, duration_minutes, device_type)
    )
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'device_type': device_type})


@app.route('/api/reports/devices', methods=['GET'])
@admin_required
def report_devices():
    """Sessions and watch-minutes grouped by device_type over the requested window."""
    days = _safe_int(request.args.get('days'), 30)
    conn = get_db()
    rows = conn.execute("""
        SELECT COALESCE(device_type, 'browser') AS device_type,
               COUNT(*)                         AS sessions,
               COALESCE(SUM(duration_minutes), 0) AS total_minutes
        FROM watch_history
        WHERE started_at >= datetime('now', ?)
        GROUP BY device_type
        ORDER BY sessions DESC
    """, (f'-{days} days',)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ─── Users ────────────────────────────────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    conn = get_db()
    users = [dict(r) for r in conn.execute("SELECT id, username, role, created_at FROM users").fetchall()]
    conn.close()
    return jsonify(users)

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    d = request.json
    pw = hashlib.sha256(d['password'].encode()).hexdigest()
    conn = get_db()
    try:
        cur = conn.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)",
            (d['username'], pw, d.get('role','viewer')))
        conn.commit()
        u = dict(conn.execute("SELECT id, username, role, created_at FROM users WHERE id=?", (cur.lastrowid,)).fetchone())
        conn.close()
        return jsonify(u), 201
    except:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 409

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@admin_required
def delete_user(uid):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))

    conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ─── Statistics ───────────────────────────────────────────────────────────────

@app.route('/api/stats/overview', methods=['GET'])
@admin_required
def stats_overview():
    conn = get_db()
    total_rooms = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    online_rooms = conn.execute(
        """SELECT COUNT(*) FROM rooms
           WHERE last_seen IS NOT NULL
           AND (strftime('%s','now') - strftime('%s', last_seen)) <= ?""",
        (ONLINE_MINUTES * 60,)
    ).fetchone()[0]
    total_channels = conn.execute("SELECT COUNT(*) FROM channels WHERE active=1").fetchone()[0]
    total_movies = conn.execute("SELECT COUNT(*) FROM vod_movies WHERE active=1").fetchone()[0]
    total_watch_hours = conn.execute("SELECT COALESCE(SUM(duration_minutes)/60,0) FROM watch_history").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(amount),0) FROM vod_purchases").fetchone()[0]

    # Top channels
    top_channels = conn.execute("""
        SELECT c.name, COUNT(wh.id) as views, SUM(wh.duration_minutes) as total_minutes
        FROM watch_history wh
        JOIN channels c ON c.id=wh.channel_id
        WHERE wh.channel_id IS NOT NULL
        GROUP BY c.id ORDER BY views DESC LIMIT 5
    """).fetchall()

    # Daily watch trend (last 7 days fake)
    daily = []
    for i in range(7, 0, -1):
        day = (datetime.now() - timedelta(days=i)).strftime('%a')
        daily.append({'day': day, 'hours': round(random.uniform(40, 120), 1)})

    conn.close()
    return jsonify({
        'total_rooms': total_rooms,
        'online_rooms': online_rooms,
        'total_channels': total_channels,
        'total_movies': total_movies,
        'total_watch_hours': round(total_watch_hours, 1),
        'total_revenue': round(total_revenue, 2),
        'top_channels': [dict(r) for r in top_channels],
        'daily_trend': daily
    })

@app.route('/api/stats/channels', methods=['GET'])
@admin_required
def stats_channels():
    conn = get_db()
    rows = conn.execute("""
        SELECT c.name, COUNT(wh.id) as views, SUM(wh.duration_minutes) as total_minutes
        FROM watch_history wh
        JOIN channels c ON c.id=wh.channel_id
        WHERE wh.channel_id IS NOT NULL
        GROUP BY c.id ORDER BY views DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/stats/rooms', methods=['GET'])
@admin_required
def stats_rooms():
    conn = get_db()
    rows = conn.execute("""
        SELECT r.room_number, COUNT(wh.id) as sessions, SUM(wh.duration_minutes) as total_minutes
        FROM watch_history wh
        JOIN rooms r ON r.id=wh.room_id
        GROUP BY r.id ORDER BY total_minutes DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ─── Weather (mock) ───────────────────────────────────────────────────────────

@app.route('/api/weather', methods=['GET'])
def get_weather():
    city = request.args.get('city', 'Al Ain')
    conditions = ['Sunny', 'Partly Cloudy', 'Cloudy', 'Light Rain', 'Clear']
    icons = ['☀️', '⛅', '☁️', '🌧️', '🌙']
    idx = random.randint(0, 4)
    return jsonify({
        'city': city,
        'temperature': random.randint(22, 38),
        'feels_like': random.randint(20, 40),
        'humidity': random.randint(30, 80),
        'wind_speed': random.randint(5, 30),
        'uv_index': random.randint(1, 11),
        'dew_point': random.randint(10, 20),
        'condition': conditions[idx],
        'icon': icons[idx],
        'forecast': [
            {'day': (datetime.now() + timedelta(days=i)).strftime('%A'),
             'high': random.randint(28, 40), 'low': random.randint(18, 26),
             'condition': random.choice(conditions), 'icon': random.choice(icons)}
            for i in range(1, 5)
        ],
        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M')
    })



# ─── Serve Frontends ────────────────────────────────────────────


# ─── Bulk Operations ──────────────────────────────────────────────────────────

@app.route('/api/channels/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_channels():
    ids = request.json.get('ids', [])
    if not ids: return jsonify({'error': 'No ids provided'}), 400
    conn = get_db()
    conn.execute(f"DELETE FROM channels WHERE id IN ({','.join('?'*len(ids))})", ids)
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'deleted': len(ids)})

@app.route('/api/channels/bulk-import-csv', methods=['POST'])
@admin_required
def bulk_import_channels_csv():
    """Import channels from CSV. Columns: name,stream_url,channel_type,group_name,logo"""
    rows = request.json.get('rows', [])
    if not rows: return jsonify({'error': 'No rows'}), 400
    conn = get_db()
    imported = 0; errors = []
    for i, row in enumerate(rows):
        try:
            name = str(row.get('name','')).strip()
            url  = str(row.get('stream_url','')).strip()
            if not name or not url: continue
            ctype = row.get('channel_type','stream_udp')
            if ctype not in ('stream_udp','m3u','analog_tuner'): ctype = 'stream_udp'
            gname = str(row.get('group_name','All Channels')).strip() or 'All Channels'
            mg = conn.execute("SELECT id FROM media_groups WHERE LOWER(name)=LOWER(?)", (gname,)).fetchone()
            if not mg:
                mc = conn.execute("INSERT INTO media_groups (name, active) VALUES (?,1)", (gname,))
                mg_id = mc.lastrowid
            else:
                mg_id = mg['id']
            conn.execute(
                "INSERT INTO channels (name,stream_url,logo,media_group_id,active,channel_type,group_title) VALUES (?,?,?,?,1,?,?)",
                (name, url, row.get('logo',''), mg_id, ctype, gname))
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {e}")
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'imported': imported, 'errors': errors})

@app.route('/api/media-groups/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_groups():
    ids = request.json.get('ids', [])
    if not ids: return jsonify({'error': 'No ids'}), 400
    conn = get_db()
    conn.execute(f"UPDATE channels SET media_group_id=1 WHERE media_group_id IN ({','.join('?'*len(ids))})", ids)
    conn.execute(f"DELETE FROM media_groups WHERE id IN ({','.join('?'*len(ids))})", ids)
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'deleted': len(ids)})

@app.route('/api/media-groups/bulk-add', methods=['POST'])
@admin_required
def bulk_add_groups():
    names = request.json.get('names', [])
    conn = get_db()
    added = 0
    for name in names:
        name = str(name).strip()
        if not name: continue
        exists = conn.execute("SELECT id FROM media_groups WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
        if not exists:
            conn.execute("INSERT INTO media_groups (name, active) VALUES (?,1)", (name,))
            added += 1
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'added': added})

@app.route('/api/vod/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_vod():
    ids = request.json.get('ids', [])
    if not ids: return jsonify({'error': 'No ids'}), 400
    conn = get_db()
    conn.execute(f"DELETE FROM vod_movies WHERE id IN ({','.join('?'*len(ids))})", ids)
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'deleted': len(ids)})

@app.route('/api/vod/bulk-add', methods=['POST'])
@admin_required
def bulk_add_vod():
    rows = request.json.get('rows', [])
    conn = get_db()
    added = 0; errors = []
    for i, row in enumerate(rows):
        try:
            title = str(row.get('title','')).strip()
            if not title: continue
            conn.execute(
                "INSERT INTO vod_movies (title,description,genre,year,language,runtime,rating,price,stream_url,active) VALUES (?,?,?,?,?,?,?,?,?,1)",
                (title, row.get('description',''), row.get('genre',''), int(row.get('year',0)) or None,
                 row.get('language','English'), int(row.get('runtime',0)), float(row.get('rating',0)),
                 float(row.get('price',0)), row.get('stream_url','')))
            added += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {e}")
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'added': added, 'errors': errors})

@app.route('/api/vod/packages/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_packages():
    ids = request.json.get('ids', [])
    if not ids: return jsonify({'error': 'No ids'}), 400
    conn = get_db()
    conn.execute(f"DELETE FROM vod_packages WHERE id IN ({','.join('?'*len(ids))})", ids)
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'deleted': len(ids)})

@app.route('/api/vod/packages/bulk-add', methods=['POST'])
@admin_required
def bulk_add_packages():
    rows = request.json.get('rows', [])
    conn = get_db()
    added = 0
    for row in rows:
        name = str(row.get('name','')).strip()
        if not name: continue
        conn.execute("INSERT INTO vod_packages (name,description,price,duration_hours,active) VALUES (?,?,?,?,1)",
            (name, row.get('description',''), float(row.get('price',0)), int(row.get('duration_hours',24))))
        added += 1
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'added': added})

@app.route('/api/radio/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_radio():
    ids = request.json.get('ids', [])
    if not ids: return jsonify({'error': 'No ids'}), 400
    conn = get_db()
    conn.execute(f"DELETE FROM radio_stations WHERE id IN ({','.join('?'*len(ids))})", ids)
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'deleted': len(ids)})

@app.route('/api/radio/bulk-add', methods=['POST'])
@admin_required
def bulk_add_radio():
    rows = request.json.get('rows', [])
    conn = get_db()
    added = 0; errors = []
    for i, row in enumerate(rows):
        try:
            name = str(row.get('name','')).strip()
            url  = str(row.get('stream_url','')).strip()
            if not name or not url: continue
            conn.execute("INSERT INTO radio_stations (name,country,genre,stream_url,logo,active) VALUES (?,?,?,?,?,1)",
                (name, row.get('country',''), row.get('genre',''), url, row.get('logo','')))
            added += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {e}")
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'added': added, 'errors': errors})

@app.route('/api/rooms/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_rooms():
    ids = request.json.get('ids', [])
    if not ids: return jsonify({'error': 'No ids'}), 400
    conn = get_db()
    conn.execute(f"DELETE FROM rooms WHERE id IN ({','.join('?'*len(ids))})", ids)
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'deleted': len(ids)})

@app.route('/api/rooms/bulk-add', methods=['POST'])
@admin_required
def bulk_add_rooms():
    """Add rooms from a list or a range like 101-120."""
    data   = request.json or {}
    rooms  = data.get('rooms', [])   # [{room_number, tv_name}, ...]
    prefix = data.get('prefix', '')  # e.g. "TV-"
    added  = 0; errors = []
    conn   = get_db()
    for room in rooms:
        num  = str(room.get('room_number','')).strip()
        name = str(room.get('tv_name', prefix + num)).strip()
        if not num: continue
        try:
            token = str(__import__('uuid').uuid4())
            conn.execute("INSERT INTO rooms (room_number, tv_name, room_token) VALUES (?,?,?)", (num, name, token))
            added += 1
        except Exception as e:
            errors.append(f"Room {num}: duplicate or error")
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'added': added, 'errors': errors})


# ═══════════════════════════════════════════════════════════════════════════════
# V6 — RSS FEEDS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/rss', methods=['GET'])
@admin_required
def get_rss_feeds():
    conn = get_db()
    feeds = [dict(r) for r in conn.execute("SELECT * FROM rss_feeds ORDER BY type, id").fetchall()]
    conn.close()
    return jsonify(feeds)

@app.route('/api/rss/public', methods=['GET'])
def get_rss_feeds_public():
    """TV/client endpoint — returns active feeds with cached items."""
    if _USE_MYSQL:
        @cache.cached(timeout=TTL_RSS, key_prefix='nv:rss_public')
        def _cached():
            return _fetch_rss_feeds()
        return jsonify(_cached())
    return jsonify(_fetch_rss_feeds())

def _fetch_rss_feeds():
    """Fetch active RSS feeds from DB and pull items from each URL."""
    conn = get_db()
    feeds = [dict(r) for r in conn.execute(
        "SELECT * FROM rss_feeds WHERE active=1 ORDER BY type, id").fetchall()]
    conn.close()
    import xml.etree.ElementTree as ET
    result = []
    for feed in feeds:
        items = []
        try:
            req2 = urllib.request.Request(feed['url'], headers={'User-Agent': 'NexVision/6.0'})
            with urllib.request.urlopen(req2, timeout=6) as resp:
                raw = resp.read()
            root = ET.fromstring(raw)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            # Try RSS 2.0 first
            for item in root.findall('.//item')[:20]:
                title = item.findtext('title', '').strip()
                desc  = item.findtext('description', '').strip()
                link  = item.findtext('link', '').strip()
                pub   = item.findtext('pubDate', '').strip()
                if title:
                    items.append({'title': title, 'description': desc[:200], 'link': link, 'pub': pub})
            # Try Atom if no items
            if not items:
                for entry in root.findall('atom:entry', ns)[:20]:
                    title = (entry.findtext('atom:title', '', ns) or '').strip()
                    summary = (entry.findtext('atom:summary', '', ns) or '').strip()
                    link_el = entry.find('atom:link', ns)
                    link = link_el.get('href', '') if link_el is not None else ''
                    if title:
                        items.append({'title': title, 'description': summary[:200], 'link': link, 'pub': ''})
        except Exception as e:
            items = [{'title': f'Feed unavailable: {e}', 'description': '', 'link': '', 'pub': ''}]
        result.append({**feed, 'items': items})
    return result

@app.route('/api/rss', methods=['POST'])
@admin_required
def create_rss_feed():
    d = request.json
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO rss_feeds (title, url, type, active, refresh_minutes, text_color, bg_color, bg_opacity) VALUES (?,?,?,?,?,?,?,?)",
        (d['title'], d['url'], d.get('type','normal'), d.get('active',1), d.get('refresh_minutes',15),
         d.get('text_color','#ffffff'), d.get('bg_color','#09090f'), d.get('bg_opacity',92)))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM rss_feeds WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    if _USE_MYSQL: invalidate_rss()
    return jsonify(row), 201

@app.route('/api/rss/<int:fid>', methods=['PUT'])
@admin_required
def update_rss_feed(fid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE rss_feeds SET title=?,url=?,type=?,active=?,refresh_minutes=?,text_color=?,bg_color=?,bg_opacity=? WHERE id=?",
        (d['title'], d['url'], d.get('type','normal'), d.get('active',1), d.get('refresh_minutes',15),
         d.get('text_color','#ffffff'), d.get('bg_color','#09090f'), d.get('bg_opacity',92), fid))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM rss_feeds WHERE id=?", (fid,)).fetchone())
    conn.close()
    if _USE_MYSQL: invalidate_rss()
    return jsonify(row)

@app.route('/api/rss/<int:fid>', methods=['DELETE'])
@admin_required
def delete_rss_feed(fid):
    conn = get_db()
    conn.execute("DELETE FROM rss_feeds WHERE id=?", (fid,))
    conn.commit(); conn.close()
    if _USE_MYSQL: invalidate_rss()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════════════════════
# V6 — MESSAGES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/messages', methods=['GET'])
@admin_required
def get_messages():
    conn = get_db()
    rows = conn.execute("""
        SELECT m.*, u.username as author
        FROM messages m LEFT JOIN users u ON u.id=m.created_by
        ORDER BY m.sent_at DESC LIMIT 200
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/messages/active', methods=['GET'])
def get_active_messages():
    """TV/client endpoint — returns messages for this room (uses X-Room-Token)."""
    token = request.headers.get('X-Room-Token', '').strip()
    conn  = get_db()
    room  = None
    if token:
        room = conn.execute("SELECT * FROM rooms WHERE room_token=?", (token,)).fetchone()

    # Build query: get all active non-expired messages targeting this room or all
    now_q = "datetime('now')"
    rows = conn.execute(f"""
        SELECT * FROM messages
        WHERE active=1
          AND (expires_at IS NULL OR expires_at > {now_q})
        ORDER BY type DESC, sent_at DESC
    """).fetchall()

    result = []
    for r in rows:
        msg = dict(r)
        target = msg.get('target', 'all')
        if target == 'all':
            result.append(msg)
        elif target == 'room' and room:
            ids = [x.strip() for x in (msg.get('room_ids') or '').split(',') if x.strip()]
            if str(room['id']) in ids or room['room_number'] in ids:
                result.append(msg)

    # ── Inject today's birthdays as birthday-type messages ────────────────────
    import datetime as _dt
    today = _dt.date.today().strftime('%m-%d')
    bdays = conn.execute("""
        SELECT * FROM birthdays
        WHERE active=1 AND strftime('%m-%d', birth_date) = ?
    """, (today,)).fetchall()

    for b in bdays:
        b = dict(b)
        # Filter to correct room: if birthday has a room_id, only send to that room
        if b.get('room_id') and room:
            if b['room_id'] != room['id']:
                continue
        elif b.get('room_id') and not room:
            continue  # room-specific birthday, but client has no token — skip
        # Use offset ID so it won't collide with real message IDs
        bday_msg = {
            'id':       90000 + b['id'],
            'type':     'birthday',
            'title':    f"🎂 Happy Birthday, {b['guest_name']}!",
            'body':     b.get('message') or 'Wishing you a wonderful birthday! May your day be filled with joy.',
            'target':   'room' if b.get('room_id') else 'all',
            'room_ids': str(b['room_id']) if b.get('room_id') else '',
            'active':   1,
            'sent_at':  None,
            'expires_at': None,
        }
        result.append(bday_msg)

    conn.close()
    return jsonify(result)

@app.route('/api/messages', methods=['POST'])
@admin_required
def create_message():
    d = request.json
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO messages (title, body, type, target, room_ids, expires_at, active, created_by)
           VALUES (?,?,?,?,?,?,?,?)""",
        (d['title'], d['body'], d.get('type','normal'), d.get('target','all'),
         d.get('room_ids',''), d.get('expires_at') or None, 1, me_id()))
    _bump_stamp(conn)
    conn.commit()
    row = dict(conn.execute("SELECT * FROM messages WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(row), 201

@app.route('/api/messages/<int:mid>', methods=['PUT'])
@admin_required
def update_message(mid):
    d = request.json
    conn = get_db()
    conn.execute("""UPDATE messages SET title=?,body=?,type=?,target=?,room_ids=?,expires_at=?,active=?
                    WHERE id=?""",
        (d['title'], d['body'], d.get('type','normal'), d.get('target','all'),
         d.get('room_ids',''), d.get('expires_at') or None, d.get('active',1), mid))
    _bump_stamp(conn)
    conn.commit()
    row = dict(conn.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone())
    conn.close()
    return jsonify(row)

@app.route('/api/messages/<int:mid>', methods=['DELETE'])
@admin_required
def delete_message(mid):
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE id=?", (mid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/messages/<int:mid>/dismiss', methods=['POST'])
def dismiss_message(mid):
    """Mark message inactive (admin or room dismiss)."""
    conn = get_db()
    conn.execute("UPDATE messages SET active=0 WHERE id=?", (mid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════════════════════
# V6 — BIRTHDAYS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/birthdays', methods=['GET'])
@admin_required
def get_birthdays():
    conn = get_db()
    rows = conn.execute("""
        SELECT b.*, r.room_number as actual_room
        FROM birthdays b LEFT JOIN rooms r ON r.id=b.room_id
        ORDER BY b.birth_date
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/birthdays/today', methods=['GET'])
def get_birthdays_today():
    """TV/client endpoint — returns today's birthdays for display."""
    today = __import__('datetime').date.today()
    token = request.headers.get('X-Room-Token','').strip()
    conn  = get_db()
    # Match by month-day
    rows = conn.execute("""
        SELECT b.*, r.room_number as actual_room
        FROM birthdays b LEFT JOIN rooms r ON r.id=b.room_id
        WHERE b.active=1
          AND strftime('%m-%d', b.birth_date) = ?
    """, (today.strftime('%m-%d'),)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/birthdays', methods=['POST'])
@admin_required
def create_birthday():
    d = request.json
    conn = get_db()
    # Resolve room_id from room_number if provided
    rid = d.get('room_id')
    if not rid and d.get('room_number'):
        rm = conn.execute("SELECT id FROM rooms WHERE room_number=?", (d['room_number'],)).fetchone()
        if rm: rid = rm['id']
    cur = conn.execute(
        "INSERT INTO birthdays (guest_name, room_id, room_number, birth_date, message, active) VALUES (?,?,?,?,?,1)",
        (d['guest_name'], rid, d.get('room_number',''), d['birth_date'], d.get('message','')))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM birthdays WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(row), 201

@app.route('/api/birthdays/<int:bid>', methods=['PUT'])
@admin_required
def update_birthday(bid):
    d = request.json
    conn = get_db()
    rid = d.get('room_id')
    if not rid and d.get('room_number'):
        rm = conn.execute("SELECT id FROM rooms WHERE room_number=?", (d['room_number'],)).fetchone()
        if rm: rid = rm['id']
    conn.execute("UPDATE birthdays SET guest_name=?,room_id=?,room_number=?,birth_date=?,message=?,active=? WHERE id=?",
        (d['guest_name'], rid, d.get('room_number',''), d['birth_date'], d.get('message',''), d.get('active',1), bid))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM birthdays WHERE id=?", (bid,)).fetchone())
    conn.close()
    return jsonify(row)

@app.route('/api/birthdays/<int:bid>', methods=['DELETE'])
@admin_required
def delete_birthday(bid):
    conn = get_db()
    conn.execute("DELETE FROM birthdays WHERE id=?", (bid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════════════════════
# V6 — VIP CHANNELS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/vip/channels', methods=['GET'])
@admin_required
def get_vip_channels():
    """Returns all VIP channels with their room access lists."""
    conn = get_db()
    channels = conn.execute("""
        SELECT c.id, c.name, c.logo, c.stream_url, c.channel_type, c.active
        FROM channels c WHERE c.is_vip=1 ORDER BY c.name
    """).fetchall()
    result = []
    for ch in channels:
        ch_dict = dict(ch)
        rooms = conn.execute("""
            SELECT r.id, r.room_number, r.tv_name
            FROM vip_channel_access va JOIN rooms r ON r.id=va.room_id
            WHERE va.channel_id=?
        """, (ch['id'],)).fetchall()
        ch_dict['rooms'] = [dict(r) for r in rooms]
        result.append(ch_dict)
    conn.close()
    return jsonify(result)

@app.route('/api/vip/access', methods=['POST'])
@admin_required
def grant_vip_access():
    """Grant room(s) access to a VIP channel."""
    d = request.json
    channel_id = d.get('channel_id')
    room_ids   = d.get('room_ids', [])
    if not channel_id or not room_ids:
        return jsonify({'error': 'channel_id and room_ids required'}), 400
    conn = get_db()
    conn.execute("UPDATE channels SET is_vip=1 WHERE id=?", (channel_id,))
    added = 0
    for rid in room_ids:
        try:
            conn.execute("INSERT OR IGNORE INTO vip_channel_access (channel_id, room_id) VALUES (?,?)", (channel_id, rid))
            added += 1
        except: pass
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'added': added})

@app.route('/api/vip/access', methods=['DELETE'])
@admin_required
def revoke_vip_access():
    """Revoke room access from a VIP channel."""
    d = request.json
    channel_id = d.get('channel_id')
    room_id    = d.get('room_id')  # single or None = revoke all
    conn = get_db()
    if room_id:
        conn.execute("DELETE FROM vip_channel_access WHERE channel_id=? AND room_id=?", (channel_id, room_id))
    else:
        conn.execute("DELETE FROM vip_channel_access WHERE channel_id=?", (channel_id,))
        conn.execute("UPDATE channels SET is_vip=0 WHERE id=?", (channel_id,))
    # If no rooms left, un-vip the channel
    remaining = conn.execute("SELECT COUNT(*) FROM vip_channel_access WHERE channel_id=?", (channel_id,)).fetchone()[0]
    if remaining == 0:
        conn.execute("UPDATE channels SET is_vip=0 WHERE id=?", (channel_id,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/vip/my-channels', methods=['GET'])
def get_my_vip_channels():
    """TV/client: returns VIP channels this room has access to."""
    token = request.headers.get('X-Room-Token', '').strip()
    conn  = get_db()
    if not token:
        conn.close()
        return jsonify([])
    room = conn.execute("SELECT * FROM rooms WHERE room_token=?", (token,)).fetchone()
    if not room:
        conn.close()
        return jsonify([])
    channels = conn.execute("""
        SELECT c.*, mg.name as group_name
        FROM vip_channel_access va
        JOIN channels c ON c.id=va.channel_id
        LEFT JOIN media_groups mg ON mg.id=c.media_group_id
        WHERE va.room_id=? AND c.active=1
        ORDER BY c.name
    """, (room['id'],)).fetchall()
    conn.close()
    return jsonify([dict(c) for c in channels])


# ── VIP VOD endpoints ──────────────────────────────────────────────────────────

@app.route('/api/vip/vod', methods=['GET'])
@admin_required
def get_vip_vod():
    """Returns all VIP VOD videos with their room access lists."""
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT video_id FROM vip_vod_access ORDER BY video_id").fetchall()
    result = []
    try:
        vod_conn = vod_get_db()
        for row in rows:
            vid = row['video_id']
            video = vod_conn.execute(
                "SELECT id, title, thumbnail FROM videos WHERE id=?", (vid,)
            ).fetchone()
            if not video:
                continue
            rooms = conn.execute("""
                SELECT r.id, r.room_number, r.tv_name
                FROM vip_vod_access va JOIN rooms r ON r.id=va.room_id
                WHERE va.video_id=?
            """, (vid,)).fetchall()
            result.append({
                'video_id': vid,
                'title': video['title'],
                'thumbnail_url': video['thumbnail'] or '',
                'rooms': [dict(r) for r in rooms]
            })
        vod_conn.close()
    except Exception:
        pass
    conn.close()
    return jsonify(result)


@app.route('/api/vip/vod-access', methods=['POST'])
@admin_required
def grant_vip_vod_access():
    """Grant room(s) access to VIP VOD video(s)."""
    d = request.json or {}
    video_ids = d.get('video_ids', [])
    room_ids  = d.get('room_ids', [])
    if not video_ids or not room_ids:
        return jsonify({'error': 'video_ids and room_ids required'}), 400
    conn = get_db()
    added = 0
    for vid in video_ids:
        for rid in room_ids:
            try:
                conn.execute("INSERT OR IGNORE INTO vip_vod_access (video_id, room_id) VALUES (?,?)", (vid, rid))
                added += 1
            except: pass
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'added': added})


@app.route('/api/vip/vod-access', methods=['DELETE'])
@admin_required
def revoke_vip_vod_access():
    """Revoke room access from a VIP VOD video."""
    d = request.json or {}
    video_id = d.get('video_id')
    room_id  = d.get('room_id')  # None = revoke all rooms for this video
    conn = get_db()
    if room_id:
        conn.execute("DELETE FROM vip_vod_access WHERE video_id=? AND room_id=?", (video_id, room_id))
    else:
        conn.execute("DELETE FROM vip_vod_access WHERE video_id=?", (video_id,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@app.route('/api/vip/my-vod', methods=['GET'])
def get_my_vip_vod():
    """TV client: returns video_ids this room has VIP VOD access to."""
    token = request.headers.get('X-Room-Token', '').strip()
    conn  = get_db()
    if not token:
        conn.close(); return jsonify([])
    room = conn.execute("SELECT id FROM rooms WHERE room_token=?", (token,)).fetchone()
    if not room:
        conn.close(); return jsonify([])
    rows = conn.execute("SELECT video_id FROM vip_vod_access WHERE room_id=?", (room['id'],)).fetchall()
    conn.close()
    return jsonify([r['video_id'] for r in rows])


# ── Content Packages ───────────────────────────────────────────────────────────

@app.route('/api/packages', methods=['GET'])
@admin_required
def list_packages():
    conn = get_db()
    pkgs = []
    for p in conn.execute("SELECT * FROM content_packages ORDER BY name").fetchall():
        p = dict(p)
        p['channel_ids'] = [r['channel_id'] for r in conn.execute(
            "SELECT channel_id FROM package_channels WHERE package_id=?", (p['id'],)).fetchall()]
        p['vod_ids'] = [r['vod_id'] for r in conn.execute(
            "SELECT vod_id FROM package_vod WHERE package_id=?", (p['id'],)).fetchall()]
        p['radio_ids'] = [r['radio_id'] for r in conn.execute(
            "SELECT radio_id FROM package_radio WHERE package_id=?", (p['id'],)).fetchall()]
        pkgs.append(p)
    conn.close()
    return jsonify(pkgs)

@app.route('/api/packages', methods=['POST'])
@admin_required
def create_package_content():
    d = request.json or {}
    name = d.get('name','').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    conn = get_db()
    cur = conn.execute("INSERT INTO content_packages (name, description, active) VALUES (?,?,?)",
        (name, d.get('description',''), d.get('active',1)))
    pid = cur.lastrowid
    _sync_package_content(conn, pid, d.get('channel_ids',[]), d.get('vod_ids',[]), d.get('radio_ids',[]))
    conn.commit()
    p = dict(conn.execute("SELECT * FROM content_packages WHERE id=?", (pid,)).fetchone())
    conn.close()
    return jsonify(p), 201

@app.route('/api/packages/<int:pid>', methods=['PUT'])
@admin_required
def update_package_content(pid):
    d = request.json or {}
    conn = get_db()
    conn.execute("UPDATE content_packages SET name=?, description=?, active=? WHERE id=?",
        (d.get('name',''), d.get('description',''), d.get('active',1), pid))
    _sync_package_content(conn, pid, d.get('channel_ids',[]), d.get('vod_ids',[]), d.get('radio_ids',[]))
    conn.commit()
    p = dict(conn.execute("SELECT * FROM content_packages WHERE id=?", (pid,)).fetchone())
    conn.close()
    return jsonify(p)

@app.route('/api/packages/<int:pid>', methods=['DELETE'])
@admin_required
def delete_package_content(pid):
    conn = get_db()
    conn.execute("DELETE FROM content_packages WHERE id=?", (pid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

def _sync_package_content(conn, pid, channel_ids, vod_ids, radio_ids=None):
    """Replace channel, vod and radio assignments for a package."""
    conn.execute("DELETE FROM package_channels WHERE package_id=?", (pid,))
    conn.execute("DELETE FROM package_vod WHERE package_id=?", (pid,))
    conn.execute("DELETE FROM package_radio WHERE package_id=?", (pid,))
    for cid in (channel_ids or []):
        try: conn.execute("INSERT OR IGNORE INTO package_channels (package_id,channel_id) VALUES (?,?)", (pid, int(cid)))
        except: pass
    for vid in (vod_ids or []):
        try: conn.execute("INSERT OR IGNORE INTO package_vod (package_id,vod_id) VALUES (?,?)", (pid, int(vid)))
        except: pass
    for rid in (radio_ids or []):
        try: conn.execute("INSERT OR IGNORE INTO package_radio (package_id,radio_id) VALUES (?,?)", (pid, int(rid)))
        except: pass

# ── Room Package Assignment ─────────────────────────────────────────────────────

@app.route('/api/rooms/<int:rid>/packages', methods=['GET'])
@admin_required
def get_room_packages(rid):
    conn = get_db()
    rows = conn.execute(
        "SELECT cp.* FROM room_packages rp JOIN content_packages cp ON cp.id=rp.package_id WHERE rp.room_id=?", (rid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/rooms/<int:rid>/packages', methods=['POST'])
@admin_required
def set_room_packages(rid):
    pkg_ids = (request.json or {}).get('package_ids', [])
    conn = get_db()
    conn.execute("DELETE FROM room_packages WHERE room_id=?", (rid,))
    for pid in pkg_ids:
        try: conn.execute("INSERT OR IGNORE INTO room_packages (room_id,package_id) VALUES (?,?)", (rid, int(pid)))
        except: pass
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/rooms/packages-map', methods=['GET'])
@admin_required
def get_rooms_packages_map():
    """Returns {room_id: [package names...]} for all rooms — used by admin room list."""
    conn = get_db()
    rows = conn.execute("""
        SELECT rp.room_id, cp.name
        FROM room_packages rp JOIN content_packages cp ON cp.id=rp.package_id
    """).fetchall()
    conn.close()
    result = {}
    for r in rows:
        result.setdefault(str(r['room_id']), []).append(r['name'])
    return jsonify(result)

@app.route('/api/my-packages', methods=['GET'])
def get_my_packages():
    """TV client: returns package IDs assigned to this room."""
    token = request.headers.get('X-Room-Token', '').strip()
    conn  = get_db()
    if not token:
        conn.close(); return jsonify([])
    room = conn.execute("SELECT id FROM rooms WHERE room_token=?", (token,)).fetchone()
    if not room:
        conn.close(); return jsonify([])
    rows = conn.execute(
        "SELECT cp.id, cp.name FROM room_packages rp JOIN content_packages cp ON cp.id=rp.package_id WHERE rp.room_id=?",
        (room['id'],)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── Helper ─────────────────────────────────────────────────────────────────────
def me_id():
    """Get current user id from JWT."""
    try:
        import jwt as pyjwt
        token = request.headers.get('Authorization','').replace('Bearer ','')
        payload = pyjwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload.get('user_id', 1)
    except:
        return 1


# ═══════════════════════════════════════════════════════════════════════════════
# V7 — GUEST SERVICES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/services', methods=['GET'])
def get_services():
    conn = get_db()
    rows = conn.execute("SELECT * FROM guest_services WHERE active=1 ORDER BY sort_order, id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/services/all', methods=['GET'])
@admin_required
def get_all_services():
    conn = get_db()
    rows = conn.execute("SELECT * FROM guest_services ORDER BY sort_order, id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/services', methods=['POST'])
@admin_required
def create_service():
    d = request.json
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO guest_services (name, category, icon, phone, description, sort_order, active) VALUES (?,?,?,?,?,?,?)",
        (d['name'], d.get('category','General'), d.get('icon','📞'), d.get('phone',''),
         d.get('description',''), d.get('sort_order',0), d.get('active',1)))
    _bump_stamp(conn)
    conn.commit()
    row = dict(conn.execute("SELECT * FROM guest_services WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(row), 201

@app.route('/api/services/<int:sid>', methods=['PUT'])
@admin_required
def update_service(sid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE guest_services SET name=?,category=?,icon=?,phone=?,description=?,sort_order=?,active=? WHERE id=?",
        (d['name'], d.get('category','General'), d.get('icon','📞'), d.get('phone',''),
         d.get('description',''), d.get('sort_order',0), d.get('active',1), sid))
    _bump_stamp(conn)
    conn.commit()
    row = dict(conn.execute("SELECT * FROM guest_services WHERE id=?", (sid,)).fetchone())
    conn.close()
    return jsonify(row)

@app.route('/api/services/<int:sid>', methods=['DELETE'])
@admin_required
def delete_service(sid):
    conn = get_db()
    conn.execute("DELETE FROM guest_services WHERE id=?", (sid,))
    _bump_stamp(conn)
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/services/reorder', methods=['POST'])
@admin_required
def reorder_services():
    order = request.json.get('order', [])  # [{id, sort_order}]
    conn = get_db()
    for item in order:
        conn.execute("UPDATE guest_services SET sort_order=? WHERE id=?", (item['sort_order'], item['id']))
    _bump_stamp(conn)
    conn.commit(); conn.close()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════════════════════
# V7 — EPG
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/epg', methods=['GET'])
def get_epg():
    """Returns EPG for a channel or all channels for next N hours."""
    channel_id = request.args.get('channel_id')
    hours = _safe_int(request.args.get('hours'), 6)
    conn = get_db()
    if channel_id:
        rows = conn.execute("""
            SELECT e.*, c.name as channel_name
            FROM epg_entries e JOIN channels c ON c.id=e.channel_id
            WHERE e.channel_id=?
              AND REPLACE(e.end_time, 'T', ' ') >= datetime('now')
              AND REPLACE(e.start_time, 'T', ' ') <= datetime('now', ?)
            ORDER BY e.start_time
        """, (channel_id, f'+{hours} hours')).fetchall()
    else:
        rows = conn.execute("""
            SELECT e.*, c.name as channel_name
            FROM epg_entries e JOIN channels c ON c.id=e.channel_id
            WHERE REPLACE(e.end_time, 'T', ' ') >= datetime('now')
              AND REPLACE(e.start_time, 'T', ' ') <= datetime('now', ?)
            ORDER BY e.channel_id, e.start_time
        """, (f'+{hours} hours',)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/epg', methods=['POST'])
@admin_required
def create_epg():
    d = request.json
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO epg_entries (channel_id,title,description,start_time,end_time,category) VALUES (?,?,?,?,?,?)",
        (d['channel_id'],d['title'],d.get('description',''),d['start_time'],d['end_time'],d.get('category','')))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM epg_entries WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(row), 201

@app.route('/api/epg/bulk', methods=['POST'])
@admin_required
def bulk_create_epg():
    entries = request.json.get('entries', [])
    conn = get_db()
    added = 0
    for e in entries:
        try:
            conn.execute(
                "INSERT INTO epg_entries (channel_id,title,description,start_time,end_time,category) VALUES (?,?,?,?,?,?)",
                (e['channel_id'],e['title'],e.get('description',''),e['start_time'],e['end_time'],e.get('category','')))
            added += 1
        except: pass
    conn.commit(); conn.close()
    return jsonify({'ok': True, 'added': added})

@app.route('/api/epg/<int:eid>', methods=['PUT'])
@admin_required
def update_epg(eid):
    d = request.json
    conn = get_db()
    conn.execute("UPDATE epg_entries SET channel_id=?,title=?,description=?,start_time=?,end_time=?,category=? WHERE id=?",
        (d['channel_id'],d['title'],d.get('description',''),d['start_time'],d['end_time'],d.get('category',''),eid))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM epg_entries WHERE id=?", (eid,)).fetchone())
    conn.close()
    return jsonify(row)

@app.route('/api/epg/<int:eid>', methods=['DELETE'])
@admin_required
def delete_epg(eid):
    conn = get_db()
    conn.execute("DELETE FROM epg_entries WHERE id=?", (eid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/epg/clear-old', methods=['POST'])
@admin_required
def clear_old_epg():
    conn = get_db()
    conn.execute("DELETE FROM epg_entries WHERE end_time < datetime('now', '-1 day')")
    conn.commit(); conn.close()
    return jsonify({'ok': True})

@app.route('/api/epg/sync-now', methods=['POST'])
@admin_required
def sync_epg_now():
    """Fetch EPG from URL and import to database."""
    import xml.etree.ElementTree as ET
    url = request.json.get('url', '').strip()

    if not url:
        return jsonify({'error': 'URL required'}), 400

    try:
        # Fetch and parse XML before touching the DB
        req = urllib.request.Request(url, headers={'User-Agent': 'NexVision/6.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()

        root = ET.fromstring(raw)

        # Build channel display-name map from the XML <channel> elements
        xml_channel_names = {}
        for ch_elem in root.findall('.//channel'):
            ch_id = ch_elem.get('id', '').strip()
            display_name = ch_elem.findtext('display-name', '').strip()
            if ch_id and display_name:
                xml_channel_names[ch_id] = display_name

        # Load ALL DB channels into memory once (avoids one query per programme)
        conn = get_db()
        tvg_map  = {}  # tvg_id  → db channel id
        name_map = {}  # name    → db channel id
        id_map   = {}  # int id  → db channel id
        for row in conn.execute("SELECT id, tvg_id, name FROM channels").fetchall():
            if row['tvg_id']:
                tvg_map[row['tvg_id'].strip()] = row['id']
            if row['name']:
                name_map[row['name'].strip().lower()] = row['id']
            id_map[row['id']] = row['id']

        # Parse all programmes into memory, match channels in Python
        entries = []
        total_parsed = 0
        unmatched = 0

        for prog in root.findall('.//programme'):
            channel_id = prog.get('channel', '').strip()
            title      = prog.findtext('title', '').strip()
            start      = prog.get('start', '').strip()
            stop       = prog.get('stop', '').strip()
            desc       = prog.findtext('desc', '').strip()

            if not (channel_id and title and start and stop):
                continue

            total_parsed += 1

            try:
                ts = start.split()[0] if ' ' in start else start
                if 'T' in ts:
                    ts = ts.replace('T', '')[:14]
                start_dt = datetime.strptime(ts, '%Y%m%d%H%M%S')

                ts_stop = stop.split()[0] if ' ' in stop else stop
                if 'T' in ts_stop:
                    ts_stop = ts_stop.replace('T', '')[:14]
                stop_dt = datetime.strptime(ts_stop, '%Y%m%d%H%M%S')
            except:
                continue

            # Match: tvg_id → nexvision-N prefix → display name
            ch_id = tvg_map.get(channel_id)
            if not ch_id and 'nexvision-' in channel_id:
                try:
                    ch_id = id_map.get(int(channel_id.replace('nexvision-', '')))
                except ValueError:
                    pass
            if not ch_id:
                dn = xml_channel_names.get(channel_id, '').strip().lower()
                if dn:
                    ch_id = name_map.get(dn)

            if ch_id:
                entries.append((ch_id, title, desc, start_dt.isoformat(), stop_dt.isoformat(), ''))
            else:
                unmatched += 1

        # Write everything in one fast transaction
        conn.execute("DELETE FROM epg_entries WHERE end_time < datetime('now', '-1 day')")
        conn.executemany("""
            INSERT OR REPLACE INTO epg_entries
            (channel_id, title, description, start_time, end_time, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """, entries)
        conn.commit()
        conn.close()

        imported = len(entries)
        return jsonify({'imported': imported, 'total_parsed': total_parsed, 'unmatched': unmatched})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/epg/generate-guide', methods=['POST'])
@admin_required
def generate_epg_guide():
    """Generate guide.xml from database EPG entries."""
    import xml.etree.ElementTree as ET

    days = _safe_int(request.json.get('days'), 2)
    path = request.json.get('path', '/opt/nexvision/epg/public/guide.xml').strip()

    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT e.channel_id, c.name, e.title, e.description, e.start_time, e.end_time
            FROM epg_entries e
            JOIN channels c ON c.id = e.channel_id
            WHERE e.end_time > datetime('now', '-1 day')
            ORDER BY e.channel_id, e.start_time
        """).fetchall()
        conn.close()

        # Create XML structure
        tv = ET.Element('tv', {'generator-info-name': 'NexVision'})

        # Add channels
        channels = {}
        for row in rows:
            ch_id = row['channel_id']
            if ch_id not in channels:
                channels[ch_id] = row['name']
                ch = ET.SubElement(tv, 'channel', {'id': f'nexvision-{ch_id}'})
                ET.SubElement(ch, 'display-name').text = row['name']

        # Add programmes
        for row in rows:
            prog = ET.SubElement(tv, 'programme', {
                'channel': f'nexvision-{row["channel_id"]}',
                'start': row['start_time'].replace(' ', '').replace('-', '').replace(':', ''),
                'stop': row['end_time'].replace(' ', '').replace('-', '').replace(':', '')
            })
            ET.SubElement(prog, 'title').text = row['title']
            if row['description']:
                ET.SubElement(prog, 'desc').text = row['description']

        # Write to file (fallback to EPG public dir if requested path is not writable)
        tree = ET.ElementTree(tv)
        try:
            out_dir = os.path.dirname(path) or '.'
            os.makedirs(out_dir, exist_ok=True)
            tree.write(path, encoding='UTF-8', xml_declaration=True)
        except PermissionError:
            path = '/opt/nexvision/epg/public/guide.xml'
            os.makedirs('/opt/nexvision/epg/public', exist_ok=True)
            tree.write(path, encoding='UTF-8', xml_declaration=True)

        size = os.path.getsize(path)
        return jsonify({'path': path, 'size_bytes': size})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/epg/monitor', methods=['GET'])
def get_epg_monitor():
    """Get EPG sync monitor status."""
    conn = get_db()
    settings = {}
    for row in conn.execute("SELECT key, value FROM settings WHERE key LIKE 'epg_%'").fetchall():
        settings[row['key'].replace('epg_', '')] = row['value']
    conn.close()

    return jsonify({
        'auto_url': settings.get('auto_url', 'http://localhost:3000/guide.xml'),
        'auto_enabled': int(settings.get('auto_enabled', 0)),
        'auto_interval_minutes': int(settings.get('auto_interval_minutes', 360)),
        'last_sync_at': settings.get('last_sync_at', 'Never'),
        'last_message': settings.get('last_message', ''),
    })


# ═══════════════════════════════════════════════════════════════════════════════
# V7 — SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/settings', methods=['GET'])
def get_settings():
    if _USE_MYSQL:
        @cache.cached(timeout=TTL_SETTINGS, key_prefix='nv:settings')
        def _cached():
            conn = get_db()
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            conn.close()
            return {r['key']: r['value'] for r in rows}
        return jsonify(_cached())
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return jsonify({r['key']: r['value'] for r in rows})

@app.route('/api/settings/stamp', methods=['GET'])
def get_settings_stamp():
    """Lightweight endpoint TV clients can poll to detect config changes."""
    if _USE_MYSQL:
        @cache.cached(timeout=5, key_prefix='nv:settings_stamp')
        def _cached():
            conn = get_db()
            row = conn.execute("SELECT value FROM settings WHERE key='config_stamp'").fetchone()
            conn.close()
            return row['value'] if row else '0'
        return jsonify({'stamp': _cached()})
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key='config_stamp'").fetchone()
    conn.close()
    return jsonify({'stamp': row['value'] if row else '0'})

@app.route('/api/settings', methods=['POST'])
@admin_required
def save_settings():
    d = request.json or {}
    conn = get_db()
    for k, v in d.items():
        conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,CURRENT_TIMESTAMP)", (k, str(v)))
    # Bump config_stamp so TV clients detect the change and auto-refresh
    import time as _time
    conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('config_stamp',?,CURRENT_TIMESTAMP)",
                 (str(int(_time.time())),))
    conn.commit(); conn.close()
    if _USE_MYSQL: invalidate_settings()
    return jsonify({'ok': True})



# ═══════════════════════════════════════════════════════════════════════════════
# V8 — MESSAGE INBOX (per-room read tracking)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/messages/inbox', methods=['GET'])
def get_message_inbox():
    """
    Returns ALL non-expired messages for this room (including already-dismissed),
    plus a read status for each. Used by the guest Messages inbox screen.
    """
    token = request.headers.get('X-Room-Token', '').strip()
    conn  = get_db()
    room  = None
    if token:
        room = conn.execute("SELECT * FROM rooms WHERE room_token=?", (token,)).fetchone()

    rows = conn.execute("""
        SELECT m.*,
               CASE WHEN mr.id IS NOT NULL THEN 1 ELSE 0 END AS is_read
        FROM messages m
        LEFT JOIN message_reads mr
               ON mr.message_id = m.id AND mr.room_id = ?
        WHERE (m.expires_at IS NULL OR m.expires_at > datetime('now'))
          AND m.sent_at >= datetime('now', '-30 days')
        ORDER BY m.sent_at DESC
    """, (room['id'] if room else -1,)).fetchall()

    # Filter by target
    result = []
    for r in rows:
        msg = dict(r)
        target = msg.get('target', 'all')
        if target == 'all':
            result.append(msg)
        elif target == 'room' and room:
            ids = [x.strip() for x in (msg.get('room_ids') or '').split(',') if x.strip()]
            if str(room['id']) in ids or room['room_number'] in ids:
                result.append(msg)

    # ── Inject today's birthdays into inbox ───────────────────────────────────
    import datetime as _dt
    today = _dt.date.today().strftime('%m-%d')
    bdays = conn.execute("""
        SELECT * FROM birthdays
        WHERE active=1 AND strftime('%m-%d', birth_date) = ?
    """, (today,)).fetchall()

    for b in bdays:
        b = dict(b)
        if b.get('room_id') and room:
            if b['room_id'] != room['id']:
                continue
        elif b.get('room_id') and not room:
            continue
        result.append({
            'id':       90000 + b['id'],
            'type':     'birthday',
            'title':    f"🎂 Happy Birthday, {b['guest_name']}!",
            'body':     b.get('message') or 'Wishing you a wonderful birthday! May your day be filled with joy.',
            'target':   'room' if b.get('room_id') else 'all',
            'room_ids': str(b['room_id']) if b.get('room_id') else '',
            'active':   1,
            'is_read':  0,
            'sent_at':  _dt.date.today().isoformat(),
            'expires_at': None,
        })

    conn.close()
    return jsonify(result)

@app.route('/api/messages/unread-count', methods=['GET'])
def get_unread_count():
    """Returns unread message count for header badge."""
    token = request.headers.get('X-Room-Token', '').strip()
    conn  = get_db()
    room  = conn.execute("SELECT * FROM rooms WHERE room_token=?", (token,)).fetchone() if token else None
    if not room:
        conn.close()
        return jsonify({'count': 0})

    count = conn.execute("""
        SELECT COUNT(*) FROM messages m
        LEFT JOIN message_reads mr ON mr.message_id=m.id AND mr.room_id=?
        WHERE mr.id IS NULL
          AND (m.expires_at IS NULL OR m.expires_at > datetime('now'))
          AND m.sent_at >= datetime('now', '-30 days')
          AND (m.target='all' OR (m.target='room' AND (
              instr(','||m.room_ids||',', ','||?||',')>0
              OR instr(','||m.room_ids||',', ','||?||',')>0
          )))
    """, (room['id'], str(room['id']), room['room_number'])).fetchone()[0]

    conn.close()
    return jsonify({'count': count})

@app.route('/api/messages/<int:mid>/read', methods=['POST'])
def mark_message_read(mid):
    """Mark a message as read for this room."""
    token = request.headers.get('X-Room-Token', '').strip()
    conn  = get_db()
    room  = conn.execute("SELECT * FROM rooms WHERE room_token=?", (token,)).fetchone() if token else None
    if room:
        try:
            conn.execute("INSERT OR IGNORE INTO message_reads (message_id, room_id) VALUES (?,?)",
                         (mid, room['id']))
            conn.commit()
        except: pass
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/messages/mark-all-read', methods=['POST'])
def mark_all_messages_read():
    """Mark all current messages as read for this room."""
    token = request.headers.get('X-Room-Token', '').strip()
    conn  = get_db()
    room  = conn.execute("SELECT * FROM rooms WHERE room_token=?", (token,)).fetchone() if token else None
    if room:
        msgs = conn.execute("SELECT id FROM messages WHERE (expires_at IS NULL OR expires_at > datetime('now'))").fetchall()
        for m in msgs:
            try:
                conn.execute("INSERT OR IGNORE INTO message_reads (message_id, room_id) VALUES (?,?)",
                             (m['id'], room['id']))
            except: pass
        conn.commit()
    conn.close()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════════════════════
# V8 — PRAYER TIMES
# ═══════════════════════════════════════════════════════════════════════════════

import urllib.request as _ureq

# Simple in-memory cache: {date_city: {times, cached_at}}
_prayer_cache = {}

@app.route('/api/prayer', methods=['GET'])
def get_prayer_times():
    """
    Returns today's prayer times.
    Uses aladhan.com API with server-side caching (refresh once per day).
    Respects prayer_enabled setting — returns {enabled:false} if disabled.
    """
    conn = get_db()
    settings = {r['key']: r['value'] for r in conn.execute("SELECT key,value FROM settings").fetchall()}
    conn.close()

    if settings.get('prayer_enabled', '0') != '1':
        return jsonify({'enabled': False})

    city    = settings.get('prayer_city',    'Dubai')
    country = settings.get('prayer_country', 'AE')
    method  = settings.get('prayer_method',  '4')

    import datetime as _dt
    today   = _dt.date.today().isoformat()
    cache_k = f"{today}_{city}_{country}_{method}"

    # Return cached if valid
    if cache_k in _prayer_cache:
        data = _prayer_cache[cache_k]
        data['enabled'] = True
        return jsonify(data)

    try:
        url = (f"https://api.aladhan.com/v1/timingsByCity"
               f"?city={city}&country={country}&method={method}")
        req2 = _ureq.Request(url, headers={'User-Agent': 'NexVision/8.0'})
        with _ureq.urlopen(req2, timeout=8) as resp:
            raw = __import__('json').loads(resp.read())

        timings = raw.get('data', {}).get('timings', {})
        date_info = raw.get('data', {}).get('date', {})
        hijri = date_info.get('hijri', {})

        result = {
            'enabled':  True,
            'city':     city,
            'country':  country,
            'date':     today,
            'hijri':    hijri.get('date', ''),
            'hijri_month': hijri.get('month', {}).get('en', ''),
            'timings': {
                'Fajr':    timings.get('Fajr',    ''),
                'Sunrise': timings.get('Sunrise', ''),
                'Dhuhr':   timings.get('Dhuhr',   ''),
                'Asr':     timings.get('Asr',     ''),
                'Maghrib': timings.get('Maghrib', ''),
                'Isha':    timings.get('Isha',    ''),
                'Midnight':timings.get('Midnight',''),
            }
        }
        _prayer_cache[cache_k] = result
        return jsonify(result)

    except Exception as e:
        # Fallback: return approximate Dubai times if API unavailable
        return jsonify({
            'enabled': True,
            'city': city,
            'date': today,
            'hijri': '',
            'hijri_month': '',
            'offline': True,
            'timings': {
                'Fajr':    '05:13',
                'Sunrise': '06:33',
                'Dhuhr':   '12:22',
                'Asr':     '15:46',
                'Maghrib': '18:10',
                'Isha':    '19:40',
                'Midnight':'00:16',
            }
        })

@app.route('/api/prayer/settings', methods=['POST'])
@admin_required
def save_prayer_settings():
    d = request.json or {}
    conn = get_db()
    for k in ['prayer_enabled', 'prayer_city', 'prayer_country', 'prayer_method', 'prayer_notify']:
        if k in d:
            conn.execute("INSERT OR REPLACE INTO settings (key,value,updated_at) VALUES (?,?,CURRENT_TIMESTAMP)",
                         (k, str(d[k])))
    conn.commit(); conn.close()
    # Clear cache so next request fetches fresh data
    _prayer_cache.clear()
    return jsonify({'ok': True})




# ═══════════════════════════════════════════════════════════════════════════════
# FILE UPLOAD (local images/videos for slides, hotel logo, etc.)
# ═══════════════════════════════════════════════════════════════════════════════

import os as _os, uuid as _uuid
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = _os.path.join(BASE_DIR, 'uploads')
_os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXT = {'png','jpg','jpeg','gif','webp','mp4','webm','mov','avi'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXT

@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/api/upload', methods=['POST'])
@admin_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(f.filename):
        return jsonify({'error': 'File type not allowed. Use: jpg, png, gif, webp, mp4, webm'}), 400
    ext  = f.filename.rsplit('.',1)[1].lower()
    name = str(_uuid.uuid4()) + '.' + ext
    f.save(_os.path.join(UPLOAD_FOLDER, name))
    url = request.host_url.rstrip('/') + '/uploads/' + name
    return jsonify({'ok': True, 'url': url, 'filename': name})

# ═══════════════════════════════════════════════════════════════════════════════
# V8 — PROMO SLIDES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/slides', methods=['GET'])
def get_slides_public():
    if _USE_MYSQL:
        @cache.cached(timeout=TTL_SLIDES, key_prefix='nv:slides_public')
        def _cached():
            conn = get_db()
            rows = conn.execute(
                "SELECT * FROM promo_slides WHERE active=1 ORDER BY sort_order, id"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        return jsonify(_cached())
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM promo_slides WHERE active=1 ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/slides/all', methods=['GET'])
@admin_required
def get_slides_all():
    conn = get_db()
    rows = conn.execute("SELECT * FROM promo_slides ORDER BY sort_order, id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/slides', methods=['POST'])
@admin_required
def create_slide():
    d = request.json
    conn = get_db()
    max_ord = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM promo_slides").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO promo_slides (title,subtitle,image_url,video_url,media_type,link_action,sort_order,duration_seconds,active) VALUES (?,?,?,?,?,?,?,?,?)",
        (d.get('title',''), d.get('subtitle',''), d.get('image_url',''), d.get('video_url',''),
         d.get('media_type','image'), d.get('link_action',''), max_ord+1, d.get('duration_seconds',5), d.get('active',1)))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM promo_slides WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    if _USE_MYSQL: invalidate_slides()
    return jsonify(row), 201

@app.route('/api/slides/<int:sid>', methods=['PUT'])
@admin_required
def update_slide(sid):
    d = request.json
    conn = get_db()
    conn.execute(
        "UPDATE promo_slides SET title=?,subtitle=?,image_url=?,video_url=?,media_type=?,link_action=?,sort_order=?,duration_seconds=?,active=? WHERE id=?",
        (d.get('title',''), d.get('subtitle',''), d.get('image_url',''), d.get('video_url',''),
         d.get('media_type','image'), d.get('link_action',''), d.get('sort_order',0), d.get('duration_seconds',5), d.get('active',1), sid))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM promo_slides WHERE id=?", (sid,)).fetchone())
    conn.close()
    if _USE_MYSQL: invalidate_slides()
    return jsonify(row)

@app.route('/api/slides/<int:sid>', methods=['DELETE'])
@admin_required
def delete_slide(sid):
    conn = get_db()
    conn.execute("DELETE FROM promo_slides WHERE id=?", (sid,))
    conn.commit(); conn.close()
    if _USE_MYSQL: invalidate_slides()
    return jsonify({'ok': True})

@app.route('/api/slides/reorder', methods=['POST'])
@admin_required
def reorder_slides():
    order = request.json.get('order', [])
    conn = get_db()
    for item in order:
        conn.execute("UPDATE promo_slides SET sort_order=? WHERE id=?", (item['sort_order'], item['id']))
    conn.commit(); conn.close()
    if _USE_MYSQL: invalidate_slides()
    return jsonify({'ok': True})

# ═══════════════════════════════════════════════════════════════════════════════
# V8 — NAVIGATION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/nav', methods=['GET'])
def get_nav():
    """Public — TV client fetches this on startup."""
    if _USE_MYSQL:
        @cache.cached(timeout=TTL_NAV, key_prefix='nv:nav_public')
        def _cached():
            conn = get_db()
            items = [dict(r) for r in conn.execute(
                "SELECT * FROM nav_items ORDER BY sort_order, id").fetchall()]
            pos_row   = conn.execute("SELECT value FROM settings WHERE key='navbar_position'").fetchone()
            style_row = conn.execute("SELECT value FROM settings WHERE key='navbar_style'").fetchone()
            conn.close()
            return {
                'items':    items,
                'position': pos_row['value'] if pos_row else 'top',
                'style':    style_row['value'] if style_row else 'pill',
            }
        return jsonify(_cached())
    conn = get_db()
    items = [dict(r) for r in conn.execute(
        "SELECT * FROM nav_items ORDER BY sort_order, id").fetchall()]
    pos_row = conn.execute("SELECT value FROM settings WHERE key='navbar_position'").fetchone()
    style_row = conn.execute("SELECT value FROM settings WHERE key='navbar_style'").fetchone()
    conn.close()
    return jsonify({
        'items':    items,
        'position': pos_row['value'] if pos_row else 'top',
        'style':    style_row['value'] if style_row else 'pill',
    })

@app.route('/api/nav/items', methods=['GET'])
@admin_required
def get_nav_items_admin():
    conn = get_db()
    items = [dict(r) for r in conn.execute(
        "SELECT * FROM nav_items ORDER BY sort_order, id").fetchall()]
    pos_row   = conn.execute("SELECT value FROM settings WHERE key='navbar_position'").fetchone()
    style_row = conn.execute("SELECT value FROM settings WHERE key='navbar_style'").fetchone()
    conn.close()
    return jsonify({
        'items':    items,
        'position': pos_row['value'] if pos_row else 'top',
        'style':    style_row['value'] if style_row else 'pill',
    })

@app.route('/api/nav/items', methods=['POST'])
@admin_required
def create_nav_item():
    d = request.json
    conn = get_db()
    # key must be unique; generate slug from label if not provided
    key = d.get('key') or re.sub(r'[^a-z0-9_]', '_', d['label'].lower().strip())
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM nav_items").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO nav_items (key, label, icon, enabled, sort_order, is_system, target_url) VALUES (?,?,?,?,?,0,?)",
        (key, d['label'], d.get('icon','📄'), d.get('enabled',1), max_order+1, d.get('target_url','')))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM nav_items WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    if _USE_MYSQL: invalidate_nav()
    return jsonify(row), 201

@app.route('/api/nav/items/<int:nid>', methods=['PUT'])
@admin_required
def update_nav_item(nid):
    d = request.json
    conn = get_db()
    conn.execute(
        "UPDATE nav_items SET label=?, icon=?, enabled=?, target_url=? WHERE id=?",
        (d['label'], d.get('icon','📄'), d.get('enabled',1), d.get('target_url',''), nid))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM nav_items WHERE id=?", (nid,)).fetchone())
    conn.close()
    if _USE_MYSQL: invalidate_nav()
    return jsonify(row)

@app.route('/api/nav/items/<int:nid>/toggle', methods=['POST'])
@admin_required
def toggle_nav_item(nid):
    conn = get_db()
    conn.execute("UPDATE nav_items SET enabled = CASE WHEN enabled=1 THEN 0 ELSE 1 END WHERE id=?", (nid,))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM nav_items WHERE id=?", (nid,)).fetchone())
    conn.close()
    if _USE_MYSQL: invalidate_nav()
    return jsonify(row)

@app.route('/api/nav/items/<int:nid>', methods=['DELETE'])
@admin_required
def delete_nav_item(nid):
    conn = get_db()
    item = conn.execute("SELECT is_system FROM nav_items WHERE id=?", (nid,)).fetchone()
    if item and item['is_system']:
        conn.close()
        return jsonify({'error': 'Cannot delete system menu items. Disable them instead.'}), 400
    conn.execute("DELETE FROM nav_items WHERE id=?", (nid,))
    conn.commit(); conn.close()
    if _USE_MYSQL: invalidate_nav()
    return jsonify({'ok': True})

@app.route('/api/nav/reorder', methods=['POST'])
@admin_required
def reorder_nav():
    """Accepts [{id, sort_order}, ...] and saves new order."""
    order = request.json.get('order', [])
    conn  = get_db()
    for item in order:
        conn.execute("UPDATE nav_items SET sort_order=? WHERE id=?", (item['sort_order'], item['id']))
    conn.commit(); conn.close()
    if _USE_MYSQL: invalidate_nav()
    return jsonify({'ok': True})

@app.route('/api/nav/position', methods=['POST'])
@admin_required
def set_nav_position():
    d = request.json
    conn = get_db()
    pos   = d.get('position', 'top')
    style = d.get('style', 'pill')
    conn.execute("INSERT OR REPLACE INTO settings (key,value,updated_at) VALUES ('navbar_position',?,CURRENT_TIMESTAMP)", (pos,))
    conn.execute("INSERT OR REPLACE INTO settings (key,value,updated_at) VALUES ('navbar_style',?,CURRENT_TIMESTAMP)", (style,))
    conn.commit(); conn.close()
    if _USE_MYSQL: invalidate_nav()
    return jsonify({'ok': True, 'position': pos, 'style': style})



@app.route('/api/content/items/<int:iid>/upload', methods=['POST'])
@admin_required
def upload_content_item_image(iid):
    """Upload a local image for a content item and set its photo_url."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(f.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    ext  = f.filename.rsplit('.',1)[1].lower()
    name = 'content_' + str(_uuid.uuid4()) + '.' + ext
    f.save(_os.path.join(UPLOAD_FOLDER, name))
    url  = request.host_url.rstrip('/') + '/uploads/' + name
    # Update photo_url in DB
    conn = get_db()
    conn.execute("UPDATE content_items SET photo_url=?, image=? WHERE id=?", (url, url, iid))
    _bump_stamp(conn)
    conn.commit()
    item = dict(conn.execute("SELECT * FROM content_items WHERE id=?", (iid,)).fetchone())
    conn.close()
    return jsonify({'ok': True, 'url': url, 'item': item})


@app.route('/api/content/items/<int:iid>/gallery', methods=['GET'])
def get_item_gallery(iid):
    """Return all gallery images for a content item."""
    conn = get_db()
    imgs = [dict(r) for r in conn.execute(
        "SELECT id, url, position, fit, sort_order FROM content_item_images WHERE item_id=? ORDER BY sort_order, id",
        (iid,)).fetchall()]
    conn.close()
    return jsonify(imgs)

@app.route('/api/content/items/<int:iid>/gallery', methods=['POST'])
@admin_required
def add_item_gallery_url(iid):
    """Add an image URL to item gallery."""
    d = request.json
    url = (d or {}).get('url', '').strip()
    if not url:
        return jsonify({'error': 'url required'}), 400
    conn = get_db()
    max_ord = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM content_item_images WHERE item_id=?", (iid,)).fetchone()[0]
    conn.execute("INSERT INTO content_item_images (item_id, url, sort_order) VALUES (?,?,?)", (iid, url, max_ord+1))
    _bump_stamp(conn)
    conn.commit()
    imgs = [dict(r) for r in conn.execute(
        "SELECT id, url, position, fit, sort_order FROM content_item_images WHERE item_id=? ORDER BY sort_order, id", (iid,)).fetchall()]
    conn.close()
    return jsonify(imgs), 201

@app.route('/api/content/items/<int:iid>/gallery/upload', methods=['POST'])
@admin_required
def upload_item_gallery_image(iid):
    """Upload an image file and add it to item gallery."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(f.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    ext  = f.filename.rsplit('.',1)[1].lower()
    name = 'gallery_' + str(_uuid.uuid4()) + '.' + ext
    f.save(_os.path.join(UPLOAD_FOLDER, name))
    url  = request.host_url.rstrip('/') + '/uploads/' + name
    conn = get_db()
    max_ord = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM content_item_images WHERE item_id=?", (iid,)).fetchone()[0]
    conn.execute("INSERT INTO content_item_images (item_id, url, sort_order) VALUES (?,?,?)", (iid, url, max_ord+1))
    _bump_stamp(conn)
    conn.commit()
    imgs = [dict(r) for r in conn.execute(
        "SELECT id, url, position, fit, sort_order FROM content_item_images WHERE item_id=? ORDER BY sort_order, id", (iid,)).fetchall()]
    conn.close()
    return jsonify({'ok': True, 'url': url, 'images': imgs})

@app.route('/api/content/item-images/<int:imgid>', methods=['DELETE'])
@admin_required
def delete_item_gallery_image(imgid):
    """Delete a single gallery image."""
    conn = get_db()
    conn.execute("DELETE FROM content_item_images WHERE id=?", (imgid,))
    _bump_stamp(conn)
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

@app.route('/api/content/item-images/<int:imgid>', methods=['PATCH'])
@admin_required
def update_item_gallery_image(imgid):
    """Update position/fit adjustment of a gallery image."""
    d = request.json or {}
    conn = get_db()
    conn.execute(
        "UPDATE content_item_images SET position=?, fit=? WHERE id=?",
        (d.get('position', 'center center'), d.get('fit', 'cover'), imgid))
    _bump_stamp(conn)
    conn.commit()
    row = dict(conn.execute(
        "SELECT id, url, position, fit, sort_order FROM content_item_images WHERE id=?",
        (imgid,)).fetchone())
    conn.close()
    return jsonify(row)


@app.route('/api/services/<int:sid>/upload', methods=['POST'])
@admin_required
def upload_service_image(sid):
    """Upload a local image/icon for a guest service."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(f.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    ext  = f.filename.rsplit('.',1)[1].lower()
    name = 'svc_' + str(_uuid.uuid4()) + '.' + ext
    f.save(_os.path.join(UPLOAD_FOLDER, name))
    url  = request.host_url.rstrip('/') + '/uploads/' + name
    conn = get_db()
    conn.execute("UPDATE guest_services SET icon=? WHERE id=?", (url, sid))
    _bump_stamp(conn)
    conn.commit()
    row = dict(conn.execute("SELECT * FROM guest_services WHERE id=?", (sid,)).fetchone())
    conn.close()
    return jsonify({'ok': True, 'url': url, 'service': row})



# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN EDITOR TOOLS — Rich text + local image upload helpers
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/admin/editor-config', methods=['GET'])
@admin_required
def get_editor_config():
    """Returns available editor capabilities for the admin panel."""
    return jsonify({
        'rich_text': True,
        'image_upload': True,
        'upload_endpoint': '/api/upload',
        'content_item_upload_endpoint': '/api/content/items/{id}/upload',
        'service_upload_endpoint': '/api/services/{id}/upload',
        'allowed_types': list(ALLOWED_EXT),
        'max_size_mb': 5,
        'features': ['bold','italic','underline','lists','headings','links','images'],
    })


@app.route('/api/content/<int:pid>/items/full', methods=['GET'])
@admin_required
def get_content_items_full(pid):
    """Returns content items with ALL fields including content_html and photo_url."""
    conn = get_db()
    items = [dict(r) for r in conn.execute(
        "SELECT id, page_id, title, description, content_html, photo_url, image, active, sort_order "
        "FROM content_items WHERE page_id=? ORDER BY sort_order, id", (pid,)).fetchall()]
    conn.close()
    return jsonify(items)

@app.route('/admin/')
@app.route('/admin')
def serve_admin():
    resp = send_from_directory(ADMIN_DIR, 'index.html')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

@app.route('/admin/<path:filename>')
def serve_admin_static(filename):
    return send_from_directory(ADMIN_DIR, filename)

@app.route('/cast-receiver')
def serve_cast_receiver():
    resp = send_from_directory(CAST_DIR, 'receiver.html')
    # Cast SDK fetches the receiver fresh on every session — never serve stale.
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


# ─── Cast Session Tracking ────────────────────────────────────────────────────

@app.route('/api/cast/session', methods=['POST'])
def cast_session_start():
    """Record a new Chromecast session when the receiver begins playback."""
    d = request.get_json(silent=True) or {}
    room_id         = d.get('room_id')
    channel_id      = d.get('channel_id')
    sender_platform = str(d.get('sender_platform', ''))[:64]
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO cast_sessions (room_id, channel_id, sender_platform)
           VALUES (?, ?, ?)""",
        (room_id, channel_id, sender_platform),
    )
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': session_id}), 201


@app.route('/api/cast/session/<int:session_id>', methods=['PATCH'])
def cast_session_end(session_id):
    """Update ended_at and duration_seconds when the cast session finishes."""
    d = request.get_json(silent=True) or {}
    ended_at         = d.get('ended_at')        # ISO-8601 string or None (defaults to NOW)
    duration_seconds = d.get('duration_seconds') # integer, required
    conn = get_db()
    if ended_at:
        conn.execute(
            """UPDATE cast_sessions
               SET ended_at = ?, duration_seconds = ?
               WHERE id = ?""",
            (ended_at, duration_seconds, session_id),
        )
    else:
        conn.execute(
            """UPDATE cast_sessions
               SET ended_at = CURRENT_TIMESTAMP, duration_seconds = ?
               WHERE id = ?""",
            (duration_seconds, session_id),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM cast_sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Session not found'}), 404
    return jsonify(dict(row))


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_tv(path):
    if path.startswith('api/'):
        return jsonify({'error': 'Not found'}), 404
    if path.startswith('admin'):
        return send_from_directory(ADMIN_DIR, 'index.html')
    # Serve PWA static files directly (manifest, service worker, icons)
    if path in ('manifest.json', 'sw.js') or path.startswith('icon-'):
        resp = send_from_directory(TV_DIR, path)
        if path == 'sw.js':
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            resp.headers['Service-Worker-Allowed'] = '/'
        return resp
    return send_from_directory(TV_DIR, 'index.html')

# ══════════════════════════════════════════════════════════════════════════════
# VOD STREAMING SERVER  (merged from vod_server.py)
# All routes are prefixed with  /vod/
#   VOD API:      /vod/api/videos, /vod/api/upload, /vod/api/import, …
#   HLS streams:  /vod/hls/<video_id>/master.m3u8
#   Thumbnails:   /vod/thumbnails/<filename>
#   Dashboard:    /vod/
#   Auth:         X-API-Key header  (env: VOD_API_KEY)
# ══════════════════════════════════════════════════════════════════════════════

# ─── VOD Config ───────────────────────────────────────────────────────────────

VOD_BASE_DIR   = Path(BASE_DIR) / 'vod'
VIDEOS_DIR     = VOD_BASE_DIR / 'videos'
HLS_DIR        = VOD_BASE_DIR / 'hls'
THUMBS_DIR     = VOD_BASE_DIR / 'thumbnails'
UPLOADS_DIR    = VOD_BASE_DIR / 'uploads'
VOD_DB_PATH    = VOD_BASE_DIR / 'vod.db'

for _vod_d in [VIDEOS_DIR, HLS_DIR, THUMBS_DIR, UPLOADS_DIR]:
    _vod_d.mkdir(parents=True, exist_ok=True)

QUALITY_PROFILES = [
    ('1080p', '1920x1080', '4000k', '192k'),
    ('720p',  '1280x720',  '2500k', '128k'),
    ('480p',  '854x480',   '1000k', '128k'),
    ('360p',  '640x360',   '600k',  '96k'),
]

DEFAULT_QUALITIES   = ['720p', '480p', '360p']
HLS_SEGMENT_SECS    = 4
THUMB_TIME_PERCENT  = 10
ALLOWED_VIDEO_EXTS  = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.ts', '.m4v', '.flv', '.wmv'}
MAX_UPLOAD_MB       = 10_000

VOD_NEXVISION_URL   = os.environ.get('NEXVISION_URL', 'http://localhost:5000')
VOD_NEXVISION_TOKEN = os.environ.get('NEXVISION_TOKEN', '')
VOD_API_KEY         = os.environ.get('VOD_API_KEY', 'nexvision-vod-key-2024')

# ─── FFmpeg path resolution (Windows-safe) ────────────────────────────────────
import shutil as _shutil

def _find_ffmpeg():
    """
    Find ffmpeg/ffprobe executable.
    Search order:
      1. FFMPEG_PATH environment variable (full path or folder)
      2. Folder next to app.py: ./ffmpeg/bin/ffmpeg.exe  or  ./ffmpeg/ffmpeg.exe
      3. System PATH (works on Linux/Mac; often missing on Windows)
    """
    import os as _os2
    from pathlib import Path as _P2

    # env override — can be "C:/ffmpeg/bin/ffmpeg.exe" or just "C:/ffmpeg/bin"
    env_path = _os2.environ.get('FFMPEG_PATH', '').strip()
    if env_path:
        p = _P2(env_path)
        if p.is_file():
            return str(p), str(p.parent / ('ffprobe' + ('.exe' if _os2.name == 'nt' else '')))
        if p.is_dir():
            ext = '.exe' if _os2.name == 'nt' else ''
            return str(p / f'ffmpeg{ext}'), str(p / f'ffprobe{ext}')

    # look next to app.py
    ext = '.exe' if _os2.name == 'nt' else ''
    base = _P2(__file__).parent
    candidates = [
        base / 'ffmpeg' / 'bin' / f'ffmpeg{ext}',
        base / 'ffmpeg' / f'ffmpeg{ext}',
        base / 'bin' / f'ffmpeg{ext}',
        base / f'ffmpeg{ext}',
    ]
    for c in candidates:
        if c.exists():
            probe = c.parent / f'ffprobe{ext}'
            return str(c), str(probe)

    # fall back to PATH
    ff  = _shutil.which('ffmpeg')
    ffp = _shutil.which('ffprobe')
    if ff:
        return ff, (ffp or ff.replace('ffmpeg', 'ffprobe'))

    return 'ffmpeg', 'ffprobe'   # last resort — will fail with WinError 2

FFMPEG_BIN, FFPROBE_BIN = _find_ffmpeg()

def _check_ffmpeg_available():
    """Return (ok, version_string, error_message)"""
    import subprocess as _sp
    try:
        out = _sp.check_output([FFMPEG_BIN, '-version'],
                               stderr=_sp.STDOUT, timeout=5)
        line = out.decode(errors='replace').splitlines()[0]
        return True, line, ''
    except FileNotFoundError:
        msg = (
            f"FFmpeg not found at: {FFMPEG_BIN}\n"
            "To fix this on Windows:\n"
            "  1. Download FFmpeg: https://www.gyan.dev/ffmpeg/builds/ (ffmpeg-release-essentials.zip)\n"
            "  2. Extract and place the 'ffmpeg' folder next to app.py  (so app.py/ffmpeg/bin/ffmpeg.exe exists)\n"
            "     OR add FFmpeg to your system PATH\n"
            "     OR set environment variable: FFMPEG_PATH=C:\\ffmpeg\\bin"
        )
        return False, '', msg
    except Exception as e:
        return False, '', str(e)


_transcode_jobs = {}
_transcode_lock = threading.Lock()
_VOD_PORT       = 5000   # updated at startup

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
vod_log = logging.getLogger('nexvision-vod')

# ─── VOD Database ─────────────────────────────────────────────────────────────

def vod_get_db():
    if _USE_MYSQL:
        return get_vod_mysql_db()
    conn = sqlite3.connect(str(VOD_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def vod_init_db():
    conn = vod_get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS videos (
        id           TEXT PRIMARY KEY,
        title        TEXT NOT NULL,
        description  TEXT DEFAULT '',
        filename     TEXT NOT NULL,
        original_url TEXT DEFAULT '',
        filesize     INTEGER DEFAULT 0,
        duration     REAL  DEFAULT 0,
        width        INTEGER DEFAULT 0,
        height       INTEGER DEFAULT 0,
        fps          REAL  DEFAULT 0,
        video_codec  TEXT DEFAULT '',
        audio_codec  TEXT DEFAULT '',
        bitrate      INTEGER DEFAULT 0,
        thumbnail    TEXT DEFAULT '',
        status       TEXT DEFAULT 'pending',
        qualities    TEXT DEFAULT '[]',
        hls_path     TEXT DEFAULT '',
        tags         TEXT DEFAULT '',
        category     TEXT DEFAULT '',
        year         INTEGER DEFAULT 0,
        language     TEXT DEFAULT 'en',
        rating       REAL  DEFAULT 0,
        nexvision_id INTEGER DEFAULT 0,
        views        INTEGER DEFAULT 0,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS transcode_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id   TEXT NOT NULL,
        quality    TEXT NOT NULL,
        status     TEXT DEFAULT 'queued',
        started_at TIMESTAMP,
        ended_at   TIMESTAMP,
        error      TEXT DEFAULT '',
        FOREIGN KEY (video_id) REFERENCES videos(id)
    );

    CREATE TABLE IF NOT EXISTS stream_sessions (
        id          TEXT PRIMARY KEY,
        video_id    TEXT NOT NULL,
        ip          TEXT DEFAULT '',
        user_agent  TEXT DEFAULT '',
        quality     TEXT DEFAULT '',
        started_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        bytes_sent  INTEGER DEFAULT 0,
        FOREIGN KEY (video_id) REFERENCES videos(id)
    );

    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """)
    defaults = [
        ('server_name',         'NexVision VOD'),
        ('nexvision_url',       VOD_NEXVISION_URL),
        ('nexvision_token',     VOD_NEXVISION_TOKEN),
        ('default_qualities',   json.dumps(DEFAULT_QUALITIES)),
        ('hls_segment_secs',    str(HLS_SEGMENT_SECS)),
        ('max_upload_mb',       str(MAX_UPLOAD_MB)),
        ('auto_push_nexvision', '1'),
    ]
    for k, v in defaults:
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v))
    conn.commit()

    # Migrate stream_sessions — add device_type if missing
    try:
        conn.execute("ALTER TABLE stream_sessions ADD COLUMN device_type TEXT DEFAULT 'browser'")
        conn.commit()
    except Exception:
        pass  # column already exists

    conn.close()

# ─── VOD Auth ─────────────────────────────────────────────────────────────────

def require_api_key(f):
    """API key guard for VOD write operations (X-API-Key header or ?api_key= query param)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = (
            request.headers.get('X-API-Key') or
            request.args.get('api_key') or
            ''
        )
        if key != VOD_API_KEY:
            return jsonify({'error': 'Invalid or missing API key. Pass X-API-Key header.'}), 401
        return f(*args, **kwargs)
    return decorated

# ─── FFprobe helpers ──────────────────────────────────────────────────────────

def probe_video(path: Path) -> dict:
    """Run ffprobe and return video metadata."""
    cmd = [
        FFPROBE_BIN, '-v', 'quiet',
        '-print_format', 'json',
        '-show_format', '-show_streams',
        str(path)
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=30)
        data = json.loads(out)
    except Exception as e:
        vod_log.warning(f"ffprobe failed for {path}: {e}")
        return {}

    info = {'duration': 0, 'width': 0, 'height': 0, 'fps': 0,
            'video_codec': '', 'audio_codec': '', 'bitrate': 0, 'filesize': 0}

    fmt = data.get('format', {})
    info['duration']  = float(fmt.get('duration', 0))
    info['bitrate']   = int(fmt.get('bit_rate', 0))
    info['filesize']  = int(fmt.get('size', path.stat().st_size if path.exists() else 0))

    for stream in data.get('streams', []):
        codec_type = stream.get('codec_type', '')
        if codec_type == 'video' and not info['video_codec']:
            info['video_codec'] = stream.get('codec_name', '')
            info['width']       = stream.get('width', 0)
            info['height']      = stream.get('height', 0)
            fps_str = stream.get('r_frame_rate', '0/1')
            try:
                num, den = fps_str.split('/')
                info['fps'] = round(float(num) / float(den), 2) if float(den) else 0
            except Exception:
                info['fps'] = 0
        elif codec_type == 'audio' and not info['audio_codec']:
            info['audio_codec'] = stream.get('codec_name', '')

    return info

# ─── Thumbnail generation ─────────────────────────────────────────────────────

def generate_thumbnail(video_path: Path, video_id: str, duration: float) -> str:
    """Extract a thumbnail frame. Returns relative URL path."""
    thumb_file = THUMBS_DIR / f"{video_id}.jpg"
    t = max(1.0, duration * (THUMB_TIME_PERCENT / 100))
    cmd = [
        FFMPEG_BIN, '-y',
        '-ss', str(t),
        '-i', str(video_path),
        '-vframes', '1',
        '-vf', 'scale=640:-1',
        '-q:v', '4',
        str(thumb_file)
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
        if thumb_file.exists():
            return f'/vod/thumbnails/{video_id}.jpg'
    except Exception as e:
        vod_log.warning(f"Thumbnail generation failed: {e}")
    return ''

# ─── HLS Transcoding ──────────────────────────────────────────────────────────

def get_quality_profile(name: str):
    for p in QUALITY_PROFILES:
        if p[0] == name:
            return p
    return None


def _build_ffmpeg_cmd(input_path: Path, output_dir: Path, quality: str,
                      video_width: int, video_height: int) -> list:
    """Build FFmpeg command for HLS transcoding at a given quality."""
    prof = get_quality_profile(quality)
    if not prof:
        raise ValueError(f"Unknown quality profile: {quality}")

    _, res, vbr, abr = prof
    target_w, target_h = map(int, res.split('x'))

    if video_width and video_height:
        scale_h = min(target_h, video_height)
        vf = f'scale=-2:{scale_h}'
    else:
        vf = f'scale=-2:{target_h}'

    output_dir.mkdir(parents=True, exist_ok=True)
    m3u8 = output_dir / 'index.m3u8'

    cmd = [
        FFMPEG_BIN, '-y',
        '-i', str(input_path),
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-maxrate', vbr,
        '-bufsize', str(int(vbr.rstrip('k')) * 2) + 'k',
        '-vf', vf,
        '-pix_fmt', 'yuv420p',
        '-profile:v', 'main',
        '-level', '4.0',
        '-c:a', 'aac',
        '-b:a', abr,
        '-ar', '44100',
        '-ac', '2',
        '-f', 'hls',
        '-hls_time', str(HLS_SEGMENT_SECS),
        '-hls_list_size', '0',
        '-hls_segment_filename', str(output_dir / 'seg_%05d.ts'),
        '-hls_playlist_type', 'vod',
        '-hls_flags', 'independent_segments',
        str(m3u8)
    ]
    return cmd


def _progress_reader(proc, video_id: str, quality: str, duration: float):
    """Read FFmpeg stderr and update job progress."""
    pattern = re.compile(r'time=(\d+):(\d+):(\d+)\.(\d+)')
    for line in proc.stderr:
        line = line.decode('utf-8', errors='replace').strip()
        m = pattern.search(line)
        if m and duration > 0:
            h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            elapsed = h * 3600 + mi * 60 + s + cs / 100
            pct = min(99, int(elapsed / duration * 100))
            with _transcode_lock:
                if video_id in _transcode_jobs:
                    jq = _transcode_jobs[video_id].get('quality_progress', {})
                    jq[quality] = pct
                    _transcode_jobs[video_id]['quality_progress'] = jq
                    all_p = list(jq.values())
                    _transcode_jobs[video_id]['progress'] = int(sum(all_p) / len(all_p))


def transcode_video(video_id: str, input_path: Path, qualities: list,
                    video_width: int, video_height: int, duration: float):
    """
    Transcode a video to HLS for each requested quality.
    Runs in a background thread. Updates DB on completion.
    """
    vod_log.info(f"[transcode] Start {video_id} qualities={qualities}")

    with _transcode_lock:
        _transcode_jobs[video_id] = {
            'status': 'transcoding',
            'progress': 0,
            'quality_progress': {q: 0 for q in qualities},
            'error': None,
            'started_at': time.time(),
        }

    conn = vod_get_db()
    conn.execute("UPDATE videos SET status='transcoding', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                 (video_id,))
    conn.execute("INSERT INTO transcode_log (video_id, quality, status, started_at) VALUES (?,?,?,?)",
                 (video_id, ','.join(qualities), 'running', datetime.utcnow().isoformat()))
    conn.commit()

    completed_qualities = []
    error_msg = None

    for quality in qualities:
        vod_log.info(f"[transcode] {video_id} -> {quality}")
        output_dir = HLS_DIR / video_id / quality
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            cmd = _build_ffmpeg_cmd(input_path, output_dir, quality, video_width, video_height)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            with _transcode_lock:
                if video_id in _transcode_jobs:
                    _transcode_jobs[video_id]['pid'] = proc.pid

            _progress_reader(proc, video_id, quality, duration)
            proc.wait()

            if proc.returncode == 0:
                completed_qualities.append(quality)
                vod_log.info(f"[transcode] {video_id} {quality} OK")
            else:
                error_msg = f"FFmpeg failed for quality {quality} (exit {proc.returncode})"
                vod_log.error(f"[transcode] {video_id} {quality} FAIL — {error_msg}")
                break

        except Exception as e:
            error_msg = str(e)
            vod_log.error(f"[transcode] {video_id} exception: {e}")
            break

    master_path = HLS_DIR / video_id / 'master.m3u8'
    if completed_qualities:
        _write_master_playlist(master_path, video_id, completed_qualities)

    final_status = 'ready' if completed_qualities else 'error'
    hls_url = (
        f'/vod/hls/{video_id}/master.m3u8' if len(completed_qualities) > 1
        else (f'/vod/hls/{video_id}/{completed_qualities[0]}/index.m3u8' if completed_qualities else '')
    )

    conn.execute(
        "UPDATE videos SET status=?, qualities=?, hls_path=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (final_status, json.dumps(completed_qualities), hls_url, video_id)
    )
    conn.execute(
        "UPDATE transcode_log SET status=?, ended_at=?, error=? WHERE video_id=? AND status='running'",
        (final_status, datetime.utcnow().isoformat(), error_msg or '', video_id)
    )
    conn.commit()

    row = conn.execute("SELECT * FROM videos WHERE id=?", (video_id,)).fetchone()
    conn.close()

    if row and final_status == 'ready':
        _vod_push_to_nexvision(dict(row), hls_url)

    with _transcode_lock:
        if video_id in _transcode_jobs:
            _transcode_jobs[video_id].update({
                'status':   final_status,
                'progress': 100 if final_status == 'ready' else _transcode_jobs[video_id].get('progress', 0),
                'error':    error_msg,
                'ended_at': time.time(),
            })

    vod_log.info(f"[transcode] {video_id} done -> {final_status} | qualities={completed_qualities}")


def _write_master_playlist(path: Path, video_id: str, qualities: list):
    """Write an HLS master playlist referencing all quality variants."""
    lines = ['#EXTM3U', '#EXT-X-VERSION:3']
    for q in qualities:
        prof = get_quality_profile(q)
        if not prof:
            continue
        _, res, vbr, _ = prof
        bw = int(vbr.rstrip('k')) * 1000
        w, h = res.split('x')
        lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={w}x{h},NAME="{q}"')
        lines.append(f'{q}/index.m3u8')
    path.write_text('\n'.join(lines) + '\n')

# ─── NexVision Integration ────────────────────────────────────────────────────

def _vod_push_to_nexvision(video: dict, hls_path: str):
    """Push the HLS stream URL back to NexVision IPTV after transcoding."""
    conn = vod_get_db()
    settings = {r['key']: r['value'] for r in conn.execute("SELECT key, value FROM settings").fetchall()}
    conn.close()

    if settings.get('auto_push_nexvision', '1') != '1':
        return
    if not video.get('nexvision_id'):
        return

    nx_url   = settings.get('nexvision_url', VOD_NEXVISION_URL).rstrip('/')
    nx_token = settings.get('nexvision_token', VOD_NEXVISION_TOKEN)
    if not nx_token:
        vod_log.warning("[nexvision] No token — skipping push")
        return

    my_host  = _vod_get_my_url()
    full_hls = my_host + hls_path

    payload = json.dumps({
        'stream_url': full_hls,
        'poster':     my_host + video.get('thumbnail', '') if video.get('thumbnail') else '',
    }).encode()

    req = urllib.request.Request(
        f"{nx_url}/api/vod/{video['nexvision_id']}",
        data=payload,
        headers={
            'Content-Type':  'application/json',
            'Authorization': f"Bearer {nx_token}",
        },
        method='PUT'
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            vod_log.info(f"[nexvision] Pushed stream_url for movie {video['nexvision_id']} -> {resp.status}")
    except Exception as e:
        vod_log.warning(f"[nexvision] Push failed: {e}")


def _vod_get_my_url():
    """Return our own base URL for generating absolute HLS links."""
    try:
        return request.host_url.rstrip('/')
    except RuntimeError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return f'http://{ip}:{_VOD_PORT}'
    except Exception:
        return f'http://localhost:{_VOD_PORT}'

# ─── Video download from URL ──────────────────────────────────────────────────

def download_video(url: str, video_id: str, filename: str) -> Path:
    """Download a remote video to the videos directory. Updates progress."""
    dest = VIDEOS_DIR / f"{video_id}_{filename}"
    with _transcode_lock:
        _transcode_jobs[video_id] = {'status': 'downloading', 'progress': 0, 'error': None}

    req = urllib.request.Request(url, headers={'User-Agent': 'NexVision-VOD/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            chunk = 65536
            with open(dest, 'wb') as f:
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    f.write(data)
                    downloaded += len(data)
                    if total:
                        pct = min(99, int(downloaded / total * 100))
                        with _transcode_lock:
                            if video_id in _transcode_jobs:
                                _transcode_jobs[video_id]['progress'] = pct
        vod_log.info(f"[download] {video_id} complete -> {dest}")
        return dest
    except Exception as e:
        with _transcode_lock:
            if video_id in _transcode_jobs:
                _transcode_jobs[video_id].update({'status': 'error', 'error': str(e)})
        conn = vod_get_db()
        conn.execute("UPDATE videos SET status='error', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (video_id,))
        conn.commit(); conn.close()
        raise

# ─── Background ingest pipeline ───────────────────────────────────────────────

def _run_ingest(video_id: str, source_path: Path, qualities: list,
                title: str, nexvision_id: int = 0, metadata: dict = None):
    """Full ingest pipeline: probe -> thumbnail -> transcode -> push to NexVision."""
    metadata = metadata or {}
    try:
        vod_log.info(f"[ingest] {video_id} probing...")
        info = probe_video(source_path)
        conn = vod_get_db()
        conn.execute("""
            UPDATE videos SET
              filesize=?, duration=?, width=?, height=?, fps=?,
              video_codec=?, audio_codec=?, bitrate=?,
              status='probed', updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (
            info.get('filesize', source_path.stat().st_size),
            info.get('duration', 0), info.get('width', 0),
            info.get('height', 0), info.get('fps', 0),
            info.get('video_codec', ''), info.get('audio_codec', ''),
            info.get('bitrate', 0), video_id
        ))
        conn.commit()

        thumb = generate_thumbnail(source_path, video_id, info.get('duration', 0))
        if thumb:
            conn.execute("UPDATE videos SET thumbnail=? WHERE id=?", (thumb, video_id))
            conn.commit()

        transcode_video(
            video_id, source_path, qualities,
            info.get('width', 0), info.get('height', 0), info.get('duration', 0)
        )
        conn.close()

    except Exception as e:
        vod_log.error(f"[ingest] {video_id} error: {e}", exc_info=True)
        conn = vod_get_db()
        conn.execute("UPDATE videos SET status='error', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (video_id,))
        conn.commit(); conn.close()
        with _transcode_lock:
            if video_id not in _transcode_jobs:
                _transcode_jobs[video_id] = {}
            _transcode_jobs[video_id].update({'status': 'error', 'error': str(e)})


def _run_url_ingest(video_id: str, url: str, qualities: list,
                    title: str, nexvision_id: int = 0):
    """Download from URL then run the full ingest pipeline."""
    try:
        url_path  = url.split('?')[0]
        raw_name  = url_path.rstrip('/').split('/')[-1] or 'video.mp4'
        safe_name = re.sub(r'[^\w\-.]', '_', raw_name)
        if not any(safe_name.lower().endswith(ext) for ext in ALLOWED_VIDEO_EXTS):
            safe_name += '.mp4'

        dest = download_video(url, video_id, safe_name)
        conn = vod_get_db()
        conn.execute("UPDATE videos SET filename=?, original_url=? WHERE id=?",
                     (dest.name, url, video_id))
        conn.commit(); conn.close()
        _run_ingest(video_id, dest, qualities, title, nexvision_id)
    except Exception as e:
        vod_log.error(f"[url_ingest] {video_id}: {e}")

# ─── VOD Static file serving ──────────────────────────────────────────────────

@app.route('/vod/hls/<video_id>/master.m3u8')
def vod_serve_master(video_id):
    path = HLS_DIR / video_id / 'master.m3u8'
    if not path.exists():
        abort(404)
    _vod_track_session(video_id, 'master')
    if os.getenv('USE_X_ACCEL', '0') == '1':
        # Nginx serves the file directly — Python never reads video bytes
        resp = make_response()
        resp.headers['X-Accel-Redirect']         = f'/internal/vod/hls/{video_id}/master.m3u8'
        resp.headers['Content-Type']             = 'application/vnd.apple.mpegurl'
        resp.headers['Cache-Control']            = 'no-cache'
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    resp = send_from_directory(str(HLS_DIR / video_id), 'master.m3u8')
    resp.headers['Content-Type']  = 'application/vnd.apple.mpegurl'
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/vod/hls/<video_id>/<quality>/index.m3u8')
def vod_serve_playlist(video_id, quality):
    path = HLS_DIR / video_id / quality / 'index.m3u8'
    if not path.exists():
        abort(404)
    _vod_track_session(video_id, quality)
    if os.getenv('USE_X_ACCEL', '0') == '1':
        resp = make_response()
        resp.headers['X-Accel-Redirect']         = f'/internal/vod/hls/{video_id}/{quality}/index.m3u8'
        resp.headers['Content-Type']             = 'application/vnd.apple.mpegurl'
        resp.headers['Cache-Control']            = 'no-cache'
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    resp = send_from_directory(str(HLS_DIR / video_id / quality), 'index.m3u8')
    resp.headers['Content-Type']  = 'application/vnd.apple.mpegurl'
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/vod/hls/<video_id>/<quality>/<segment>')
def vod_serve_segment(video_id, quality, segment):
    if not segment.endswith('.ts'):
        abort(404)
    seg_path = HLS_DIR / video_id / quality / segment
    if not seg_path.exists():
        abort(404)
    if segment.endswith('00000.ts') or segment.endswith('00001.ts'):
        conn = vod_get_db()
        conn.execute("UPDATE videos SET views=views+1 WHERE id=?", (video_id,))
        conn.commit(); conn.close()
    if os.getenv('USE_X_ACCEL', '0') == '1':
        # Critical path: Nginx serves .ts segments at kernel level (sendfile)
        # This is how 500 simultaneous streams work without killing the CPU
        resp = make_response()
        resp.headers['X-Accel-Redirect']            = f'/internal/vod/hls/{video_id}/{quality}/{segment}'
        resp.headers['Content-Type']                = 'video/mp2t'
        resp.headers['Cache-Control']               = 'public, max-age=3600'
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Accept-Ranges']               = 'bytes'
        return resp
    resp = send_from_directory(str(HLS_DIR / video_id / quality), segment)
    resp.headers['Content-Type']  = 'video/mp2t'
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Accept-Ranges']               = 'bytes'
    return resp


@app.route('/vod/thumbnails/<filename>')
def vod_serve_thumbnail(filename):
    return send_from_directory(str(THUMBS_DIR), filename)


@app.route('/vod/uploads/<filename>')
def vod_serve_upload(filename):
    return send_from_directory(str(UPLOADS_DIR), filename)


def _detect_device_type(ua: str) -> str:
    """Classify a User-Agent string into tv / mobile / tablet / browser."""
    u = ua.lower()
    if any(k in u for k in ('tizen', 'webos', 'hbbtv', 'smart-tv', 'smarttv',
                             'googletv', 'android tv', 'firetv', 'fire tv',
                             'netcast', 'viera', 'bravia', 'philipstv')):
        return 'tv'
    if any(k in u for k in ('iphone', 'windows phone', 'blackberry')):
        return 'mobile'
    if 'android' in u:
        return 'mobile' if 'mobile' in u else 'tablet'
    if 'ipad' in u:
        return 'tablet'
    return 'browser'


def _vod_track_session(video_id: str, quality: str):
    """Track a stream session (best-effort, non-blocking)."""
    try:
        sid = request.cookies.get('vod_sid') or request.headers.get('X-Session-Id') or str(uuid.uuid4())
        ip  = request.remote_addr or ''
        ua  = request.headers.get('User-Agent', '')[:200]
        device_type = _detect_device_type(ua)
        conn = vod_get_db()
        conn.execute("""
            INSERT INTO stream_sessions (id, video_id, ip, user_agent, quality, device_type)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET last_seen=CURRENT_TIMESTAMP
        """, (sid, video_id, ip, ua, quality, device_type))
        conn.commit(); conn.close()
    except Exception:
        pass

# ─── VOD API: Videos ──────────────────────────────────────────────────────────

@app.route('/vod/api/videos', methods=['GET'])
def vod_list_videos():
    status   = request.args.get('status')
    category = request.args.get('category')
    search   = request.args.get('search', '').strip()
    limit    = _safe_int(request.args.get('limit'), 100)
    offset   = _safe_int(request.args.get('offset'), 0)

    wheres, params = [], []
    if status:
        wheres.append('status=?'); params.append(status)
    if category:
        wheres.append('category=?'); params.append(category)
    if search:
        wheres.append('(title LIKE ? OR description LIKE ? OR tags LIKE ?)')
        params += [f'%{search}%', f'%{search}%', f'%{search}%']

    where_sql = ('WHERE ' + ' AND '.join(wheres)) if wheres else ''
    conn = vod_get_db()
    rows = conn.execute(
        f"SELECT * FROM videos {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset]
    ).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM videos {where_sql}", params).fetchone()[0]
    conn.close()

    host = _vod_get_my_url()
    videos = []
    for r in rows:
        v = dict(r)
        v['qualities']     = json.loads(v.get('qualities') or '[]')
        v['hls_url']       = host + v['hls_path'] if v.get('hls_path') else ''
        v['thumbnail_url'] = host + v['thumbnail'] if v.get('thumbnail') else ''
        v['stream_urls']   = _vod_build_stream_urls(host, v['id'], v['qualities'])
        videos.append(v)

    return jsonify({'videos': videos, 'total': total, 'limit': limit, 'offset': offset})


@app.route('/vod/api/videos/<vid>', methods=['GET'])
def vod_get_video(vid):
    conn = vod_get_db()
    row = conn.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    host = _vod_get_my_url()
    v = dict(row)
    v['qualities']     = json.loads(v.get('qualities') or '[]')
    v['hls_url']       = host + v['hls_path'] if v.get('hls_path') else ''
    v['thumbnail_url'] = host + v['thumbnail'] if v.get('thumbnail') else ''
    v['stream_urls']   = _vod_build_stream_urls(host, v['id'], v['qualities'])
    with _transcode_lock:
        job = _transcode_jobs.get(vid)
        if job:
            v['job'] = {k: val for k, val in job.items() if k != 'pid'}
    return jsonify(v)


def _vod_build_stream_urls(host: str, video_id: str, qualities: list) -> dict:
    """Build a dict of quality -> absolute HLS URL."""
    urls = {}
    if len(qualities) > 1:
        urls['master'] = f"{host}/vod/hls/{video_id}/master.m3u8"
    for q in qualities:
        urls[q] = f"{host}/vod/hls/{video_id}/{q}/index.m3u8"
    return urls


@app.route('/vod/api/videos/<vid>', methods=['PUT'])
@require_api_key
def vod_update_video(vid):
    d = request.json or {}
    conn = vod_get_db()
    conn.execute("""
        UPDATE videos SET title=?, description=?, category=?, tags=?,
          year=?, language=?, rating=?, nexvision_id=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (
        d.get('title', ''), d.get('description', ''), d.get('category', ''),
        d.get('tags', ''), d.get('year', 0), d.get('language', 'en'),
        d.get('rating', 0), d.get('nexvision_id', 0), vid
    ))
    conn.commit()
    row = conn.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(row))


@app.route('/vod/api/videos/<vid>', methods=['DELETE'])
@require_api_key
def vod_delete_video(vid):
    conn = vod_get_db()
    row  = conn.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    _vod_delete_video_files(vid, row['filename'])
    conn.execute("DELETE FROM transcode_log   WHERE video_id=?", (vid,))
    conn.execute("DELETE FROM stream_sessions WHERE video_id=?", (vid,))
    conn.execute("DELETE FROM videos WHERE id=?", (vid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


def _vod_delete_video_files(video_id: str, filename: str):
    """Remove original file, HLS segments, and thumbnail."""
    import shutil
    for vdir in [VIDEOS_DIR, UPLOADS_DIR]:
        p = vdir / filename
        if p.exists():
            try: p.unlink()
            except Exception: pass
    hls_dir = HLS_DIR / video_id
    if hls_dir.exists():
        try: shutil.rmtree(str(hls_dir))
        except Exception: pass
    thumb = THUMBS_DIR / f"{video_id}.jpg"
    if thumb.exists():
        try: thumb.unlink()
        except Exception: pass

# ─── VOD API: Upload ──────────────────────────────────────────────────────────

@app.route('/vod/api/upload', methods=['POST'])
@require_api_key
def vod_upload_video():
    if 'file' not in request.files:
        return jsonify({'error': 'No file field in request'}), 400
    f = request.files['file']
    if not f or not f.filename:
        return jsonify({'error': 'Empty file'}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        return jsonify({'error': f'Unsupported format {ext}. Use: {", ".join(ALLOWED_VIDEO_EXTS)}'}), 400

    video_id  = str(uuid.uuid4())
    safe_name = re.sub(r'[^\w\-.]', '_', f.filename)
    dest_path = VIDEOS_DIR / f"{video_id}_{safe_name}"

    f.save(str(dest_path))
    vod_log.info(f"[upload] Saved {dest_path} ({dest_path.stat().st_size} bytes)")

    title     = request.form.get('title', Path(f.filename).stem.replace('_', ' ').replace('-', ' ').title())
    desc      = request.form.get('description', '')
    cat       = request.form.get('category', '')
    tags      = request.form.get('tags', '')
    nx_id     = _safe_int(request.form.get('nexvision_id'), 0)
    q_raw     = request.form.get('qualities', ','.join(DEFAULT_QUALITIES))
    qualities = [q.strip() for q in q_raw.split(',') if q.strip() and get_quality_profile(q.strip())]
    if not qualities:
        qualities = list(DEFAULT_QUALITIES)

    conn = vod_get_db()
    conn.execute("""
        INSERT INTO videos (id, title, description, filename, category, tags, nexvision_id,
                            filesize, status)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (video_id, title, desc, dest_path.name, cat, tags, nx_id,
          dest_path.stat().st_size, 'uploading'))
    conn.commit(); conn.close()

    # Guard: check FFmpeg is available before starting transcode
    _ff_ok2, _, _ff_err2 = _check_ffmpeg_available()
    if not _ff_ok2:
        return jsonify({'error': 'FFmpeg not found on this server. ' + _ff_err2.splitlines()[0]}), 500

    t = threading.Thread(
        target=_run_ingest,
        args=(video_id, dest_path, qualities, title, nx_id),
        daemon=True
    )
    t.start()

    host = _vod_get_my_url()
    return jsonify({
        'ok':           True,
        'video_id':     video_id,
        'title':        title,
        'status':       'uploading',
        'progress_url': f'{host}/vod/api/videos/{video_id}/progress',
        'hls_url':      f'{host}/vod/hls/{video_id}/master.m3u8',
    }), 202

# ─── VOD API: Import from URL ─────────────────────────────────────────────────

@app.route('/vod/api/import', methods=['POST'])
@require_api_key
def vod_import_from_url():
    d = request.json or {}
    url = d.get('url', '').strip()
    if not url:
        return jsonify({'error': 'url is required'}), 400

    video_id  = str(uuid.uuid4())
    title     = d.get('title', url.rstrip('/').split('/')[-1].split('.')[0].title())
    desc      = d.get('description', '')
    cat       = d.get('category', '')
    tags      = d.get('tags', '')
    nx_id     = int(d.get('nexvision_id', 0) or 0)
    qualities = d.get('qualities', DEFAULT_QUALITIES)
    if isinstance(qualities, str):
        qualities = [q.strip() for q in qualities.split(',')]
    qualities = [q for q in qualities if get_quality_profile(q)]
    if not qualities:
        qualities = list(DEFAULT_QUALITIES)

    conn = vod_get_db()
    conn.execute("""
        INSERT INTO videos (id, title, description, filename, original_url, category, tags,
                            nexvision_id, status)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (video_id, title, desc, 'pending_download', url, cat, tags, nx_id, 'queued'))
    conn.commit(); conn.close()

    _ff_ok3, _, _ff_err3 = _check_ffmpeg_available()
    if not _ff_ok3:
        return jsonify({'error': f'FFmpeg not found. Install FFmpeg and restart. {_ff_err3.splitlines()[0]}'}), 500

    t = threading.Thread(
        target=_run_url_ingest,
        args=(video_id, url, qualities, title, nx_id),
        daemon=True
    )
    t.start()

    host = _vod_get_my_url()
    return jsonify({
        'ok':           True,
        'video_id':     video_id,
        'title':        title,
        'status':       'queued',
        'progress_url': f'{host}/vod/api/videos/{video_id}/progress',
        'hls_url':      f'{host}/vod/hls/{video_id}/master.m3u8',
    }), 202

# ─── VOD API: Progress ────────────────────────────────────────────────────────

@app.route('/vod/api/videos/<vid>/progress', methods=['GET'])
def vod_get_progress(vid):
    conn = vod_get_db()
    row  = conn.execute("SELECT status, qualities FROM videos WHERE id=?", (vid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    db_status    = row['status']
    db_qualities = json.loads(row['qualities'] or '[]')

    with _transcode_lock:
        job = _transcode_jobs.get(vid, {})

    return jsonify({
        'video_id':         vid,
        'status':           job.get('status', db_status),
        'progress':         job.get('progress', 100 if db_status == 'ready' else 0),
        'quality_progress': job.get('quality_progress', {}),
        'qualities_done':   db_qualities,
        'error':            job.get('error'),
        'started_at':       job.get('started_at'),
    })


@app.route('/vod/api/videos/<vid>/progress/stream', methods=['GET'])
def vod_progress_stream(vid):
    """Server-Sent Events stream for live transcode progress."""
    def generate():
        for _ in range(600):
            conn = vod_get_db()
            row  = conn.execute("SELECT status, qualities FROM videos WHERE id=?", (vid,)).fetchone()
            conn.close()
            if not row:
                break

            with _transcode_lock:
                job = _transcode_jobs.get(vid, {})

            db_status = row['status']
            data = {
                'video_id':         vid,
                'status':           job.get('status', db_status),
                'progress':         job.get('progress', 100 if db_status == 'ready' else 0),
                'quality_progress': job.get('quality_progress', {}),
                'qualities_done':   json.loads(row['qualities'] or '[]'),
                'error':            job.get('error'),
            }
            yield f"data: {json.dumps(data)}\n\n"

            if data['status'] in ('ready', 'error'):
                break
            time.sleep(1)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':               'no-cache',
            'X-Accel-Buffering':           'no',
            'Access-Control-Allow-Origin': '*',
        }
    )

# ─── VOD API: Retranscode ─────────────────────────────────────────────────────

@app.route('/vod/api/videos/<vid>/retranscode', methods=['POST'])
@require_api_key
def vod_retranscode(vid):
    conn  = vod_get_db()
    row   = conn.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    d = request.json or {}
    qualities = d.get('qualities', DEFAULT_QUALITIES)
    if isinstance(qualities, str):
        qualities = [q.strip() for q in qualities.split(',')]
    qualities = [q for q in qualities if get_quality_profile(q)]

    src = VIDEOS_DIR / row['filename']
    if not src.exists():
        src = UPLOADS_DIR / row['filename']
    if not src.exists():
        return jsonify({'error': 'Original file not found on disk'}), 400

    t = threading.Thread(
        target=transcode_video,
        args=(vid, src, qualities, row['width'], row['height'], row['duration']),
        daemon=True
    )
    t.start()

    return jsonify({'ok': True, 'video_id': vid, 'qualities': qualities})

# ─── VOD API: Thumbnail regeneration ─────────────────────────────────────────

@app.route('/vod/api/videos/<vid>/thumbnail', methods=['POST'])
@require_api_key
def vod_regen_thumbnail(vid):
    conn = vod_get_db()
    row  = conn.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404

    src = VIDEOS_DIR / row['filename']
    if not src.exists():
        src = UPLOADS_DIR / row['filename']
    if not src.exists():
        return jsonify({'error': 'Original file not found'}), 400

    d = request.json or {}
    at = float(d.get('at', row['duration'] * THUMB_TIME_PERCENT / 100))
    at = max(0.5, min(at, row['duration'] - 1))

    thumb_file = THUMBS_DIR / f"{vid}.jpg"
    cmd = [
        FFMPEG_BIN, '-y', '-ss', str(at), '-i', str(src),
        '-vframes', '1', '-vf', 'scale=640:-1', '-q:v', '4', str(thumb_file)
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
        if thumb_file.exists():
            thumb_url = f'/vod/thumbnails/{vid}.jpg'
            conn = vod_get_db()
            conn.execute("UPDATE videos SET thumbnail=? WHERE id=?", (thumb_url, vid))
            conn.commit(); conn.close()
            return jsonify({'ok': True, 'thumbnail_url': _vod_get_my_url() + thumb_url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'error': 'Thumbnail generation failed'}), 500

# ─── VOD API: Analytics ───────────────────────────────────────────────────────

@app.route('/vod/api/analytics', methods=['GET'])
def vod_analytics():
    conn  = vod_get_db()
    stats = {
        'total_videos':    conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0],
        'ready_videos':    conn.execute("SELECT COUNT(*) FROM videos WHERE status='ready'").fetchone()[0],
        'pending_videos':  conn.execute("SELECT COUNT(*) FROM videos WHERE status NOT IN ('ready','error')").fetchone()[0],
        'error_videos':    conn.execute("SELECT COUNT(*) FROM videos WHERE status='error'").fetchone()[0],
        'total_views':     conn.execute("SELECT COALESCE(SUM(views),0) FROM videos").fetchone()[0],
        'total_duration':  conn.execute("SELECT COALESCE(SUM(duration),0) FROM videos WHERE status='ready'").fetchone()[0],
        'total_size_gb':   round(conn.execute("SELECT COALESCE(SUM(filesize),0) FROM videos").fetchone()[0] / 1e9, 2),
        'active_sessions': conn.execute(
            "SELECT COUNT(DISTINCT id) FROM stream_sessions WHERE last_seen >= datetime('now','-5 minutes')"
        ).fetchone()[0],
        'top_videos': [dict(r) for r in conn.execute(
            "SELECT id, title, views, status FROM videos ORDER BY views DESC LIMIT 10"
        ).fetchall()],
        'categories': [dict(r) for r in conn.execute(
            "SELECT category, COUNT(*) as count FROM videos WHERE category!='' GROUP BY category ORDER BY count DESC"
        ).fetchall()],
        'by_device': [dict(r) for r in conn.execute("""
            SELECT COALESCE(device_type, 'browser') AS device_type,
                   COUNT(DISTINCT id)               AS sessions
            FROM stream_sessions
            WHERE last_seen >= datetime('now', '-30 days')
            GROUP BY device_type
            ORDER BY sessions DESC
        """).fetchall()],
    }
    conn.close()
    return jsonify(stats)

# ─── VOD API: Jobs ────────────────────────────────────────────────────────────

@app.route('/vod/api/jobs', methods=['GET'])
def vod_list_jobs():
    with _transcode_lock:
        jobs = [
            {'video_id': vid, **{k: v for k, v in job.items() if k != 'pid'}}
            for vid, job in _transcode_jobs.items()
        ]
    conn = vod_get_db()
    for job in jobs:
        row = conn.execute("SELECT title FROM videos WHERE id=?", (job['video_id'],)).fetchone()
        job['title'] = row['title'] if row else '?'
    conn.close()
    return jsonify(jobs)


@app.route('/vod/api/jobs/<vid>/cancel', methods=['POST'])
@require_api_key
def vod_cancel_job(vid):
    with _transcode_lock:
        job = _transcode_jobs.get(vid)
        if not job:
            return jsonify({'error': 'No active job for this video'}), 404
        pid = job.get('pid')
        if pid:
            try:
                import signal
                os.kill(pid, signal.SIGTERM)
                job['status'] = 'cancelled'
                job['error']  = 'Cancelled by user'
            except ProcessLookupError:
                pass
    conn = vod_get_db()
    conn.execute("UPDATE videos SET status='error', updated_at=CURRENT_TIMESTAMP WHERE id=?", (vid,))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ─── VOD API: Auth proxy (get IPTV JWT without leaving the server) ────────────

@app.route('/vod/api/auth/token', methods=['POST'])
def vod_auth_token():
    data = request.json or {}
    pw = hashlib.sha256(data.get('password', '').encode()).hexdigest()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
                        (data.get('username', ''), pw)).fetchone()
    conn.close()
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    token = jwt.encode({
        'id': user['id'], 'username': user['username'], 'role': user['role'],
        'exp': datetime.utcnow() + timedelta(hours=24)
    }, app.config['SECRET_KEY'], algorithm='HS256')
    return jsonify({'token': token})


# ─── VOD API: Settings ────────────────────────────────────────────────────────

@app.route('/vod/api/settings', methods=['GET'])
def vod_get_settings():
    conn = vod_get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return jsonify({r['key']: r['value'] for r in rows})


@app.route('/vod/api/settings', methods=['POST'])
@require_api_key
def vod_save_settings():
    d = request.json or {}
    conn = vod_get_db()
    for k, v in d.items():
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (k, str(v)))
    conn.commit(); conn.close()
    return jsonify({'ok': True})

# ─── VOD API: Manual NexVision push ──────────────────────────────────────────

@app.route('/vod/api/videos/<vid>/push-nexvision', methods=['POST'])
@require_api_key
def vod_push_nexvision(vid):
    conn = vod_get_db()
    row  = conn.execute("SELECT * FROM videos WHERE id=?", (vid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    if dict(row)['status'] != 'ready':
        return jsonify({'error': 'Video is not ready yet'}), 400
    _vod_push_to_nexvision(dict(row), dict(row)['hls_path'])
    return jsonify({'ok': True, 'nexvision_id': dict(row)['nexvision_id']})

# ─── VOD API: Health ──────────────────────────────────────────────────────────

@app.route('/vod/api/health', methods=['GET'])
def vod_health():
    host = _vod_get_my_url()
    return jsonify({
        'status':  'ok',
        'service': 'NexVision VOD Stream Server',
        'version': APP_VERSION,
        'host':    host,
        'api':     host + '/vod/api/',
        'ffmpeg':  _vod_check_ffmpeg(),
        'disk':    _vod_disk_info(),
        'uptime':  _vod_uptime(),
    })


def _vod_check_ffmpeg() -> dict:
    try:
        out = subprocess.check_output([FFMPEG_BIN, '-version'], stderr=subprocess.STDOUT, timeout=5)
        line = out.decode().splitlines()[0]
        return {'ok': True, 'version': line}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _vod_disk_info() -> dict:
    try:
        import shutil
        total, used, free = shutil.disk_usage(str(VOD_BASE_DIR))
        return {
            'total_gb': round(total / 1e9, 1),
            'free_gb':  round(free  / 1e9, 1),
            'used_pct': round(used  / total * 100, 1),
        }
    except Exception:
        return {}


_vod_start_time = time.time()


def _vod_uptime() -> str:
    secs = int(time.time() - _vod_start_time)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    return f"{h}h {m}m {s}s"

# ─── VOD Management Dashboard ─────────────────────────────────────────────────

def _vod_embedded_nav(active: str) -> str:
    """Compact VOD/Admin/Storage tab bar injected when rendered inside admin iframe."""
    tabs = [
        ('vod',     '/vod/?embedded=1&inframe=1',       'VOD'),
        ('admin',   '/vod/admin?embedded=1',             'Admin'),
        ('storage', '/vod/admin/storage?embedded=1',     'Storage'),
    ]
    parts = []
    for key, href, label in tabs:
        if key == active:
            s = ('padding:6px 14px;border-radius:6px;text-decoration:none;'
                 'background:rgba(201,168,76,.15);border:1px solid #c9a84c;'
                 'color:#c9a84c;font-size:12px;font-weight:600')
        else:
            s = ('padding:6px 14px;border-radius:6px;text-decoration:none;'
                 'background:#131320;border:1px solid rgba(255,255,255,.12);'
                 'color:rgba(240,240,248,.6);font-size:12px;font-weight:600')
        parts.append(f'<a href="{href}" style="{s}">{label}</a>')
    return (
        '<div style="background:#0d0d14;border-bottom:1px solid rgba(255,255,255,.06);'
        'padding:8px 16px;display:flex;gap:8px;align-items:center">'
        + ''.join(parts)
        + '</div>'
    )


@app.route('/vod/')
@app.route('/vod')
def vod_dashboard():
    inframe = request.args.get('inframe') == '1'
    embedded = (
        request.args.get('embedded') == '1'
        or inframe
        or request.headers.get('Sec-Fetch-Dest', '').lower() == 'iframe'
    )
    html = _render_vod_ui()
    if embedded:
        nav = '' if inframe else _vod_embedded_nav('vod')
        html = re.sub(
            r'<header style="display:flex;align-items:center;gap:20px">.*?</header>\s*',
            nav,
            html,
            flags=re.DOTALL
        )
    resp = make_response(html)
    resp.headers['Content-Type']  = 'text/html; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma']        = 'no-cache'
    resp.headers['Expires']       = '0'
    return resp


def _render_vod_ui() -> str:
    """Single-page VOD management dashboard."""
    _html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NexVision VOD</title>
<script>
(function () {
  if (new URLSearchParams(window.location.search).get('embedded') === '1') {
    document.documentElement.classList.add('embedded-mode');
  }
})();
</script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#06060a;--bg2:#0d0d14;--bg3:#131320;--bg4:#1a1a2e;--gold:#c9a84c;--gold2:#e8c56a;--gold3:rgba(201,168,76,.15);--white:#f0f0f8;--muted:rgba(240,240,248,.35);--dimmed:rgba(240,240,248,.6);--border:rgba(255,255,255,.06);--border2:rgba(255,255,255,.12);--red:#e84855;--green:#52d98e;--blue:#4a9eff}
body{background:var(--bg);color:var(--white);font-family:system-ui,sans-serif;min-height:100vh}
header{background:var(--bg2);border-bottom:1px solid var(--border);padding:16px 32px;display:flex;align-items:center;gap:16px}
.logo{font-size:20px;font-weight:700;color:var(--gold);letter-spacing:4px;text-transform:uppercase;display:flex;align-items:center;gap:10px;min-height:32px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);padding:10px 16px;border-radius:14px}
.logo span{color:var(--white)}
.logo img{display:block;max-height:32px;max-width:180px;width:auto;object-fit:contain}
.hdr-badge{font-size:10px;background:var(--gold3);border:1px solid var(--gold);color:var(--gold);padding:2px 10px;border-radius:20px;letter-spacing:1px}
.container{max-width:1200px;margin:0 auto;padding:32px}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:16px;margin-bottom:32px}
.stat-card{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:20px}
.stat-val{font-size:32px;font-weight:700;color:var(--gold);margin-bottom:4px}
.stat-lbl{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px}
.panel{background:var(--bg2);border:1px solid var(--border);border-radius:14px;margin-bottom:24px;overflow:hidden}
.panel-hdr{padding:18px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.panel-title{font-size:15px;font-weight:600;color:var(--white)}
.panel-body{padding:24px}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
.form-row.full{grid-template-columns:1fr}
.form-group label{display:block;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
input,select,textarea{width:100%;background:var(--bg3);border:1px solid var(--border2);border-radius:8px;padding:10px 14px;color:var(--white);font-size:13px;outline:none;transition:.15s;font-family:inherit}
input:focus,select:focus,textarea:focus{border-color:var(--gold)}
select option{background:var(--bg3)}
textarea{resize:vertical;min-height:80px}
.btn{padding:10px 22px;border-radius:8px;border:none;cursor:pointer;font-size:13px;font-weight:600;transition:.15s;display:inline-flex;align-items:center;gap:8px}
.btn-gold{background:var(--gold);color:#000}
.btn-gold:hover{background:var(--gold2)}
.btn-ghost{background:transparent;border:1px solid var(--border2);color:var(--dimmed)}
.btn-ghost:hover{border-color:var(--border2);color:var(--white)}
.btn-red{background:rgba(232,72,85,.15);border:1px solid rgba(232,72,85,.3);color:var(--red)}
.btn-sm{padding:5px 12px;font-size:11px;border-radius:6px}
.video-table{width:100%;border-collapse:collapse}
.video-table th{text-align:left;font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;padding:8px 12px;border-bottom:1px solid var(--border)}
.video-table td{padding:12px;border-bottom:1px solid var(--border);font-size:13px;vertical-align:middle}
.video-table tr:last-child td{border-bottom:none}
.video-table tr:hover td{background:rgba(255,255,255,.02)}
.status-badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:600;letter-spacing:.5px;text-transform:uppercase}
.status-ready{background:rgba(82,217,142,.12);color:var(--green)}
.status-error{background:rgba(232,72,85,.12);color:var(--red)}
.status-transcoding,.status-uploading,.status-downloading,.status-queued,.status-probed{background:rgba(74,158,255,.12);color:var(--blue)}
.progress-bar{width:100%;height:5px;background:var(--bg4);border-radius:3px;overflow:hidden;margin-top:6px}
.progress-fill{height:100%;background:var(--gold);border-radius:3px;transition:width .5s}
.thumb{width:64px;height:40px;object-fit:cover;border-radius:6px;background:var(--bg4)}
.copy-btn{cursor:pointer;font-size:10px;color:var(--gold);border:1px solid rgba(201,168,76,.3);background:rgba(201,168,76,.08);padding:2px 8px;border-radius:4px}
.copy-btn:hover{background:rgba(201,168,76,.15)}
.alert{padding:12px 16px;border-radius:8px;font-size:13px;margin-bottom:16px}
.alert-success{background:rgba(82,217,142,.1);border:1px solid rgba(82,217,142,.3);color:var(--green)}
.alert-error{background:rgba(232,72,85,.1);border:1px solid rgba(232,72,85,.3);color:var(--red)}
.alert-info{background:rgba(74,158,255,.1);border:1px solid rgba(74,158,255,.3);color:var(--blue)}
.tab-bar{display:flex;gap:2px;margin-bottom:24px;background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:4px;width:fit-content}
.tab{padding:8px 20px;border-radius:7px;cursor:pointer;font-size:13px;color:var(--muted);transition:.15s;border:none;background:transparent}
.tab.active{background:var(--bg3);color:var(--white)}
.empty{text-align:center;padding:48px;color:var(--muted);font-size:14px}
.empty-icon{font-size:40px;margin-bottom:12px}
.hlsurl{font-family:monospace;font-size:11px;color:var(--dimmed);word-break:break-all}
.topnav{display:flex;gap:10px;flex-wrap:wrap;margin-left:16px;align-items:center;flex:1}
.topnav a{padding:8px 14px;border-radius:8px;text-decoration:none;color:var(--dimmed);background:var(--bg3);border:1px solid var(--border2);font-size:13px;font-weight:600;transition:.15s}
.topnav a:hover{color:var(--white);border-color:var(--gold)}
.topnav a.active{background:var(--gold3);border-color:var(--gold);color:var(--gold)}
.hdr-right{display:flex;gap:10px;margin-left:auto;align-items:center}
.theme-toggle{padding:8px 12px;border-radius:8px;border:1px solid var(--border2);background:var(--bg3);color:var(--dimmed);font-size:12px;font-weight:600;cursor:pointer;transition:.15s;white-space:nowrap;display:flex;align-items:center;gap:6px}
.theme-toggle:hover{color:var(--white);border-color:var(--gold)}
html.embedded-mode header{display:none}
html.embedded-mode .container{max-width:none;padding:20px}
body[data-theme='light']{--bg:#f4f6fb;--bg2:#ffffff;--bg3:#eef2fb;--bg4:#dfe5f2;--gold:#9a7220;--gold2:#b78929;--gold3:rgba(154,114,32,.12);--white:#1a2233;--muted:rgba(26,34,51,.45);--dimmed:rgba(26,34,51,.7);--border:rgba(12,22,38,.08);--border2:rgba(12,22,38,.16);--red:#c23a48;--green:#2f8e5f;--blue:#2a74c9}
</style>
</head>
<body>
<header style="display:flex;align-items:center;gap:20px">
  <nav class="topnav">
    <a href="/vod" class="active">VOD</a>
    <a href="/vod/admin">Admin</a>
    <a href="/vod/admin/storage">Storage</a>
    <div class="hdr-right">
      <button id="theme-toggle" class="theme-toggle" onclick="toggleTheme()" title="Toggle theme"><span id="theme-icon">🌙</span> Dark</button>
      <div style="font-size:12px;color:var(--muted)" id="hdr-status">Loading...</div>
    </div>
  </nav>
</header>

<div class="container">
  <div class="stats-grid" id="stats-grid">
    <div class="stat-card"><div class="stat-val" id="st-total">-</div><div class="stat-lbl">Total Videos</div></div>
    <div class="stat-card"><div class="stat-val" id="st-ready">-</div><div class="stat-lbl">Ready to Stream</div></div>
    <div class="stat-card"><div class="stat-val" id="st-views">-</div><div class="stat-lbl">Total Views</div></div>
    <div class="stat-card"><div class="stat-val" id="st-active">-</div><div class="stat-lbl">Processing</div></div>
    <div class="stat-card"><div class="stat-val" id="st-size">-</div><div class="stat-lbl">Disk Used (GB)</div></div>
    <div class="stat-card"><div class="stat-val" id="st-sessions">-</div><div class="stat-lbl">Live Sessions</div></div>
  </div>

  <div class="tab-bar">
    <button class="tab active" onclick="switchTab('videos')">Videos</button>
    <button class="tab" onclick="switchTab('upload')">Upload</button>
    <button class="tab" onclick="switchTab('import')">Import URL</button>
    <button class="tab" onclick="switchTab('jobs')">Jobs</button>
    <button class="tab" onclick="switchTab('settings')">Settings</button>
  </div>

  <div id="tab-videos">
    <div class="panel">
      <div class="panel-hdr">
        <div class="panel-title">Video Library</div>
        <div style="display:flex;gap:8px">
          <input id="search-input" placeholder="Search..." style="width:200px;padding:6px 12px" oninput="debounceSearch()">
          <button class="btn btn-ghost btn-sm" onclick="loadVideos()">Refresh</button>
        </div>
      </div>
      <div class="panel-body" style="padding:0">
        <div id="video-list-wrap">
          <div class="empty"><div class="empty-icon">-</div>Loading videos...</div>
        </div>
      </div>
    </div>
  </div>

  <div id="tab-upload" style="display:none">
    <div class="panel">
      <div class="panel-hdr"><div class="panel-title">Upload Video File</div></div>
      <div class="panel-body">
        <div id="upload-alert"></div>
        <div class="form-row">
          <div class="form-group"><label>Video File *</label><input type="file" id="upload-file" accept="video/*,.mkv,.ts,.avi" onchange="onFileSelect()"></div>
          <div class="form-group"><label>Title</label><input id="upload-title" placeholder="Auto-detected from filename"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>Description</label><input id="upload-desc" placeholder="Optional description"></div>
          <div class="form-group"><label>Category</label><input id="upload-cat" placeholder="e.g. Movies, Sports, Kids"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>Tags (comma-separated)</label><input id="upload-tags" placeholder="action, thriller, 2024"></div>
          <div class="form-group"><label>NexVision Movie ID (optional)</label><input id="upload-nxid" type="number" placeholder="VOD movie ID"></div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Output Qualities</label>
            <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:6px">
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--dimmed)"><input type="checkbox" id="q-1080p"> 1080p</label>
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--dimmed)"><input type="checkbox" id="q-720p" checked> 720p</label>
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--dimmed)"><input type="checkbox" id="q-480p" checked> 480p</label>
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--dimmed)"><input type="checkbox" id="q-360p" checked> 360p</label>
            </div>
          </div>
          <div class="form-group"><label>API Key</label><input id="upload-key" type="password" placeholder="Your VOD API key"></div>
        </div>
        <div style="margin-top:8px;display:flex;gap:12px;align-items:center">
          <button class="btn btn-gold" onclick="doUpload()" id="upload-btn">Upload &amp; Transcode</button>
          <div id="upload-progress" style="display:none;flex:1">
            <div style="font-size:12px;color:var(--dimmed);margin-bottom:4px" id="upload-progress-lbl">Uploading...</div>
            <div class="progress-bar"><div class="progress-fill" id="upload-progress-fill" style="width:0%"></div></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div id="tab-import" style="display:none">
    <div class="panel">
      <div class="panel-hdr"><div class="panel-title">Import from URL</div></div>
      <div class="panel-body">
        <div id="import-alert"></div>
        <div class="form-row full"><div class="form-group"><label>Video URL *</label><input id="import-url" placeholder="https://example.com/video.mp4"></div></div>
        <div class="form-row">
          <div class="form-group"><label>Title</label><input id="import-title" placeholder="Auto-detected from URL"></div>
          <div class="form-group"><label>Category</label><input id="import-cat" placeholder="Movies, Sports, Kids..."></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>NexVision Movie ID (optional)</label><input id="import-nxid" type="number" placeholder="VOD movie ID"></div>
          <div class="form-group"><label>API Key</label><input id="import-key" type="password" placeholder="Your VOD API key"></div>
        </div>
        <button class="btn btn-gold" onclick="doImport()">Import &amp; Transcode</button>
        <div id="import-result" style="margin-top:16px"></div>
      </div>
    </div>
  </div>

  <div id="tab-jobs" style="display:none">
    <div class="panel">
      <div class="panel-hdr">
        <div class="panel-title">Active Transcode Jobs</div>
        <button class="btn btn-ghost btn-sm" onclick="loadJobs()">Refresh</button>
      </div>
      <div class="panel-body" id="jobs-list">
        <div class="empty"><div class="empty-icon">-</div>No active jobs</div>
      </div>
    </div>
  </div>

  <div id="tab-settings" style="display:none">
    <div class="panel">
      <div class="panel-hdr"><div class="panel-title">Server Settings</div></div>
      <div class="panel-body">
        <div id="settings-alert"></div>
        <div class="form-row">
          <div class="form-group"><label>Server Name</label><input id="cfg-name" value="NexVision VOD"></div>
          <div class="form-group"><label>NexVision IPTV URL</label><input id="cfg-nx-url" placeholder="http://192.168.1.100:5000"></div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>NexVision JWT Token</label>
            <div style="display:flex;gap:8px;align-items:center">
              <input id="cfg-nx-token" type="password" placeholder="Admin JWT from NexVision login" style="flex:1">
              <button class="btn" style="white-space:nowrap;padding:6px 12px;font-size:12px" onclick="toggleTokenForm()">Get Token</button>
            </div>
            <div id="token-form" style="display:none;margin-top:8px;padding:12px;background:var(--bg4);border-radius:8px;border:1px solid var(--border2)">
              <div style="display:grid;grid-template-columns:1fr 1fr auto;gap:8px;align-items:end">
                <div><label style="font-size:11px;color:var(--muted)">Username</label><input id="tok-user" placeholder="admin" style="margin-top:4px"></div>
                <div><label style="font-size:11px;color:var(--muted)">Password</label><input id="tok-pass" type="password" placeholder="••••••••" style="margin-top:4px"></div>
                <button class="btn btn-gold" style="padding:8px 14px" onclick="fetchToken()">Login</button>
              </div>
              <div id="tok-msg" style="margin-top:6px;font-size:12px"></div>
            </div>
          </div>
          <div class="form-group"><label>Auto-push to NexVision on transcode</label><select id="cfg-autopush"><option value="1">Enabled</option><option value="0">Disabled</option></select></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>HLS Segment Duration (seconds)</label><input id="cfg-seg" type="number" value="4" min="2" max="10"></div>
          <div class="form-group"><label>Admin API Key (to save settings)</label><input id="settings-key" type="password" placeholder="Your VOD API key"></div>
        </div>
        <button class="btn btn-gold" onclick="saveSettings()">Save Settings</button>
      </div>
    </div>
  </div>
</div>

<script>
const API = window.location.origin + '/vod/api';
const APIKEY_LS = 'vod_api_key';
const THEME_KEY = 'nv_theme_mode';
const EMBEDDED_MODE = new URLSearchParams(window.location.search).get('embedded') === '1';
let _searchTimer = null;
let _vod_public_settings = {};
let _vod_public_config_stamp = null;

if (EMBEDDED_MODE) {
    document.body.classList.add('embedded-mode');
    const hdr = document.querySelector('header');
    if (hdr) hdr.remove();
}

function applyTheme(mode) {
    const m = (mode === 'light') ? 'light' : 'dark';
    document.body.setAttribute('data-theme', m);
    updateThemeButton(m);
}
function updateThemeButton(mode) {
    const btn = document.getElementById('theme-toggle');
    const icon = document.getElementById('theme-icon');
    if (btn && icon) {
        if (mode === 'light') {
            btn.innerHTML = '<span id="theme-icon">☀️</span> Normal';
        } else {
            btn.innerHTML = '<span id="theme-icon">🌙</span> Dark';
        }
    }
}
function toggleTheme() {
    const cur = localStorage.getItem(THEME_KEY) || 'dark';
    const next = (cur === 'dark') ? 'light' : 'dark';
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
}
applyTheme(localStorage.getItem(THEME_KEY) || 'dark');
updateThemeButton(localStorage.getItem(THEME_KEY) || 'dark');

async function loadPublicBranding() {
    try {
        const res = await fetch('/api/settings', {method:'GET'});
        if (!res.ok) return;
        const data = await res.json();
        _vod_public_settings = data;
        applyPublicBranding(data);
    } catch (e) {
        console.log('Public branding load skipped', e);
    }
}

function applyPublicBranding(settings) {
    const cfg = settings || _vod_public_settings || {};
    const brandText = String(cfg.admin_brand_name || 'NexVision').trim() || 'NexVision';
    const modeText = String(cfg.admin_mode_label || 'STREAM SERVER').trim() || 'STREAM SERVER';
    const titleText = String(cfg.admin_title || (brandText + ' VOD')).trim() || 'NexVision VOD';
    const logoUrl = String(cfg.admin_logo_url || '').trim();
    const logoEl = document.getElementById('vod-public-logo');
    const badgeEl = document.getElementById('vod-public-badge');

    function renderTextLogo() {
        if (!logoEl) return;
        logoEl.innerHTML = '';
        logoEl.appendChild(document.createTextNode(brandText + ' '));
        const suffix = document.createElement('span');
        suffix.textContent = 'VOD';
        logoEl.appendChild(suffix);
    }

    if (logoEl) {
        if (logoUrl) {
            logoEl.innerHTML = '';
            const img = document.createElement('img');
            img.src = logoUrl;
            img.alt = brandText;
            img.onerror = renderTextLogo;
            logoEl.appendChild(img);
            const suffix = document.createElement('span');
            suffix.textContent = 'VOD';
            logoEl.appendChild(suffix);
        } else {
            renderTextLogo();
        }
    }

    if (badgeEl) badgeEl.textContent = modeText;
    document.title = titleText;
}

async function pollPublicBranding() {
    try {
        const res = await fetch('/api/settings/stamp', {method:'GET'});
        if (!res.ok) return;
        const data = await res.json();
        const nextStamp = String(data.stamp || '0');
        if (_vod_public_config_stamp === null) {
            _vod_public_config_stamp = nextStamp;
            return;
        }
        if (nextStamp !== _vod_public_config_stamp) {
            _vod_public_config_stamp = nextStamp;
            loadPublicBranding();
        }
    } catch (e) {
        console.log('Public branding poll skipped', e);
    }
}

loadPublicBranding();
pollPublicBranding();
setInterval(pollPublicBranding, 30000);

function getKey(inputId) {
  return document.getElementById(inputId).value.trim() ||
         localStorage.getItem(APIKEY_LS) || '';
}
function saveKey(inputId) {
  const k = document.getElementById(inputId).value.trim();
  if (k) localStorage.setItem(APIKEY_LS, k);
}

function switchTab(name) {
  ['videos','upload','import','jobs','settings'].forEach(t => {
    document.getElementById('tab-'+t).style.display = t === name ? '' : 'none';
  });
  document.querySelectorAll('.tab').forEach((b,i) => {
    b.classList.toggle('active', ['videos','upload','import','jobs','settings'][i] === name);
  });
  if (name === 'jobs')     loadJobs();
  if (name === 'settings') loadSettings();
}

async function fetchJson(path, opts) {
  const options = Object.assign({}, opts);
  const storedKey = localStorage.getItem(APIKEY_LS);
  if (storedKey && !((options.headers || {})['X-API-Key'])) {
    options.headers = Object.assign({}, options.headers, {'X-API-Key': storedKey});
  }
  const res = await fetch(API + path, options);
  return res.json();
}

async function loadStats() {
  try {
    const d = await fetchJson('/analytics');
    document.getElementById('st-total').textContent   = d.total_videos;
    document.getElementById('st-ready').textContent   = d.ready_videos;
    document.getElementById('st-views').textContent   = (d.total_views||0).toLocaleString();
    document.getElementById('st-active').textContent  = d.pending_videos;
    document.getElementById('st-size').textContent    = d.total_size_gb + ' GB';
    document.getElementById('st-sessions').textContent = d.active_sessions;

    const h = await fetchJson('/health');
    document.getElementById('hdr-status').textContent =
      'FFmpeg ' + (h.ffmpeg.ok ? 'OK' : 'MISSING') +
      ' | Disk: ' + (h.disk.free_gb||'?') + ' GB free | Up: ' + h.uptime;
  } catch(e) {
    document.getElementById('hdr-status').textContent = 'Server error';
  }
}

let _searchQ = '';
function debounceSearch() {
  _searchQ = document.getElementById('search-input').value;
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(loadVideos, 300);
}

async function loadVideos() {
  const wrap = document.getElementById('video-list-wrap');
  wrap.innerHTML = '<div class="empty"><div class="empty-icon">-</div>Loading...</div>';
  try {
    const q = _searchQ ? '&search=' + encodeURIComponent(_searchQ) : '';
    const d = await fetchJson('/videos?limit=200' + q);
    if (!d.videos || !d.videos.length) {
      wrap.innerHTML = '<div class="empty"><div class="empty-icon">-</div>No videos yet. Upload or import one!</div>';
      return;
    }
    wrap.innerHTML = '<table class="video-table"><thead><tr>'
      + '<th style="width:70px">Thumb</th><th>Title</th><th>Duration</th><th>Status</th><th>HLS URL</th><th>Views</th><th>Actions</th>'
      + '</tr></thead><tbody>'
      + d.videos.map(v => videoRow(v)).join('')
      + '</tbody></table>';
  } catch(e) {
    wrap.innerHTML = '<div class="empty"><div class="empty-icon">!</div>' + e + '</div>';
  }
}

function fmtDur(s) {
  if (!s) return '-';
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), ss = Math.floor(s%60);
  return h > 0 ? h+'h '+m.toString().padStart(2,'0')+'m' : m+':'+ss.toString().padStart(2,'0');
}

function videoRow(v) {
  const statusCls = {ready:'ready',error:'error',transcoding:'transcoding',
    uploading:'uploading',downloading:'downloading',queued:'queued',probed:'transcoding'}[v.status]||'queued';
  const hlsUrl = v.hls_url || '';
  const thumbHtml = v.thumbnail_url
    ? '<img src="'+v.thumbnail_url+'" class="thumb">'
    : '<div class="thumb" style="display:flex;align-items:center;justify-content:center">-</div>';
  const safeId = esc(v.id);
  const safeTitle = esc(v.title);
  // Store URL in a data attribute — avoids all quote-escaping issues in onclick
  const copyBtn  = hlsUrl ? '<button class="copy-btn" data-url="'+esc(hlsUrl)+'" onclick="copyUrl(this)">&#9113; Copy</button>' : '';
  const hlsBtn   = hlsUrl ? '<button class="btn btn-ghost btn-sm" data-url="'+esc(hlsUrl)+'" onclick="copyUrl(this)">HLS</button>' : '';
  return '<tr id="vrow-'+safeId+'">'
    + '<td>'+thumbHtml+'</td>'
    + '<td><div style="font-weight:500">'+safeTitle+'</div>'
    + '<div style="font-size:10px;color:var(--muted)">'+((v.qualities||[]).join(', '))+'</div></td>'
    + '<td style="font-family:monospace;font-size:12px">'+fmtDur(v.duration)+'</td>'
    + '<td><span class="status-badge status-'+statusCls+'">'+v.status+'</span></td>'
    + '<td>'+(hlsUrl ? '<div class="hlsurl">'+esc(hlsUrl)+'</div>'+copyBtn : '<span style="color:var(--muted)">-</span>')+'</td>'
    + '<td style="font-family:monospace;text-align:center">'+(v.views||0)+'</td>'
    + '<td><div style="display:flex;gap:6px">'
    + hlsBtn
    + '<button class="btn btn-red btn-sm" onclick="deleteVideo(\''+safeId+'\',\''+safeTitle+'\')">Del</button>'
    + '</div></td></tr>';
}

function copyUrl(btn) {
  const url = (btn && btn.dataset && btn.dataset.url) ? btn.dataset.url : String(btn);
  if (!url || url === '[object HTMLButtonElement]') return;

  function flash() {
    if (!btn || !btn.dataset) return;
    const orig = btn.innerHTML;
    btn.innerHTML = '&#10003; Copied!';
    btn.style.color = 'var(--green)';
    setTimeout(() => { btn.innerHTML = orig; btn.style.color = ''; }, 1800);
  }

  // 1. Try execCommand (works on HTTP LAN — must run synchronously in click handler)
  const ta = document.createElement('textarea');
  ta.value = url;
  ta.setAttribute('readonly', '');
  // position on-screen but invisible — off-screen (-9999px) can fail in some browsers
  ta.style.cssText = 'position:fixed;top:0;left:0;width:2em;height:2em;opacity:0;z-index:-1;pointer-events:none';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, url.length);
  let ok = false;
  try { ok = document.execCommand('copy'); } catch(e) { ok = false; }
  document.body.removeChild(ta);
  if (ok) { flash(); return; }

  // 2. Try async clipboard API (HTTPS / localhost only — writeText may be undefined on HTTP)
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    navigator.clipboard.writeText(url).then(flash).catch(() => prompt('Copy this URL:', url));
    return;
  }

  // 3. Last resort — show a prompt so user can manually copy
  prompt('Copy this URL:', url);
}

async function deleteVideo(id, title) {
  if (!confirm('Delete "' + title + '"?\nThis removes all HLS segments and the original file.')) return;
  const key = localStorage.getItem(APIKEY_LS) || prompt('API Key:');
  if (!key) return;
  const r = await fetchJson('/videos/' + id, {method:'DELETE', headers:{'X-API-Key': key}});
  if (r.ok) { document.getElementById('vrow-'+id).remove(); loadStats(); }
  else alert('Error: ' + r.error);
}

function onFileSelect() {
  const f = document.getElementById('upload-file').files[0];
  if (f && !document.getElementById('upload-title').value) {
    document.getElementById('upload-title').value =
      f.name.replace(/[.][^.]+$/,'').replace(/[_-]+/g,' ')
             .split(' ').map(w=>w.charAt(0).toUpperCase()+w.slice(1)).join(' ');
  }
}

async function doUpload() {
  const fileEl = document.getElementById('upload-file');
  if (!fileEl.files.length) { showAlert('upload-alert','error','Select a file first'); return; }
  const key = getKey('upload-key');
  if (!key) { showAlert('upload-alert','error','Enter your API key'); return; }
  saveKey('upload-key');

  const qualities = ['1080p','720p','480p','360p'].filter(q => document.getElementById('q-'+q).checked);
  if (!qualities.length) { showAlert('upload-alert','error','Select at least one quality'); return; }

  const fd = new FormData();
  fd.append('file',        fileEl.files[0]);
  fd.append('title',       document.getElementById('upload-title').value);
  fd.append('description', document.getElementById('upload-desc').value);
  fd.append('category',    document.getElementById('upload-cat').value);
  fd.append('tags',        document.getElementById('upload-tags').value);
  fd.append('nexvision_id', document.getElementById('upload-nxid').value || '0');
  fd.append('qualities',   qualities.join(','));

  document.getElementById('upload-btn').disabled = true;
  document.getElementById('upload-progress').style.display = 'flex';
  showAlert('upload-alert','info','Uploading file...');

  try {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', API + '/upload');
    xhr.setRequestHeader('X-API-Key', key);
    xhr.upload.onprogress = e => {
      if (e.lengthComputable) {
        const pct = Math.round(e.loaded/e.total*100);
        document.getElementById('upload-progress-fill').style.width = pct+'%';
        document.getElementById('upload-progress-lbl').textContent = 'Uploading '+pct+'%...';
      }
    };
    xhr.onload = () => {
      const resp = JSON.parse(xhr.responseText);
      if (xhr.status === 202) {
        showAlert('upload-alert','success','Upload complete! Transcoding in progress. ID: '+resp.video_id);
        document.getElementById('upload-progress-lbl').textContent = 'Transcoding...';
        document.getElementById('upload-progress-fill').style.width = '5%';
        pollProgress(resp.video_id,'upload-progress-fill','upload-progress-lbl');
        switchTab('videos');
        setTimeout(loadVideos, 1000);
        loadStats();
      } else {
        showAlert('upload-alert','error', resp.error || 'Upload failed');
        document.getElementById('upload-btn').disabled = false;
      }
    };
    xhr.onerror = () => {
      showAlert('upload-alert','error','Network error');
      document.getElementById('upload-btn').disabled = false;
    };
    xhr.send(fd);
  } catch(e) {
    showAlert('upload-alert','error', e.toString());
    document.getElementById('upload-btn').disabled = false;
  }
}

async function doImport() {
  const url = document.getElementById('import-url').value.trim();
  if (!url) { showAlert('import-alert','error','Enter a URL'); return; }
  const key = getKey('import-key');
  if (!key) { showAlert('import-alert','error','Enter your API key'); return; }
  saveKey('import-key');
  showAlert('import-alert','info','Starting import...');
  try {
    const r = await fetchJson('/import', {
      method:'POST',
      headers:{'Content-Type':'application/json','X-API-Key':key},
      body: JSON.stringify({
        url,
        title:        document.getElementById('import-title').value,
        category:     document.getElementById('import-cat').value,
        nexvision_id: parseInt(document.getElementById('import-nxid').value||0),
      })
    });
    if (r.ok) {
      showAlert('import-alert','success','Import queued! Video ID: '+r.video_id);
      document.getElementById('import-result').innerHTML =
        '<div style="padding:14px;background:var(--bg3);border-radius:8px;font-size:12px;font-family:monospace">'
        + '<div class="progress-bar" style="margin:8px 0"><div class="progress-fill" id="imp-pf" style="width:0%"></div></div>'
        + '<div id="imp-lbl" style="color:var(--dimmed)">Downloading...</div>'
        + '<div style="margin-top:10px;color:var(--muted)">HLS URL (once ready):</div>'
        + '<div style="color:var(--gold)">'+r.hls_url+'</div></div>';
      pollProgress(r.video_id,'imp-pf','imp-lbl');
      setTimeout(loadVideos, 3000);
    } else {
      showAlert('import-alert','error', r.error || 'Import failed');
    }
  } catch(e) {
    showAlert('import-alert','error', e.toString());
  }
}

function pollProgress(videoId, fillId, lblId) {
  const es = new EventSource(API + '/videos/' + videoId + '/progress/stream');
  es.onmessage = e => {
    const d = JSON.parse(e.data);
    const fill = document.getElementById(fillId);
    const lbl  = document.getElementById(lblId);
    if (fill) fill.style.width = d.progress + '%';
    if (lbl) {
      if (d.status === 'ready')       lbl.textContent = 'Transcoding complete!';
      else if (d.status === 'error')  lbl.textContent = 'Error: ' + (d.error||'unknown');
      else if (d.status === 'downloading') lbl.textContent = 'Downloading... ' + d.progress + '%';
      else lbl.textContent = 'Transcoding... ' + d.progress + '% | '
        + Object.entries(d.quality_progress||{}).map(([q,p])=>q+' '+p+'%').join(', ');
    }
    if (d.status === 'ready' || d.status === 'error') { es.close(); loadVideos(); }
  };
  es.onerror = () => es.close();
}

async function loadJobs() {
  const wrap = document.getElementById('jobs-list');
  const d = await fetchJson('/jobs');
  const active = d.filter(j => !['ready','error','cancelled'].includes(j.status));
  if (!active.length) {
    wrap.innerHTML = '<div class="empty"><div class="empty-icon">-</div>No active transcode jobs</div>';
    return;
  }
  wrap.innerHTML = active.map(j =>
    '<div style="padding:14px 0;border-bottom:1px solid var(--border)">'
    + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">'
    + '<div><span style="font-weight:500">'+esc(j.title)+'</span>'
    + '<span class="status-badge status-'+j.status+'" style="margin-left:8px">'+j.status+'</span></div>'
    + '<span style="font-size:14px;font-weight:700;color:var(--gold)">'+(j.progress||0)+'%</span>'
    + '</div><div class="progress-bar"><div class="progress-fill" style="width:'+(j.progress||0)+'%"></div></div>'
    + '</div>'
  ).join('');
}

function toggleTokenForm() {
  const f = document.getElementById('token-form');
  f.style.display = f.style.display === 'none' ? '' : 'none';
}

async function fetchToken() {
  const user = document.getElementById('tok-user').value.trim();
  const pass = document.getElementById('tok-pass').value;
  const msg  = document.getElementById('tok-msg');
  if (!user || !pass) { msg.style.color='var(--red)'; msg.textContent='Enter username and password.'; return; }
  msg.style.color='var(--muted)'; msg.textContent='Logging in...';
  try {
    const r = await fetch(window.location.origin + '/vod/api/auth/token', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({username: user, password: pass})
    });
    const d = await r.json();
    if (d.token) {
      document.getElementById('cfg-nx-token').value = d.token;
      document.getElementById('token-form').style.display = 'none';
      msg.textContent = '';
      showAlert('settings-alert','success','Token obtained — click Save Settings to store it.');
    } else {
      msg.style.color='var(--red)'; msg.textContent = d.error || d.message || 'Login failed';
    }
  } catch(e) {
    msg.style.color='var(--red)'; msg.textContent = 'Request failed: ' + e.message;
  }
}

async function loadSettings() {
  const d = await fetchJson('/settings');
  document.getElementById('cfg-name').value     = d.server_name || '';
  document.getElementById('cfg-nx-url').value   = d.nexvision_url || '';
  document.getElementById('cfg-nx-token').value = d.nexvision_token || '';
  document.getElementById('cfg-autopush').value = d.auto_push_nexvision || '1';
  document.getElementById('cfg-seg').value      = d.hls_segment_secs || '4';
}

async function saveSettings() {
  const key = getKey('settings-key');
  if (!key) { showAlert('settings-alert','error','Enter API key'); return; }
  saveKey('settings-key');
  const d = {
    server_name:         document.getElementById('cfg-name').value,
    nexvision_url:       document.getElementById('cfg-nx-url').value,
    nexvision_token:     document.getElementById('cfg-nx-token').value,
    auto_push_nexvision: document.getElementById('cfg-autopush').value,
    hls_segment_secs:    document.getElementById('cfg-seg').value,
  };
  const r = await fetchJson('/settings', {
    method:'POST', headers:{'Content-Type':'application/json','X-API-Key':key},
    body: JSON.stringify(d)
  });
  if (r.ok) showAlert('settings-alert','success','Settings saved');
  else showAlert('settings-alert','error', r.error || 'Failed');
}

function showAlert(id, type, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  const cls = {success:'alert-success',error:'alert-error',info:'alert-info'}[type]||'alert-info';
  el.innerHTML = '<div class="alert ' + cls + '">' + msg + '</div>';
  if (type !== 'error') setTimeout(() => { el.innerHTML = ''; }, 6000);
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

setInterval(async () => {
  const rows = document.querySelectorAll('#video-list-wrap tr[id^="vrow-"]');
  for (const row of rows) {
    const vid = row.id.replace('vrow-','');
    const cell = row.querySelector('.status-badge');
    if (!cell) continue;
    if (['ready','error'].includes(cell.textContent.trim())) continue;
    try {
      const v = await fetchJson('/videos/' + vid);
      const nb = document.createElement('tbody');
      nb.innerHTML = videoRow(v);
      if (nb.firstElementChild) row.replaceWith(nb.firstElementChild);
    } catch(e) {}
  }
}, 3000);

loadStats();
loadVideos();
setInterval(loadStats, 30000);

const savedKey = localStorage.getItem('vod_api_key') || '';
['upload-key','import-key','settings-key'].forEach(id => {
  const el = document.getElementById(id);
  if (el && savedKey) el.value = savedKey;
});
// Kill any residual service worker so navigation always works cleanly
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then(function(regs) {
    regs.forEach(function(r) { r.unregister(); });
  });
}
if ('caches' in window) {
  caches.keys().then(function(keys) { keys.forEach(function(k) { caches.delete(k); }); });
}
</script>
</body>
</html>"""
    return _html.replace(
        "const APIKEY_LS = 'vod_api_key';",
        "const APIKEY_LS = 'vod_api_key';\n  localStorage.setItem(APIKEY_LS, '" + VOD_API_KEY.replace("'", "\\'") + "');"
    )


@app.route('/vod/admin', methods=['GET'])
def vod_admin_hub():
    """VOD Admin Hub"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>VOD Admin Hub</title>
        <style>
    *{box-sizing:border-box;margin:0;padding:0}:root{--bg:#06060a;--bg2:#0d0d14;--bg3:#131320;--bg4:#1a1a2e;--gold:#c9a84c;--gold2:#e8c56a;--gold3:rgba(201,168,76,.15);--white:#f0f0f8;--muted:rgba(240,240,248,.35);--dimmed:rgba(240,240,248,.6);--border:rgba(255,255,255,.06);--border2:rgba(255,255,255,.12);--red:#e84855;--green:#52d98e;--blue:#4a9eff}body{background:var(--bg);color:var(--white);font-family:system-ui,sans-serif;min-height:100vh}header{background:var(--bg2);border-bottom:1px solid var(--border);padding:16px 32px;display:flex;align-items:center;gap:16px}.logo{font-size:20px;font-weight:700;color:var(--gold);letter-spacing:4px;text-transform:uppercase;display:flex;align-items:center;gap:10px;min-height:32px}.logo span{color:var(--white)}.logo img{display:block;max-height:32px;max-width:180px;width:auto;object-fit:contain}.hdr-badge{font-size:10px;background:var(--gold3);border:1px solid var(--gold);color:var(--gold);padding:2px 10px;border-radius:20px;letter-spacing:1px}.container{max-width:1200px;margin:0 auto;padding:32px}.topnav{display:flex;gap:10px;flex-wrap:wrap;margin-left:16px;align-items:center;flex:1}.topnav a{padding:8px 14px;border-radius:8px;text-decoration:none;color:var(--dimmed);background:var(--bg3);border:1px solid var(--border2);font-size:13px;font-weight:600;transition:.15s}.topnav a:hover{color:var(--white);border-color:var(--gold)}.topnav a.active{background:var(--gold3);border-color:var(--gold);color:var(--gold)}.hdr-right{display:flex;gap:10px;margin-left:auto;align-items:center}.theme-toggle{padding:8px 12px;border-radius:8px;border:1px solid var(--border2);background:var(--bg3);color:var(--dimmed);font-size:12px;font-weight:600;cursor:pointer;transition:.15s;white-space:nowrap;display:flex;align-items:center;gap:6px}.theme-toggle:hover{color:var(--white);border-color:var(--gold)}.header{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:24px;margin-bottom:24px}.header h1{color:var(--white);font-size:28px;margin-bottom:8px}.header p{color:var(--muted);font-size:14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px}.card{background:var(--bg2);border:1px solid var(--border);padding:28px;border-radius:10px;text-align:center;transition:transform .3s}.card:hover{transform:translateY(-3px)}.card h2{color:var(--white);font-size:20px;margin-bottom:12px}.card p{color:var(--muted);margin-bottom:16px;line-height:1.5}.btn{display:inline-block;padding:10px 28px;background:var(--gold);color:#000;text-decoration:none;border-radius:6px;font-weight:600;transition:background .2s;border:none;cursor:pointer}.btn:hover{background:var(--gold2)}.section{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:24px;margin-bottom:24px}.section h2{color:var(--white);font-size:20px;margin-bottom:12px}.section-copy{color:var(--muted);margin-bottom:14px;line-height:1.5}.form-row{display:grid;grid-template-columns:2fr 1fr;gap:12px;align-items:end;margin-bottom:12px}.form-group label{display:block;color:var(--white);font-weight:600;margin-bottom:6px;font-size:12px}.form-group select{width:100%;padding:10px;border:1px solid var(--border2);border-radius:6px;font-family:inherit;font-size:13px;background:var(--bg3);color:var(--white)}.form-group select:focus{outline:none;border-color:var(--gold)}.btn-primary{padding:10px 20px;background:var(--gold);color:#000;border:none;border-radius:6px;font-weight:600;cursor:pointer;width:100%;transition:background .2s}.btn-primary:hover{background:var(--gold2)}.config-help{margin-top:12px;padding:12px;border-radius:6px;background:var(--bg3);color:var(--dimmed);line-height:1.5;font-size:13px}.config-help strong{color:var(--white)}.config-help ul{margin:6px 0 0 16px}.config-help code{background:var(--gold3);border-radius:4px;padding:2px 4px;color:var(--gold);font-size:12px}.form-group input{width:100%;padding:10px;border:1px solid var(--border2);border-radius:6px;font-family:inherit;font-size:13px;background:var(--bg3);color:var(--white)}.form-group input:focus{outline:none;border-color:var(--gold)}.cms-branding-section{margin-top:24px}.cms-branding-section h2{margin-bottom:8px}body[data-theme='light']{--bg:#f4f6fb;--bg2:#ffffff;--bg3:#eef2fb;--bg4:#dfe5f2;--gold:#9a7220;--gold2:#b78929;--gold3:rgba(154,114,32,.12);--white:#1a2233;--muted:rgba(26,34,51,.45);--dimmed:rgba(26,34,51,.7);--border:rgba(12,22,38,.08);--border2:rgba(12,22,38,.16);--red:#c23a48;--green:#2f8e5f;--blue:#2a74c9}body[data-theme='light'] .form-group input{background:var(--bg3);color:var(--white);border-color:var(--border2)}@media(max-width:768px){.grid{grid-template-columns:1fr}.header h1{font-size:22px}.form-row{grid-template-columns:1fr}}
        </style>
    </head>
    <body>
        <header style="display:flex;align-items:center;gap:20px;margin-bottom:24px">
          <div class="logo" id="vod-admin-logo">NexVision <span>VOD</span></div>
          <div class="hdr-badge" id="vod-admin-badge">ADMIN</div>
          <nav class="topnav">
            <a href="/vod">VOD</a>
            <a href="/vod/admin" class="active">Admin</a>
            <a href="/vod/admin/storage">Storage</a>
            <div class="hdr-right">
              <button id="theme-toggle" class="theme-toggle" onclick="toggleTheme()" title="Toggle theme"><span id="theme-icon">🌙</span> Dark</button>
            </div>
          </nav>
        </header>
        <div class="container">
            <div class="header">
                <h1>🎛️ VOD Admin Console</h1>
                <p>Manage your VOD system</p>
            </div>
            <div class="grid">
                <div class="card">
                    <h2>📦 Storage Management</h2>
                    <p>Configure and monitor multi-backend storage (Local, NAS, S3, Azure, GCS)</p>
                    <a href="/vod/admin/storage" class="btn">Go to Storage</a>
                </div>
                <div class="card">
                    <h2>🎬 VOD Dashboard</h2>
                    <p>Manage videos, packages, and content</p>
                    <a href="/vod" class="btn">Go to VOD</a>
                </div>
            </div>
            
            <!-- CMS Branding Section -->
            <div class="section cms-branding-section">
                <h2>🎨 CMS Branding</h2>
                <p class="section-copy">Customize the VOD platform appearance and branding</p>
                
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:20px 0">
                    <div class="form-group">
                        <label>Sidebar Brand Text</label>
                        <input type="text" id="s-vod-brand-text" placeholder="e.g., NETSHIELD" maxlength="50">
                    </div>
                    <div class="form-group">
                        <label>Sidebar Label</label>
                        <input type="text" id="s-vod-mode-label" placeholder="e.g., NETSHIELD" maxlength="50">
                    </div>
                </div>
                
                <div class="form-group">
                    <label>Browser Title</label>
                    <input type="text" id="s-vod-title" placeholder="e.g., Netshield" maxlength="100">
                </div>
                
                <div class="form-group">
                    <label>Sidebar Logo URL (optional)</label>
                    <div style="display:flex;gap:10px">
                        <input type="text" id="s-vod-logo" placeholder="http://..." style="flex:1">
                        <button type="button" onclick="openVODFileUpload()" class="btn-primary" style="width:auto">📁 Upload</button>
                        <input type="file" id="vod-logo-upload" accept="image/*" style="display:none" onchange="uploadVODLogoFile(event)">
                    </div>
                </div>
                
                <div style="display:flex;gap:10px;margin-top:20px">
                    <button onclick="saveVODBranding(this)" class="btn" style="width:auto">💾 Save Branding</button>
                </div>
            </div>
        </div>
        <script>
        const THEME_KEY = 'nv_theme_mode';
        let _vod_settings = {};
        let _vod_config_stamp = null;

        function getVODAuthHeaders(includeJson) {
            const headers = {};
            const token = localStorage.getItem('nv_jwt') || '';
            if (token) headers['Authorization'] = 'Bearer ' + token;
            if (includeJson) headers['Content-Type'] = 'application/json';
            return headers;
        }

        function hasVODToken() {
            return !!localStorage.getItem('nv_jwt');
        }
        
        function applyTheme(mode){
            const m = (mode === 'light') ? 'light' : 'dark';
            document.body.setAttribute('data-theme', m);
            updateThemeButton(m);
        }
        function updateThemeButton(mode) {
            const btn = document.getElementById('theme-toggle');
            if (btn) {
                if (mode === 'light') {
                    btn.innerHTML = '<span id="theme-icon">☀️</span> Normal';
                } else {
                    btn.innerHTML = '<span id="theme-icon">🌙</span> Dark';
                }
            }
        }
        function toggleTheme(){
            const cur = localStorage.getItem(THEME_KEY) || 'dark';
            const next = (cur === 'dark') ? 'light' : 'dark';
            localStorage.setItem(THEME_KEY, next);
            applyTheme(next);
        }
        
        // Load branding from settings
        async function loadVODBranding() {
            try {
                const res = await fetch('/api/settings', { method: 'GET' });
                if (!res.ok) return;
                const data = await res.json();
                _vod_settings = data;
                
                document.getElementById('s-vod-brand-text').value = data.admin_brand_name || '';
                document.getElementById('s-vod-mode-label').value = data.admin_mode_label || '';
                document.getElementById('s-vod-title').value = data.admin_title || '';
                document.getElementById('s-vod-logo').value = data.admin_logo_url || '';
                
                applyVODAminBranding(data);
            } catch(e) {
                console.log('Branding load OK (settings not required)', e);
            }
        }

        async function pollVODBranding() {
            try {
                const res = await fetch('/api/settings/stamp', { method: 'GET' });
                if (!res.ok) return;
                const data = await res.json();
                const nextStamp = String(data.stamp || '0');
                if (_vod_config_stamp === null) {
                    _vod_config_stamp = nextStamp;
                    return;
                }
                if (nextStamp !== _vod_config_stamp) {
                    _vod_config_stamp = nextStamp;
                    loadVODBranding();
                }
            } catch (e) {
                console.log('Branding poll skipped', e);
            }
        }
        
        // Apply branding to VOD admin page itself
        function applyVODAminBranding(s) {
            if (!s) s = _vod_settings;
            const brandText = String(s.admin_brand_name || 'NexVision').trim() || 'NexVision';
            const modeText = String(s.admin_mode_label || 'ADMIN').trim() || 'ADMIN';
            const title = String(s.admin_title || 'VOD Admin Hub').trim() || 'VOD Admin Hub';
            const logoUrl = String(s.admin_logo_url || '').trim();

            const logoEl = document.getElementById('vod-admin-logo');
            const badgeEl = document.getElementById('vod-admin-badge');

            function renderTextLogo() {
                if (!logoEl) return;
                logoEl.innerHTML = '';
                logoEl.appendChild(document.createTextNode(brandText + ' '));
                const suffix = document.createElement('span');
                suffix.textContent = 'VOD';
                logoEl.appendChild(suffix);
            }

            if (logoEl) {
                if (logoUrl) {
                    logoEl.innerHTML = '';
                    const img = document.createElement('img');
                    img.src = logoUrl;
                    img.alt = brandText;
                    img.onerror = renderTextLogo;
                    logoEl.appendChild(img);
                    const suffix = document.createElement('span');
                    suffix.textContent = 'VOD';
                    logoEl.appendChild(suffix);
                } else {
                    renderTextLogo();
                }
            }

            if (badgeEl) badgeEl.textContent = modeText;
            document.title = title;
        }
        
        // Save branding to settings
        async function saveVODBranding(btnEl) {
            if (!hasVODToken()) {
                alert('Login required: open /admin and sign in first, then retry.');
                return;
            }
            const btn = btnEl || document.querySelector('.cms-branding-section .btn');
            const orig = btn ? btn.innerHTML : '';
            if (btn) {
                btn.innerHTML = '⏳ Saving...';
                btn.disabled = true;
            }
            
            const payload = {
                admin_brand_name: document.getElementById('s-vod-brand-text').value,
                admin_mode_label: document.getElementById('s-vod-mode-label').value,
                admin_title: document.getElementById('s-vod-title').value,
                admin_logo_url: document.getElementById('s-vod-logo').value
            };
            
            try {
                const res = await fetch('/api/settings', {
                    method: 'POST',
                    headers: getVODAuthHeaders(true),
                    body: JSON.stringify(payload)
                });
                
                if (res.ok) {
                    _vod_settings = { ..._vod_settings, ...payload };
                    applyVODAminBranding(_vod_settings);
                    if (btn) btn.innerHTML = '✅ Saved!';
                    setTimeout(() => {
                        if (btn) {
                            btn.innerHTML = orig;
                            btn.disabled = false;
                        }
                    }, 1500);
                } else {
                    const data = await res.json().catch(() => ({}));
                    if (data && data.error) alert('Save failed: ' + data.error);
                    if (btn) btn.innerHTML = '❌ Error!';
                    setTimeout(() => {
                        if (btn) {
                            btn.innerHTML = orig;
                            btn.disabled = false;
                        }
                    }, 1500);
                }
            } catch(e) {
                console.error('Save failed:', e);
                if (btn) btn.innerHTML = '❌ Error!';
                setTimeout(() => {
                    if (btn) {
                        btn.innerHTML = orig;
                        btn.disabled = false;
                    }
                }, 1500);
            }
        }
        
        // File upload handlers
        function openVODFileUpload() {
            document.getElementById('vod-logo-upload').click();
        }
        
        async function uploadVODLogoFile(event) {
            const file = event.target.files[0];
            if (!file) return;

            if (!hasVODToken()) {
                alert('Login required: open /admin and sign in first, then retry upload.');
                event.target.value = '';
                return;
            }
            
            const fd = new FormData();
            fd.append('file', file);
            
            const btn = event.target.previousElementSibling;
            const origText = btn.innerHTML;
            btn.innerHTML = '⏳ Uploading...';
            btn.disabled = true;
            
            try {
                const res = await fetch('/api/upload', {
                    method: 'POST',
                    headers: getVODAuthHeaders(false),
                    body: fd,
                    credentials: 'same-origin'
                });
                
                if (res.ok) {
                    const data = await res.json();
                    if (data.url) {
                        document.getElementById('s-vod-logo').value = data.url;
                        // Auto-save after successful upload
                        setTimeout(() => saveVODBranding(), 300);
                    } else {
                        alert('Upload failed: ' + (data.error || 'No URL returned'));
                    }
                } else {
                    const data = await res.json();
                    alert('Upload failed: ' + (data.error || res.statusText));
                }
            } catch(e) {
                console.error('Upload error:', e);
                alert('Upload error: ' + e.message);
            } finally {
                btn.innerHTML = origText;
                btn.disabled = false;
                event.target.value = '';  // Reset file input
            }
        }
        
        applyTheme(localStorage.getItem(THEME_KEY) || 'dark');
        updateThemeButton(localStorage.getItem(THEME_KEY) || 'dark');
        loadVODBranding();
        pollVODBranding();
        setInterval(pollVODBranding, 30000);
        
        // Kill any residual service worker so navigation always works cleanly
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.getRegistrations().then(function(regs) {
                regs.forEach(function(r) { r.unregister(); });
            });
        }
        if ('caches' in window) {
            caches.keys().then(function(keys) { keys.forEach(function(k) { caches.delete(k); }); });
        }
        </script>
    </body>
    </html>
    """
    inframe = request.args.get('inframe') == '1'
    embedded = (
        request.args.get('embedded') == '1'
        or inframe
        or request.headers.get('Sec-Fetch-Dest', '').lower() == 'iframe'
    )
    if embedded:
        nav = '' if inframe else _vod_embedded_nav('admin')
        html = re.sub(
            r'<header style="display:flex;align-items:center;gap:20px;margin-bottom:24px">.*?</header>\s*',
            nav,
            html,
            flags=re.DOTALL
        )
    resp = make_response(html)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/vod/admin/storage', methods=['GET'])
def vod_admin_storage():
    """Storage Management Dashboard"""
    current_config = StorageConfig.load()
    current_backend = current_config.get('backend', StorageConfig.DEFAULT_BACKEND)
    quick_setup_backends = []
    for backend_id, info in StorageConfig.BACKENDS.items():
        quick_setup_backends.append({
            'id': backend_id,
            'name': info['name'],
            'icon': info['icon'],
            'description': info['description'],
            'config_keys': info.get('config_keys', []),
            'optional_keys': info.get('optional_keys', []),
            'configured': all(os.getenv(key) for key in info.get('config_keys', [])) if info.get('requires_config') else True,
            'is_current': backend_id == current_backend,
        })

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Storage Management - NexVision</title>
        <style>
    *{box-sizing:border-box;margin:0;padding:0}:root{--bg:#06060a;--bg2:#0d0d14;--bg3:#131320;--bg4:#1a1a2e;--gold:#c9a84c;--gold2:#e8c56a;--gold3:rgba(201,168,76,.15);--white:#f0f0f8;--muted:rgba(240,240,248,.35);--dimmed:rgba(240,240,248,.6);--border:rgba(255,255,255,.06);--border2:rgba(255,255,255,.12);--red:#e84855;--green:#52d98e;--blue:#4a9eff}body{background:var(--bg);color:var(--white);font-family:system-ui,sans-serif;min-height:100vh}header{background:var(--bg2);border-bottom:1px solid var(--border);padding:16px 32px;display:flex;align-items:center;gap:16px}.logo{font-size:20px;font-weight:700;color:var(--gold);letter-spacing:4px;text-transform:uppercase;display:flex;align-items:center;gap:10px;min-height:32px}.logo span{color:var(--white)}.logo img{display:block;max-height:32px;max-width:180px;width:auto;object-fit:contain}.hdr-badge{font-size:10px;background:var(--gold3);border:1px solid var(--gold);color:var(--gold);padding:2px 10px;border-radius:20px;letter-spacing:1px}.container{max-width:1200px;margin:0 auto;padding:32px}.topnav{display:flex;gap:10px;flex-wrap:wrap;margin-left:16px;align-items:center;flex:1}.topnav a{padding:8px 14px;border-radius:8px;text-decoration:none;color:var(--dimmed);background:var(--bg3);border:1px solid var(--border2);font-size:13px;font-weight:600;transition:.15s}.topnav a:hover{color:var(--white);border-color:var(--gold)}.topnav a.active{background:var(--gold3);border-color:var(--gold);color:var(--gold)}.hdr-right{display:flex;gap:10px;margin-left:auto;align-items:center}.theme-toggle{padding:8px 12px;border-radius:8px;border:1px solid var(--border2);background:var(--bg3);color:var(--dimmed);font-size:12px;font-weight:600;cursor:pointer;transition:.15s;white-space:nowrap;display:flex;align-items:center;gap:6px}.theme-toggle:hover{color:var(--white);border-color:var(--gold)}.header{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:24px;margin-bottom:24px}.header h1{color:var(--white);font-size:28px;margin-bottom:8px}.header p{color:var(--muted);font-size:14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px}.card{background:var(--bg2);border:1px solid var(--border);padding:28px;border-radius:10px;text-align:center;transition:transform .3s}.card:hover{transform:translateY(-3px)}.card h2{color:var(--white);font-size:20px;margin-bottom:12px}.card p{color:var(--muted);margin-bottom:16px;line-height:1.5}.btn{display:inline-block;padding:10px 28px;background:var(--gold);color:#000;text-decoration:none;border-radius:6px;font-weight:600;transition:background .2s;border:none;cursor:pointer}.btn:hover{background:var(--gold2)}.section{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:24px;margin-bottom:24px}.section h2{color:var(--white);font-size:20px;margin-bottom:12px}.section-copy{color:var(--muted);margin-bottom:14px;line-height:1.5}.form-row{display:grid;grid-template-columns:2fr 1fr;gap:12px;align-items:end;margin-bottom:12px}.form-group label{display:block;color:var(--white);font-weight:600;margin-bottom:6px;font-size:12px}.form-group select{width:100%;padding:10px;border:1px solid var(--border2);border-radius:6px;font-family:inherit;font-size:13px;background:var(--bg3);color:var(--white)}.form-group select:focus{outline:none;border-color:var(--gold)}.btn-primary{padding:10px 20px;background:var(--gold);color:#000;border:none;border-radius:6px;font-weight:600;cursor:pointer;width:100%;transition:background .2s}.btn-primary:hover{background:var(--gold2)}.config-help{margin-top:12px;padding:12px;border-radius:6px;background:var(--bg3);color:var(--dimmed);line-height:1.5;font-size:13px}.config-help strong{color:var(--white)}.config-help ul{margin:6px 0 0 16px}.config-help code{background:var(--gold3);border-radius:4px;padding:2px 4px;color:var(--gold);font-size:12px}body[data-theme='light']{--bg:#f4f6fb;--bg2:#ffffff;--bg3:#eef2fb;--bg4:#dfe5f2;--gold:#9a7220;--gold2:#b78929;--gold3:rgba(154,114,32,.12);--white:#1a2233;--muted:rgba(26,34,51,.45);--dimmed:rgba(26,34,51,.7);--border:rgba(12,22,38,.08);--border2:rgba(12,22,38,.16);--red:#c23a48;--green:#2f8e5f;--blue:#2a74c9}@media(max-width:768px){.grid{grid-template-columns:1fr}.header h1{font-size:22px}.form-row{grid-template-columns:1fr}}
        </style>
    </head>
    <body>
        <header style="display:flex;align-items:center;gap:20px;margin-bottom:24px">
          <div class="logo" id="vod-storage-logo">NexVision <span>VOD</span></div>
          <div class="hdr-badge" id="vod-storage-badge">STORAGE</div>
          <nav class="topnav">
            <a href="/vod">VOD</a>
            <a href="/vod/admin">Admin</a>
            <a href="/vod/admin/storage" class="active">Storage</a>
            <div class="hdr-right">
              <button id="theme-toggle" class="theme-toggle" onclick="toggleTheme()" title="Toggle theme"><span id="theme-icon">🌙</span> Dark</button>
            </div>
          </nav>
        </header>
        <div class="container">
            <div class="header">
                <h1>📦 Storage Management</h1>
                <p>Configure and monitor multi-backend storage for your VOD system.</p>
            </div>

            <div class="section">
                <h2>Quick Setup</h2>
                <p class="section-copy">Select a storage backend below to jump to its setup panel and view the required environment variables.</p>
                <div class="config-form">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="quick-backend-select">Select Backend Type:</label>
                            <select id="quick-backend-select">
                                <option value="">Loading backends...</option>
                            </select>
                        </div>
                        <div>
                            <button class="btn-primary" type="button" onclick="openSelectedBackendConfig()">Open Configuration</button>
                        </div>
                    </div>
                    <div id="quick-backend-help" class="config-help">Loading backend requirements...</div>
                </div>
            </div>

            <div class="section">
                __STORAGE_ADMIN_HTML__
            </div>
        </div>
        <script>
            const THEME_KEY = 'nv_theme_mode';
            let _vod_storage_settings = {};
            let _vod_storage_config_stamp = null;
            function applyTheme(mode){
                const m = (mode === 'light') ? 'light' : 'dark';
                document.body.setAttribute('data-theme', m);
                updateThemeButton(m);
            }
            function updateThemeButton(mode) {
                const btn = document.getElementById('theme-toggle');
                if (btn) {
                    if (mode === 'light') {
                        btn.innerHTML = '<span id="theme-icon">☀️</span> Normal';
                    } else {
                        btn.innerHTML = '<span id="theme-icon">🌙</span> Dark';
                    }
                }
            }
            function toggleTheme(){
                const cur = localStorage.getItem(THEME_KEY) || 'dark';
                const next = (cur === 'dark') ? 'light' : 'dark';
                localStorage.setItem(THEME_KEY, next);
                applyTheme(next);
            }

            async function loadStorageBranding() {
                try {
                    const res = await fetch('/api/settings', { method: 'GET' });
                    if (!res.ok) return;
                    const data = await res.json();
                    _vod_storage_settings = data;
                    applyStorageBranding(data);
                } catch (e) {
                    console.log('Storage branding load skipped', e);
                }
            }

            function applyStorageBranding(settings) {
                const cfg = settings || _vod_storage_settings || {};
                const brandText = String(cfg.admin_brand_name || 'NexVision').trim() || 'NexVision';
                const modeText = String(cfg.admin_mode_label || 'STORAGE').trim() || 'STORAGE';
                const titleText = String(cfg.admin_title || 'Storage Management - NexVision').trim() || 'Storage Management - NexVision';
                const logoUrl = String(cfg.admin_logo_url || '').trim();
                const logoEl = document.getElementById('vod-storage-logo');
                const badgeEl = document.getElementById('vod-storage-badge');

                function renderTextLogo() {
                    if (!logoEl) return;
                    logoEl.innerHTML = '';
                    logoEl.appendChild(document.createTextNode(brandText + ' '));
                    const suffix = document.createElement('span');
                    suffix.textContent = 'VOD';
                    logoEl.appendChild(suffix);
                }

                if (logoEl) {
                    if (logoUrl) {
                        logoEl.innerHTML = '';
                        const img = document.createElement('img');
                        img.src = logoUrl;
                        img.alt = brandText;
                        img.onerror = renderTextLogo;
                        logoEl.appendChild(img);
                        const suffix = document.createElement('span');
                        suffix.textContent = 'VOD';
                        logoEl.appendChild(suffix);
                    } else {
                        renderTextLogo();
                    }
                }

                if (badgeEl) badgeEl.textContent = modeText;
                document.title = titleText;
            }

            async function pollStorageBranding() {
                try {
                    const res = await fetch('/api/settings/stamp', { method: 'GET' });
                    if (!res.ok) return;
                    const data = await res.json();
                    const nextStamp = String(data.stamp || '0');
                    if (_vod_storage_config_stamp === null) {
                        _vod_storage_config_stamp = nextStamp;
                        return;
                    }
                    if (nextStamp !== _vod_storage_config_stamp) {
                        _vod_storage_config_stamp = nextStamp;
                        loadStorageBranding();
                    }
                } catch (e) {
                    console.log('Storage branding poll skipped', e);
                }
            }

            applyTheme(localStorage.getItem(THEME_KEY) || 'dark');
            updateThemeButton(localStorage.getItem(THEME_KEY) || 'dark');
            loadStorageBranding();
            pollStorageBranding();
            setInterval(pollStorageBranding, 30000);

            window.quickSetupBackends = __QUICK_SETUP_BACKENDS__;
            window.quickSetupCurrent = __QUICK_SETUP_CURRENT__;

            async function loadQuickSetupBackends() {
                const select = document.getElementById('quick-backend-select');
                const help = document.getElementById('quick-backend-help');
                const backends = window.quickSetupBackends || [];

                if (!backends.length) {
                    help.textContent = 'Unable to load backend configuration.';
                    return;
                }

                select.innerHTML = backends.map(backend => {
                    const current = backend.is_current ? ' (current)' : '';
                    return `<option value="${backend.id}">${backend.name}${current}</option>`;
                }).join('');

                select.value = window.quickSetupCurrent || (backends[0] && backends[0].id) || '';
                updateQuickBackendHelp();
            }

            function updateQuickBackendHelp() {
                const select = document.getElementById('quick-backend-select');
                const help = document.getElementById('quick-backend-help');
                const backends = window.quickSetupBackends || [];
                const backend = backends.find(item => item.id === select.value);

                if (!backend) {
                    help.textContent = 'Choose a backend to view its setup requirements.';
                    return;
                }

                const required = backend.config_keys || [];
                const optional = backend.optional_keys || [];
                let html = `<strong>${backend.icon} ${backend.name}</strong><br>${backend.description}<br>`;
                html += `<strong>Configured:</strong> ${backend.configured ? 'Yes' : 'No'}<br>`;
                html += `<strong>Required variables:</strong>`;
                html += required.length ? `<ul>${required.map(key => `<li><code>${key}</code></li>`).join('')}</ul>` : '<div>No extra variables required.</div>';
                if (optional.length) {
                    html += `<strong>Optional variables:</strong><ul>${optional.map(key => `<li><code>${key}</code></li>`).join('')}</ul>`;
                }
                help.innerHTML = html;
            }

            function openSelectedBackendConfig() {
                const select = document.getElementById('quick-backend-select');
                const backendId = select.value;
                if (!backendId) {
                    return;
                }

                // Try to find and highlight the backend card in STORAGE_ADMIN_HTML
                const card = document.querySelector(`[data-backend-id="${backendId}"]`);
                if (card) {
                    // Clear any previous highlights
                    document.querySelectorAll('.backend-card').forEach(c => {
                        c.style.boxShadow = '';
                        c.style.borderColor = '';
                    });
                    // Highlight the selected card
                    card.style.borderColor = '#0066cc';
                    card.style.boxShadow = '0 0 0 4px rgba(0, 102, 204, 0.15)';
                    // Scroll to it
                    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    return;
                }

                // Fallback: if no card found, show the help info which has the backend details
                updateQuickBackendHelp();
            }

            document.addEventListener('DOMContentLoaded', function() {
                loadQuickSetupBackends();
                document.getElementById('quick-backend-select').addEventListener('change', updateQuickBackendHelp);
            });
            // Kill any residual service worker so navigation always works cleanly
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.getRegistrations().then(function(regs) {
                    regs.forEach(function(r) { r.unregister(); });
                });
            }
            if ('caches' in window) {
                caches.keys().then(function(keys) { keys.forEach(function(k) { caches.delete(k); }); });
            }
        </script>
    </body>
    </html>
    """
    html = html.replace('__STORAGE_ADMIN_HTML__', STORAGE_ADMIN_HTML)
    html = html.replace('__QUICK_SETUP_BACKENDS__', json.dumps(quick_setup_backends))
    html = html.replace('__QUICK_SETUP_CURRENT__', json.dumps(current_backend))
    inframe = request.args.get('inframe') == '1'
    embedded = (
        request.args.get('embedded') == '1'
        or inframe
        or request.headers.get('Sec-Fetch-Dest', '').lower() == 'iframe'
    )
    if embedded:
        nav = '' if inframe else _vod_embedded_nav('storage')
        html = re.sub(
            r'<header style="display:flex;align-items:center;gap:20px;margin-bottom:24px">.*?</header>\s*',
            nav,
            html,
            flags=re.DOTALL
        )
    resp = make_response(html)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


def find_free_port(preferred=5000, fallbacks=(5001, 5002, 5080, 8080, 8000)):
    """Find an available TCP port on Windows and other platforms."""
    import socket
    for port in (preferred,) + fallbacks:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    # Last resort: let OS pick
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('0.0.0.0', 0))
        return s.getsockname()[1]


def get_local_ip():
    """Get the machine's LAN IP so technicians know the TV setup URL."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('8.8.8.8', 80))
            return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'


if __name__ == '__main__':
    # ── Database setup ────────────────────────────────────────────────────────
    init_db()
    _mc = get_db()
    migrate_db(_mc)
    _mc.close()

    # ── VOD database setup ────────────────────────────────────────────────────
    vod_init_db()

    # ── Find available port (Windows port 5000 is often blocked) ──────────────
    PORT = find_free_port(preferred=5000)
    LAN  = get_local_ip()
    _VOD_PORT = PORT   # VOD uses same server/port

    print("\n" + "="*60)
    print("  NexVision IPTV Platform  —  Unified Server")
    print("="*60)
    print(f"  TV  (guests)   :  http://{LAN}:{PORT}")
    print(f"  Admin CMS      :  http://{LAN}:{PORT}/admin/")
    print(f"  Localhost      :  http://localhost:{PORT}")
    print(f"  API base       :  http://localhost:{PORT}/api/")
    print(f"  Login          :  admin / NexVis!0n")
    print(f"")
    print(f"  VOD Dashboard  :  http://{LAN}:{PORT}/vod/")
    print(f"  VOD API        :  http://{LAN}:{PORT}/vod/api/")
    print(f"  VOD API Key    :  {VOD_API_KEY}")
    print(f"  HLS streams    :  http://{LAN}:{PORT}/vod/hls/<id>/master.m3u8")
    if PORT != 5000:
        print(f"\n  Port 5000 was busy - using port {PORT} instead")
        print(f"  To free port 5000:  netstat -ano | findstr :5000")
    print("="*60 + "\n")

    # ── FFmpeg check ─────────────────────────────────────────────────────────
    _ff_ok, _ff_ver, _ff_err = _check_ffmpeg_available()
    if _ff_ok:
        print(f"  FFmpeg         :  {_ff_ver[:60]}")
        print(f"  FFmpeg path    :  {FFMPEG_BIN}")
    else:
        print("\n  ⚠️  WARNING: FFmpeg not found!")
        for line in _ff_err.splitlines():
            print(f"      {line}")
        print()
    print("=" * 60 + "\n")

    # ── Run Flask ─────────────────────────────────────────────────────────────
    # use_reloader=False avoids Windows double-process issues
    # threaded=True handles multiple TV clients simultaneously
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=False,        # set True only for development
        use_reloader=False, # prevents Windows double-launch
        threaded=True,
    )
