import uuid
from flask import jsonify
from ..extensions import get_db


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def list_rooms(search='', limit=500, offset=0):
    conn   = get_db()
    limit  = _safe_int(limit, 500)
    offset = _safe_int(offset, 0)

    if search:
        rows = conn.execute(
            "SELECT * FROM rooms WHERE room_number LIKE ? OR tv_name LIKE ? "
            "ORDER BY room_number LIMIT ? OFFSET ?",
            (f'%{search}%', f'%{search}%', limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM rooms ORDER BY room_number LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_room(d: dict):
    token = str(uuid.uuid4())
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO rooms (room_number, tv_name, room_token) VALUES (?,?,?)",
        (d['room_number'], d.get('tv_name', ''), token),
    )
    conn.commit()
    room = dict(conn.execute(
        "SELECT * FROM rooms WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(room), 201


def update_room(rid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE rooms SET room_number=?, tv_name=?, guest_name=?, checkin_time=?, checkout_time=? WHERE id=?",
        (
            d['room_number'],
            d.get('tv_name', ''),
            d.get('guest_name', ''),
            d.get('checkin_time', ''),
            d.get('checkout_time', ''),
            rid,
        ),
    )
    conn.commit()
    room = dict(conn.execute(
        "SELECT * FROM rooms WHERE id=?", (rid,)
    ).fetchone())
    conn.close()
    return jsonify(room)


def delete_room(rid: int):
    conn = get_db()
    conn.execute("DELETE FROM rooms WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def regenerate_token(rid: int):
    token = str(uuid.uuid4())
    conn = get_db()
    conn.execute("UPDATE rooms SET room_token=? WHERE id=?", (token, rid))
    conn.commit()
    conn.close()
    return jsonify({'token': token})


def room_setup(token: str):
    conn = get_db()
    room = conn.execute(
        "SELECT * FROM rooms WHERE room_token=?", (token,)
    ).fetchone()
    conn.close()
    if not room:
        return jsonify({'error': 'Invalid token'}), 404
    return jsonify({
        'room_number': room['room_number'],
        'tv_name':     room['tv_name'],
        'token':       token,
        'status':      'ok',
    })


def room_register(d: dict, user_agent: str):
    room_number = str(d.get('room_number', '')).strip()
    if not room_number:
        return jsonify({'error': 'room_number required'}), 400

    conn = get_db()
    room = conn.execute(
        "SELECT * FROM rooms WHERE LOWER(room_number) = LOWER(?)",
        (room_number,),
    ).fetchone()
    if not room:
        conn.close()
        return jsonify({'error': f'Room {room_number} not found'}), 404

    token = room['room_token']
    if not token:
        token = str(uuid.uuid4())
        conn.execute("UPDATE rooms SET room_token=? WHERE id=?", (token, room['id']))
        conn.commit()

    conn.execute(
        "UPDATE rooms SET last_seen=CURRENT_TIMESTAMP, "
        "user_agent=?, online=1 WHERE id=?",
        (user_agent[:200], room['id']),
    )
    conn.commit()
    conn.close()

    return jsonify({
        'status':       'ok',
        'room_number':  room['room_number'],
        'tv_name':      room['tv_name'] or f"TV-{room['room_number']}",
        'token':        token,
        'guest_name':   room['guest_name']    if 'guest_name'    in room.keys() else '',
        'checkin_time': room['checkin_time']  if 'checkin_time'  in room.keys() else '',
        'checkout_time':room['checkout_time'] if 'checkout_time' in room.keys() else '',
    })


def get_room_packages(rid: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT p.* FROM content_packages p "
        "JOIN room_packages rp ON rp.package_id=p.id "
        "WHERE rp.room_id=?",
        (rid,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def set_room_packages(rid: int, d: dict):
    package_ids = d.get('package_ids', [])
    conn = get_db()
    conn.execute("DELETE FROM room_packages WHERE room_id=?", (rid,))
    for pid in package_ids:
        conn.execute(
            "INSERT OR IGNORE INTO room_packages (room_id, package_id) VALUES (?,?)",
            (rid, pid),
        )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def get_rooms_packages_map():
    conn = get_db()
    rows = conn.execute(
        "SELECT rp.room_id, p.name as package_name "
        "FROM room_packages rp "
        "JOIN content_packages p ON p.id=rp.package_id"
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        key = str(r['room_id'])
        result.setdefault(key, []).append(r['package_name'])
    return jsonify(result)


def bulk_delete(ids: list):
    if not ids:
        return jsonify({'ok': True, 'deleted': 0})
    conn = get_db()
    ph = ','.join('?' * len(ids))
    conn.execute(f"DELETE FROM rooms WHERE id IN ({ph})", ids)
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'deleted': len(ids)})


def bulk_add(d: dict):
    rooms = d.get('rooms', [])
    conn = get_db()
    added = 0
    for r in rooms:
        room_number = str(r.get('room_number', '')).strip()
        if not room_number:
            continue
        try:
            conn.execute(
                "INSERT INTO rooms (room_number, tv_name, room_token, active) "
                "VALUES (?,?,?,1)",
                (room_number, r.get('tv_name', ''), str(uuid.uuid4())),
            )
            added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({'added': added})
