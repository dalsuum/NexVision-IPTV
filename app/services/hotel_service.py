"""Hotel services (room service, spa, etc.) — not Python service layer."""
import os
import uuid
from flask import jsonify
from ..extensions import get_db
from ..config import UPLOAD_DIR


def get_active(room_token: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM guest_services WHERE active=1 ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def list_all():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM guest_services ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_service(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO guest_services (name, category, icon, phone, description, sort_order, active) "
        "VALUES (?,?,?,?,?,?,?)",
        (d['name'], d.get('category', 'General'), d.get('icon', '📞'),
         d.get('phone', ''), d.get('description', ''),
         d.get('sort_order', 0), d.get('active', 1)),
    )
    conn.commit()
    svc = dict(conn.execute(
        "SELECT * FROM guest_services WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(svc), 201


def update_service(sid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE guest_services SET name=?, category=?, icon=?, "
        "phone=?, description=?, sort_order=?, active=? WHERE id=?",
        (d['name'], d.get('category', 'General'), d.get('icon', '📞'),
         d.get('phone', ''), d.get('description', ''),
         d.get('sort_order', 0), d.get('active', 1), sid),
    )
    conn.commit()
    svc = dict(conn.execute(
        "SELECT * FROM guest_services WHERE id=?", (sid,)
    ).fetchone())
    conn.close()
    return jsonify(svc)


def delete_service(sid: int):
    conn = get_db()
    conn.execute("DELETE FROM guest_services WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def reorder(ids: list):
    conn = get_db()
    for pos, sid in enumerate(ids):
        conn.execute(
            "UPDATE guest_services SET sort_order=? WHERE id=?", (pos, sid)
        )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def upload_image(sid: int, request):
    f = request.files.get('image')
    if not f:
        return jsonify({'error': 'No image'}), 400
    ext = os.path.splitext(f.filename)[1].lower().lstrip('.')
    if ext not in {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}:
        return jsonify({'error': 'Invalid file type'}), 400
    dest = UPLOAD_DIR / 'services'
    dest.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    f.save(str(dest / filename))
    url = f'/uploads/services/{filename}'
    conn = get_db()
    conn.execute("UPDATE guest_services SET icon=? WHERE id=?", (url, sid))
    conn.commit()
    conn.close()
    return jsonify({'url': url})
