"""
app/__init__.py — application factory.

Usage:
    from app import create_app
    application = create_app()
"""

from flask import Flask
from flask_cors import CORS

from .config import Config


def create_app(config_class=Config):
    # No static_folder here — admin_ui blueprint owns all /admin/* routes directly.
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Range is a non-simple header that triggers CORS preflight for Cast / ExoPlayer.
    # expose_headers lets JS/Cast read progress/seek response headers.
    CORS(
        app,
        origins='*',
        allow_headers=[
            'Range', 'Origin', 'Accept', 'X-Requested-With',
            'Content-Type', 'Authorization', 'X-Room-Token',
        ],
        expose_headers=['Content-Length', 'Content-Range', 'Accept-Ranges'],
        methods=['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'],
        max_age=600,
    )

    # ── Cache ─────────────────────────────────────────────────────────────────
    from .extensions import init_cache
    init_cache(app)

    # ── Storage-admin JSON API (VOD, no JWT) ──────────────────────────────────
    from db.vod_storage_admin import create_storage_admin_routes
    create_storage_admin_routes(app)

    # ── Blueprints ────────────────────────────────────────────────────────────
    from .blueprints import register_blueprints
    register_blueprints(app)

    # ── Request hooks ─────────────────────────────────────────────────────────
    from .hooks import register_hooks
    register_hooks(app)

    return app
