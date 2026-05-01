#!/usr/bin/env python3
"""
run.py — Development entry point.
Run with: python run.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

from app import create_app
from app.main import init_db, migrate_db, get_db, vod_init_db

if __name__ == '__main__':
    app = create_app()
    init_db()
    conn = get_db()
    migrate_db(conn)
    conn.close()
    vod_init_db()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
