"""
wsgi.py — Production entry point for Gunicorn + gevent
Run with:
    gunicorn -c gunicorn.conf.py wsgi:application
"""

import os

# ── Load .env file if python-dotenv is available ─────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

# ── Import and initialise the Flask app ──────────────────────────────────────
from .main import app, init_db, migrate_db, get_db, vod_init_db
from ..db.cache_setup import init_cache

# Initialise databases on first worker startup
init_db()
conn = get_db()
migrate_db(conn)
conn.close()
vod_init_db()

# Attach Redis cache
init_cache(app)

# Gunicorn expects an `application` callable
application = app
