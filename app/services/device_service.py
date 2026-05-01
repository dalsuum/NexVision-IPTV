from flask import jsonify
from ..extensions import get_db


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def heartbeat(d: dict, user_agent: str):
    room_token = d.get('room_token', '').strip()
    if not room_token:
        return jsonify({'error': 'room_token required'}), 400

    conn = get_db()
    room = conn.execute(
        "SELECT id FROM rooms WHERE room_token=?", (room_token,)
    ).fetchone()
    if not room:
        conn.close()
        return jsonify({'error': 'Invalid token'}), 404

    conn.execute(
        "UPDATE rooms SET last_seen=CURRENT_TIMESTAMP, user_agent=?, online=1 "
        "WHERE id=?",
        (user_agent[:200], room['id']),
    )

    # Track TV-box device registry by mac_address when provided
    mac = d.get('mac_address', '').strip()
    if mac:
        try:
            conn.execute(
                "INSERT INTO devices (mac_address, room_number, device_name, app_version, last_seen) "
                "VALUES (?,?,?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(mac_address) DO UPDATE SET "
                "room_number=excluded.room_number, device_name=excluded.device_name, "
                "app_version=excluded.app_version, last_seen=CURRENT_TIMESTAMP",
                (mac, d.get('room_number', ''), d.get('device_name', ''), d.get('app_version', '')),
            )
        except Exception:
            pass

    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def list_devices(limit=100, offset=0):
    conn = get_db()
    limit  = _safe_int(limit, 100)
    offset = _safe_int(offset, 0)
    try:
        rows = conn.execute(
            "SELECT id, mac_address, room_number, device_name, app_version, "
            "status, last_seen, created_at FROM devices "
            "ORDER BY last_seen DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception:
        conn.close()
        return jsonify([])
