import json
from datetime import datetime
from flask import jsonify
from ..extensions import get_db


def _ensure_table():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS alarms (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            label      TEXT    NOT NULL DEFAULT 'Alarm',
            time       TEXT    NOT NULL DEFAULT '07:00',
            days       TEXT    NOT NULL DEFAULT 'daily',
            sound      TEXT             DEFAULT 'bell',
            active     INTEGER          DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def _row_to_dict(row):
    d = dict(row)
    raw = d.get('days', 'daily')
    if raw == 'daily':
        d['days'] = 'daily'
    else:
        try:
            d['days'] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            d['days'] = 'daily'
    return d


def list_all():
    _ensure_table()
    conn = get_db()
    rows = conn.execute("SELECT * FROM alarms ORDER BY time, id").fetchall()
    conn.close()
    return jsonify([_row_to_dict(r) for r in rows])


def create_alarm(d: dict):
    _ensure_table()
    days = d.get('days', 'daily')
    days_str = 'daily' if days == 'daily' else json.dumps(days)
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO alarms (label, time, days, sound, active) VALUES (?,?,?,?,?)",
        (
            d.get('label', 'Alarm'),
            d.get('time', '07:00'),
            days_str,
            d.get('sound', 'bell'),
            int(d.get('active', 1)),
        )
    )
    conn.commit()
    row = conn.execute("SELECT * FROM alarms WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify(_row_to_dict(row)), 201


def update_alarm(aid: int, d: dict):
    _ensure_table()
    days = d.get('days', 'daily')
    days_str = 'daily' if days == 'daily' else json.dumps(days)
    conn = get_db()
    conn.execute(
        "UPDATE alarms SET label=?, time=?, days=?, sound=?, active=? WHERE id=?",
        (
            d.get('label', 'Alarm'),
            d.get('time', '07:00'),
            days_str,
            d.get('sound', 'bell'),
            int(d.get('active', 1)),
            aid,
        )
    )
    conn.commit()
    row = conn.execute("SELECT * FROM alarms WHERE id=?", (aid,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(_row_to_dict(row))


def delete_alarm(aid: int):
    _ensure_table()
    conn = get_db()
    conn.execute("DELETE FROM alarms WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def get_active():
    """Return all active alarms — time matching is done client-side using local browser time."""
    _ensure_table()
    conn = get_db()
    rows = conn.execute("SELECT * FROM alarms WHERE active=1 ORDER BY time").fetchall()
    conn.close()
    return jsonify([_row_to_dict(r) for r in rows])
