import hashlib
from flask import jsonify
from ..extensions import get_db


def list_users():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, role, created_at FROM users ORDER BY username"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_user(d: dict):
    pw_hash = hashlib.sha256(d.get('password', '').encode()).hexdigest()
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?,?,?)",
            (d['username'], pw_hash, d.get('role', 'operator')),
        )
        conn.commit()
        user = dict(conn.execute(
            "SELECT id, username, role FROM users WHERE id=?", (cur.lastrowid,)
        ).fetchone())
        conn.close()
        return jsonify(user), 201
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


def delete_user(uid: int):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
