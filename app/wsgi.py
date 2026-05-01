"""
wsgi.py — Production entry point for Gunicorn + gevent.

Run with:
    gunicorn -c gunicorn.conf.py wsgi:application
"""

import os

# Load .env before importing anything that reads environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
except ImportError:
    pass

# Create app via factory
from app import create_app
from app.main import init_db, migrate_db, get_db, vod_init_db   # legacy init helpers

application = create_app()

# Initialise databases — use a file lock so only one worker runs init_db at a time
import time as _time, fcntl as _fcntl
_lock_path = '/tmp/nexvision_init.lock'
_lock_file = open(_lock_path, 'w')
try:
    _fcntl.flock(_lock_file, _fcntl.LOCK_EX)
    for _attempt in range(5):
        try:
            init_db()
            break
        except Exception:
            _time.sleep(0.5 + _attempt * 0.5)
finally:
    _fcntl.flock(_lock_file, _fcntl.LOCK_UN)
    _lock_file.close()

try:
    _conn = get_db()
    migrate_db(_conn)
    _conn.close()
except Exception:
    pass

try:
    vod_init_db()
except Exception:
    pass
