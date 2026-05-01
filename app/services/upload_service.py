import os
import uuid
from flask import jsonify, current_app
from ..extensions import get_db
from ..config import UPLOAD_DIR


def upload(request):
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'No file'}), 400

    allowed = current_app.config.get('ALLOWED_IMAGE_EXTS', {'png','jpg','jpeg','gif','webp','svg'})
    ext = os.path.splitext(f.filename)[1].lower().lstrip('.')
    if ext not in allowed:
        return jsonify({'error': 'File type not allowed'}), 400

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    f.save(str(UPLOAD_DIR / filename))
    return jsonify({'url': f'/uploads/{filename}'})


def record_watch_event(d: dict):
    room_token = d.get('room_token', '').strip()
    content_type = d.get('type', 'channel')
    content_id   = d.get('id')

    if not content_id:
        return jsonify({'ok': True})

    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']

    try:
        if content_type == 'channel':
            conn.execute(
                "INSERT INTO watch_history (room_id, channel_id, device_type) VALUES (?,?,?)",
                (room_id, content_id, d.get('device_type', 'browser')),
            )
        elif content_type == 'vod':
            conn.execute(
                "INSERT INTO watch_history (room_id, vod_id, device_type) VALUES (?,?,?)",
                (room_id, content_id, d.get('device_type', 'browser')),
            )
        elif content_type == 'radio':
            conn.execute(
                "INSERT INTO watch_history (room_id, radio_id, device_type) VALUES (?,?,?)",
                (room_id, content_id, d.get('device_type', 'browser')),
            )
        conn.commit()
    except Exception:
        pass
    conn.close()
    return jsonify({'ok': True})
