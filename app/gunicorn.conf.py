"""
gunicorn.conf.py — Gunicorn + gevent configuration for 500 concurrent users
Adjust worker count based on: workers = (2 × CPU_cores) + 1
"""

import multiprocessing
import os

# ─── Binding ──────────────────────────────────────────────────────────────────
bind            = 'unix:/run/nexvision/gunicorn.sock'   # Nginx communicates via socket
backlog         = 2048

# ─── Worker model ─────────────────────────────────────────────────────────────
# gevent: single-threaded async I/O — handles 500+ waiting connections cheaply.
# Each worker uses ~50–80 MB RAM.  On a 64 GB server: up to 16 workers safe.
worker_class    = 'gevent'
worker_connections = 1000          # concurrent connections per worker (gevent)
workers         = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))

# ─── Timeouts ─────────────────────────────────────────────────────────────────
timeout         = 120              # RSS fetches / FFmpeg can be slow
graceful_timeout = 30
keepalive       = 5

# ─── Logging ──────────────────────────────────────────────────────────────────
accesslog       = '/var/log/nexvision/access.log'
errorlog        = '/var/log/nexvision/error.log'
loglevel        = 'warning'        # change to 'info' for debug
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)sμs'

# ─── Process management ───────────────────────────────────────────────────────
daemon          = False            # systemd manages the process
pidfile         = '/run/nexvision/gunicorn.pid'
# user            = 'nexvision'
# group           = 'nexvision'

# ─── Worker recycling (prevents memory leaks) ─────────────────────────────────
max_requests        = 5000
max_requests_jitter = 500          # randomise restart to avoid thundering herd
