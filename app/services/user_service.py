import hashlib
from flask import jsonify
from ..extensions import get_db


def list_users():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, role, city, created_at FROM users ORDER BY username"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_user(d: dict):
    pw_hash = hashlib.sha256(d.get('password', '').encode()).hexdigest()
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password, role, city) VALUES (?,?,?,?)",
            (d['username'], pw_hash, d.get('role', 'operator'), d.get('city', '')),
        )
        conn.commit()
        user = dict(conn.execute(
            "SELECT id, username, role, city FROM users WHERE id=?", (cur.lastrowid,)
        ).fetchone())
        conn.close()
        return jsonify(user), 201
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


def update_user(uid: int, d: dict):
    conn = get_db()
    try:
        fields, vals = [], []
        if 'city' in d:
            fields.append('city=?')
            vals.append(d['city'])
        if 'role' in d:
            fields.append('role=?')
            vals.append(d['role'])
        if d.get('password'):
            fields.append('password=?')
            vals.append(hashlib.sha256(d['password'].encode()).hexdigest())
        if not fields:
            conn.close()
            return jsonify({'error': 'Nothing to update'}), 400
        vals.append(uid)
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", vals)
        conn.commit()
        user = dict(conn.execute(
            "SELECT id, username, role, city FROM users WHERE id=?", (uid,)
        ).fetchone())
        conn.close()
        return jsonify(user)
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


def delete_user(uid: int):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def get_user_city(uid: int) -> str:
    conn = get_db()
    row = conn.execute("SELECT city FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return (row['city'] or '') if row else ''
