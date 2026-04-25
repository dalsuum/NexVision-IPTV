"""
cache_setup.py — Redis-backed Flask-Caching for NexVision IPTV
Provides the `cache` object imported by app.py and the invalidation helpers.
"""

import os
from flask_caching import Cache

# ─── Cache configuration ──────────────────────────────────────────────────────
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

CACHE_CONFIG = {
    'CACHE_TYPE':              'RedisCache',
    'CACHE_REDIS_URL':         REDIS_URL,
    'CACHE_DEFAULT_TIMEOUT':   30,          # seconds — default TTL
    'CACHE_KEY_PREFIX':        'nv:',       # namespace all keys
    'CACHE_OPTIONS': {
        'socket_connect_timeout': 2,
        'socket_timeout':         2,
        'retry_on_timeout':       True,
    },
}

# TTLs per data type (seconds)
TTL_SETTINGS  = 60    # hotel settings change rarely
TTL_CHANNELS  = 30    # channel list — TV clients poll often
TTL_VOD       = 60    # VOD library
TTL_NAV       = 120   # navigation config
TTL_SLIDES    = 60    # promo slides
TTL_RSS       = 300   # RSS — fetched from external URLs, expensive
TTL_WEATHER   = 600   # weather data

cache = Cache()


def init_cache(app):
    """Attach the cache to the Flask app."""
    app.config.update(CACHE_CONFIG)
    cache.init_app(app)


# ─── Targeted cache invalidation ─────────────────────────────────────────────
# Call these from admin save endpoints so clients get fresh data immediately.

def invalidate_settings():
    cache.delete('nv:settings')
    cache.delete('nv:settings_stamp')

def invalidate_channels():
    cache.delete('nv:channels')

def invalidate_vod():
    cache.delete('nv:vod')

def invalidate_nav():
    cache.delete('nv:nav')

def invalidate_slides():
    cache.delete('nv:slides')

def invalidate_rss():
    cache.delete('nv:rss_public')

def invalidate_all():
    """Nuclear option — flush the whole NexVision namespace."""
    cache.clear()
