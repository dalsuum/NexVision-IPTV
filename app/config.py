"""
config.py — application configuration and filesystem paths.
"""

import os
from pathlib import Path

# ── Filesystem layout ─────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent.parent   # /opt/nexvision

ADMIN_DIR   = BASE_DIR / 'web' / 'admin'
TV_DIR      = BASE_DIR / 'web' / 'tv'
CAST_DIR    = BASE_DIR / 'web' / 'cast'

UPLOAD_DIR  = BASE_DIR / 'uploads'

VOD_DIR     = BASE_DIR / 'vod'
VIDEOS_DIR  = VOD_DIR / 'videos'
HLS_DIR     = VOD_DIR / 'hls'
THUMBS_DIR  = VOD_DIR / 'thumbnails'
VOD_UPLOADS_DIR = VOD_DIR / 'uploads'

# Ensure VOD directories exist at import time
for _d in [VIDEOS_DIR, HLS_DIR, THUMBS_DIR, VOD_UPLOADS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


# ── Flask / app configuration ─────────────────────────────────────────────────

class Config:
    SECRET_KEY        = os.getenv('SECRET_KEY', 'nexvision-iptv-secure-secret-key-2024-x7k9')
    APP_VERSION       = os.getenv('NEXVISION_VERSION', '8.10')
    ONLINE_MINUTES    = 10

    ALLOWED_IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

    # ── VOD ──────────────────────────────────────────────────────────────────
    VOD_API_KEY         = os.getenv('VOD_API_KEY', 'nexvision-vod-key-2024')
    VOD_NEXVISION_URL   = os.getenv('NEXVISION_URL', 'http://localhost:5000')
    VOD_NEXVISION_TOKEN = os.getenv('NEXVISION_TOKEN', '')

    DEFAULT_QUALITIES    = ['720p', '480p', '360p']
    HLS_SEGMENT_SECS     = 4
    MAX_UPLOAD_MB        = 10_000
    ALLOWED_VIDEO_EXTS   = {'.mp4', '.mkv', '.avi', '.mov', '.webm',
                            '.ts', '.m4v', '.flv', '.wmv'}
    QUALITY_PROFILES = [
        ('1080p', '1920x1080', '4000k', '192k'),
        ('720p',  '1280x720',  '2500k', '128k'),
        ('480p',  '854x480',   '1000k', '128k'),
        ('360p',  '640x360',   '600k',  '96k'),
    ]
