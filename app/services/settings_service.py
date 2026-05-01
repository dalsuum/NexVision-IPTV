import json
from flask import jsonify
from ..extensions import get_db, cache, invalidate_settings


def _bump_stamp(conn):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) "
        "VALUES ('config_stamp', CAST(strftime('%s','now') AS TEXT))"
    )


def get_settings(room_token: str):
    cached = cache.get('nv:settings')
    if cached:
        return jsonify(json.loads(cached))

    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    data = {r['key']: r['value'] for r in rows}
    cache.set('nv:settings', json.dumps(data), timeout=60)
    return jsonify(data)


def get_stamp():
    cached = cache.get('nv:settings_stamp')
    if cached:
        return jsonify({'stamp': cached})

    conn = get_db()
    row = conn.execute(
        "SELECT value FROM settings WHERE key='config_stamp'"
    ).fetchone()
    conn.close()
    stamp = row['value'] if row else '0'
    cache.set('nv:settings_stamp', stamp, timeout=10)
    return jsonify({'stamp': stamp})


def save_settings(d: dict):
    conn = get_db()
    for key, value in d.items():
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
            (key, str(value)),
        )
    _bump_stamp(conn)
    conn.commit()
    conn.close()
    invalidate_settings()
    return jsonify({'ok': True})


def get_editor_config():
    conn = get_db()
    row = conn.execute(
        "SELECT value FROM settings WHERE key='editor_config'"
    ).fetchone()
    conn.close()
    if row:
        try:
            return jsonify(json.loads(row['value']))
        except Exception:
            pass
    return jsonify({})
