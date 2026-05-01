from flask import jsonify
from ..extensions import get_db, bump_config_stamp


def get_active(placement: str):
    """Return active ads for a given placement (vod, live, both)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM ads WHERE active=1 AND (placement=? OR placement='both') ORDER BY sort_order, id",
        (placement,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def list_all():
    conn = get_db()
    rows = conn.execute("SELECT * FROM ads ORDER BY sort_order, id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_ad(d: dict):
    conn = get_db()
    max_ord = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM ads").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO ads (title, media_type, media_url, placement, skip_after, "
        "duration_seconds, active, sort_order, link_url) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            d.get('title', 'Ad'),
            d.get('media_type', 'image'),
            d.get('media_url', ''),
            d.get('placement', 'both'),
            int(d.get('skip_after', 5)),
            int(d.get('duration_seconds', 10)),
            int(d.get('active', 1)),
            max_ord + 1,
            d.get('link_url', ''),
        ),
    )
    conn.commit()
    ad = dict(conn.execute("SELECT * FROM ads WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    bump_config_stamp()
    return jsonify(ad), 201


def update_ad(aid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE ads SET title=?, media_type=?, media_url=?, placement=?, skip_after=?, "
        "duration_seconds=?, active=?, sort_order=?, link_url=? WHERE id=?",
        (
            d.get('title', 'Ad'),
            d.get('media_type', 'image'),
            d.get('media_url', ''),
            d.get('placement', 'both'),
            int(d.get('skip_after', 5)),
            int(d.get('duration_seconds', 10)),
            int(d.get('active', 1)),
            int(d.get('sort_order', 0)),
            d.get('link_url', ''),
            aid,
        ),
    )
    conn.commit()
    ad = dict(conn.execute("SELECT * FROM ads WHERE id=?", (aid,)).fetchone())
    conn.close()
    bump_config_stamp()
    return jsonify(ad)


def delete_ad(aid: int):
    conn = get_db()
    conn.execute("DELETE FROM ads WHERE id=?", (aid,))
    conn.commit()
    conn.close()
    bump_config_stamp()
    return jsonify({'ok': True})


def reorder(ids: list):
    conn = get_db()
    for pos, aid in enumerate(ids):
        conn.execute("UPDATE ads SET sort_order=? WHERE id=?", (pos, aid))
    conn.commit()
    conn.close()
    bump_config_stamp()
    return jsonify({'ok': True})
