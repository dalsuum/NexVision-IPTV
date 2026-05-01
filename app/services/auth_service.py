import hashlib
from datetime import datetime, timedelta

import jwt
from flask import jsonify, current_app

from ..extensions import get_db


def login(username: str, password: str):
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username, pw_hash),
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401

    token = jwt.encode(
        {
            'id':       user['id'],
            'username': user['username'],
            'role':     user['role'],
            'exp':      datetime.utcnow() + timedelta(hours=24),
        },
        current_app.config['SECRET_KEY'],
        algorithm='HS256',
    )
    return jsonify({
        'token': token,
        'user': {
            'id':       user['id'],
            'username': user['username'],
            'role':     user['role'],
        },
    })
