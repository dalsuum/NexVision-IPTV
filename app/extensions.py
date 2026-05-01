"""
extensions.py — shared database and cache singletons.

Import get_db / get_vod_db wherever you need a connection; import cache
wherever you need to read/write the Redis cache.  No Flask app reference
lives here — that breaks the circular-import chain.
"""

import os
import sqlite3
from pathlib import Path

_USE_MYSQL = os.getenv('USE_MYSQL', '0') == '1'

BASE_DIR    = Path(__file__).parent.parent          # /opt/nexvision
DB_PATH     = BASE_DIR / 'nexvision.db'
VOD_DB_PATH = BASE_DIR / 'vod' / 'vod.db'

if _USE_MYSQL:
    from db.db_mysql import (
        get_mysql_db, get_vod_mysql_db, add_column_if_missing,
    )

# Re-export the cache singleton so blueprints/services only need one import
from db.cache_setup import (
    cache, init_cache,
    TTL_SETTINGS, TTL_CHANNELS, TTL_VOD, TTL_NAV,
    TTL_SLIDES, TTL_RSS, TTL_WEATHER,
    invalidate_settings, invalidate_channels, invalidate_vod,
    invalidate_nav, invalidate_slides, invalidate_rss, invalidate_all,
)


def get_db():
    """Return an open main-database connection (SQLite or MySQL)."""
    if _USE_MYSQL:
        return get_mysql_db()
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_vod_db():
    """Return an open VOD-database connection (SQLite or MySQL)."""
    if _USE_MYSQL:
        return get_vod_mysql_db()
    conn = sqlite3.connect(str(VOD_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
