from flask import jsonify
from ..extensions import get_db, invalidate_slides, bump_config_stamp


def get_public(room_token: str):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM promo_slides WHERE active=1 ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def list_all():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM promo_slides ORDER BY sort_order, id"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_slide(d: dict):
    conn = get_db()
    max_ord = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM promo_slides").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO promo_slides (title, subtitle, image_url, video_url, "
        "media_type, link_action, sort_order, duration_seconds, active) VALUES (?,?,?,?,?,?,?,?,?)",
        (d.get('title', ''), d.get('subtitle', ''), d.get('image_url', ''),
         d.get('video_url', ''), d.get('media_type', 'image'), d.get('link_action', ''),
         max_ord + 1, d.get('duration_seconds', 5), d.get('active', 1)),
    )
    conn.commit()
    slide = dict(conn.execute(
        "SELECT * FROM promo_slides WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    invalidate_slides()
    bump_config_stamp()
    return jsonify(slide), 201


def update_slide(sid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE promo_slides SET title=?, subtitle=?, image_url=?, video_url=?, "
        "media_type=?, link_action=?, sort_order=?, duration_seconds=?, active=? WHERE id=?",
        (d.get('title', ''), d.get('subtitle', ''), d.get('image_url', ''),
         d.get('video_url', ''), d.get('media_type', 'image'), d.get('link_action', ''),
         d.get('sort_order', 0), d.get('duration_seconds', 5), d.get('active', 1), sid),
    )
    conn.commit()
    slide = dict(conn.execute(
        "SELECT * FROM promo_slides WHERE id=?", (sid,)
    ).fetchone())
    conn.close()
    invalidate_slides()
    bump_config_stamp()
    return jsonify(slide)


def delete_slide(sid: int):
    conn = get_db()
    conn.execute("DELETE FROM promo_slides WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    invalidate_slides()
    bump_config_stamp()
    return jsonify({'ok': True})


def reorder(ids: list):
    conn = get_db()
    for pos, sid in enumerate(ids):
        conn.execute(
            "UPDATE promo_slides SET sort_order=? WHERE id=?", (pos, sid)
        )
    conn.commit()
    conn.close()
    invalidate_slides()
    bump_config_stamp()
    return jsonify({'ok': True})
