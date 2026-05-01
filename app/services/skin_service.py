import json
from flask import jsonify
from ..extensions import get_db


def list_skins():
    conn = get_db()
    rows = conn.execute("SELECT * FROM skins ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_skin(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO skins (name, template, background_image, is_default, theme_data) "
        "VALUES (?,?,?,?,?)",
        (d['name'], d.get('template', 'Default Skin'),
         d.get('background_image', ''), d.get('is_default', 0),
         json.dumps(d.get('theme_data', {}))),
    )
    conn.commit()
    skin = dict(conn.execute(
        "SELECT * FROM skins WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(skin), 201


def get_room_skin(room_token: str):
    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']

    skin = None
    if room_id:
        skin = conn.execute(
            "SELECT s.* FROM skins s "
            "JOIN room_skins rs ON rs.skin_id=s.id "
            "WHERE rs.room_id=? LIMIT 1",
            (room_id,),
        ).fetchone()
    if not skin:
        skin = conn.execute(
            "SELECT * FROM skins WHERE is_default=1 LIMIT 1"
        ).fetchone()
    conn.close()

    if not skin:
        return jsonify({'error': 'No skin configured'}), 404
    return jsonify(dict(skin))


def update_skin(sid: int, d: dict):
    conn = get_db()
    if d.get('is_default'):
        conn.execute("UPDATE skins SET is_default=0")
        conn.execute("UPDATE skins SET is_default=1 WHERE id=?", (sid,))
    conn.execute(
        "UPDATE skins SET name=?, template=?, background_image=?, theme_data=? WHERE id=?",
        (d['name'], d.get('template', 'Default Skin'),
         d.get('background_image', ''),
         json.dumps(d.get('theme_data', {})), sid),
    )
    conn.commit()
    skin = dict(conn.execute("SELECT * FROM skins WHERE id=?", (sid,)).fetchone())
    conn.close()
    return jsonify(skin)


def delete_skin(sid: int):
    conn = get_db()
    conn.execute("DELETE FROM skins WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
