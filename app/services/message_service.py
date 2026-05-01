from flask import jsonify
from ..extensions import get_db


def list_messages():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM messages ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def get_active(room_token: str):
    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']

    rows = conn.execute(
        "SELECT m.* FROM messages m "
        "WHERE m.active=1 "
        "AND (m.start_time IS NULL OR m.start_time <= CURRENT_TIMESTAMP) "
        "AND (m.end_time IS NULL OR m.end_time >= CURRENT_TIMESTAMP) "
        "ORDER BY m.created_at DESC"
    ).fetchall()

    if room_id:
        dismissed_ids = {r['message_id'] for r in conn.execute(
            "SELECT message_id FROM message_dismissals WHERE room_id=?", (room_id,)
        ).fetchall()}
        rows = [r for r in rows if r['id'] not in dismissed_ids]

    conn.close()
    return jsonify([dict(r) for r in rows])


def get_inbox(room_token: str, limit=50, offset=0):
    try:
        limit  = int(limit)
        offset = int(offset)
    except (ValueError, TypeError):
        limit, offset = 50, 0

    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']

    if room_id:
        rows = conn.execute(
            "SELECT m.*, "
            "CASE WHEN mr.id IS NOT NULL THEN 1 ELSE 0 END as is_read "
            "FROM messages m "
            "LEFT JOIN message_reads mr ON mr.message_id=m.id AND mr.room_id=? "
            "WHERE m.active=1 "
            "ORDER BY m.created_at DESC LIMIT ? OFFSET ?",
            (room_id, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT *, 0 as is_read FROM messages WHERE active=1 "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def get_unread_count(room_token: str):
    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']

    if room_id:
        total = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE active=1"
        ).fetchone()[0]
        read_count = conn.execute(
            "SELECT COUNT(*) FROM message_reads WHERE room_id=?", (room_id,)
        ).fetchone()[0]
        count = max(0, total - read_count)
    else:
        count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE active=1"
        ).fetchone()[0]
    conn.close()
    return jsonify({'count': count})


def create_message(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO messages (title, body, message_type, active, "
        "start_time, end_time) VALUES (?,?,?,?,?,?)",
        (d.get('title', ''), d.get('body', ''), d.get('message_type', 'info'),
         d.get('active', 1), d.get('start_time'), d.get('end_time')),
    )
    conn.commit()
    msg = dict(conn.execute(
        "SELECT * FROM messages WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(msg), 201


def update_message(mid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE messages SET title=?, body=?, message_type=?, active=?, "
        "start_time=?, end_time=? WHERE id=?",
        (d.get('title', ''), d.get('body', ''), d.get('message_type', 'info'),
         d.get('active', 1), d.get('start_time'), d.get('end_time'), mid),
    )
    conn.commit()
    msg = dict(conn.execute(
        "SELECT * FROM messages WHERE id=?", (mid,)
    ).fetchone())
    conn.close()
    return jsonify(msg)


def delete_message(mid: int):
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def dismiss_message(mid: int, room_token: str):
    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']
    if room_id:
        conn.execute(
            "INSERT OR IGNORE INTO message_dismissals (message_id, room_id) VALUES (?,?)",
            (mid, room_id),
        )
        conn.commit()
    conn.close()
    return jsonify({'ok': True})


def mark_read(mid: int, room_token: str):
    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']
    if room_id:
        conn.execute(
            "INSERT OR IGNORE INTO message_reads (message_id, room_id) VALUES (?,?)",
            (mid, room_id),
        )
        conn.commit()
    conn.close()
    return jsonify({'ok': True})


def mark_all_read(room_token: str):
    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']
    if room_id:
        msgs = conn.execute("SELECT id FROM messages WHERE active=1").fetchall()
        for m in msgs:
            conn.execute(
                "INSERT OR IGNORE INTO message_reads (message_id, room_id) VALUES (?,?)",
                (m['id'], room_id),
            )
        conn.commit()
    conn.close()
    return jsonify({'ok': True})
