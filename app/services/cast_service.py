from flask import jsonify
from ..extensions import get_db


def start_session(d: dict):
    conn = get_db()
    try:
        room_id    = d.get('room_id')
        channel_id = d.get('channel_id') or d.get('content_id')
        platform   = d.get('sender_platform', d.get('platform', ''))
        cur = conn.execute(
            "INSERT INTO cast_sessions (room_id, channel_id, sender_platform, started_at) "
            "VALUES (?,?,?,CURRENT_TIMESTAMP)",
            (room_id, channel_id, platform),
        )
        conn.commit()
        session_id = cur.lastrowid
        conn.close()
        return jsonify({'session_id': session_id, 'status': 'started'})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


def end_session(session_id: int, d: dict):
    conn = get_db()
    try:
        duration = d.get('duration_seconds', 0)
        conn.execute(
            "UPDATE cast_sessions SET ended_at=CURRENT_TIMESTAMP, "
            "duration_seconds=? WHERE id=?",
            (duration, session_id),
        )
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 400


def list_sessions(limit=100):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT cs.*, r.room_number, c.name as channel_name "
            "FROM cast_sessions cs "
            "LEFT JOIN rooms r ON r.id=cs.room_id "
            "LEFT JOIN channels c ON c.id=cs.channel_id "
            "ORDER BY cs.started_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500
