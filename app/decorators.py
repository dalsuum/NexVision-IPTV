"""
decorators.py — authentication and authorisation decorators.

Uses current_app instead of a direct `app` reference so these work
inside the app-factory pattern without circular imports.
"""

from functools import wraps

import jwt
from flask import request, jsonify, current_app


def token_required(f):
    """Validate JWT Bearer token; sets request.user on success."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            data = jwt.decode(
                token, current_app.config['SECRET_KEY'], algorithms=['HS256']
            )
            request.user = data
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Validate JWT; require role admin or operator."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            data = jwt.decode(
                token, current_app.config['SECRET_KEY'], algorithms=['HS256']
            )
            if data.get('role') not in ('admin', 'operator'):
                return jsonify({'error': 'Admin required'}), 403
            request.user = data
        except Exception:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated


def require_api_key(f):
    """Validate VOD API key from X-API-Key header or ?api_key= param."""
    @wraps(f)
    def decorated(*args, **kwargs):
        key = (
            request.headers.get('X-API-Key') or
            request.args.get('api_key') or
            ''
        )
        if key != current_app.config['VOD_API_KEY']:
            return jsonify({'error': 'Invalid or missing API key'}), 401
        return f(*args, **kwargs)
    return decorated
