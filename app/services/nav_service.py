import json
from flask import jsonify
from ..extensions import get_db, invalidate_nav, bump_config_stamp


def get_nav(room_token: str):
    conn = get_db()
    items = [dict(r) for r in conn.execute(
        "SELECT * FROM nav_items ORDER BY sort_order, id"
    ).fetchall()]
    pos_row   = conn.execute("SELECT value FROM settings WHERE key='navbar_position'").fetchone()
    style_row = conn.execute("SELECT value FROM settings WHERE key='navbar_style'").fetchone()
    conn.close()
    return jsonify({
        'items':    items,
        'position': pos_row['value'] if pos_row else 'top',
        'style':    style_row['value'] if style_row else 'pill',
    })


def list_items_admin():
    conn = get_db()
    rows      = conn.execute("SELECT * FROM nav_items ORDER BY sort_order, id").fetchall()
    pos_row   = conn.execute("SELECT value FROM settings WHERE key='navbar_position'").fetchone()
    style_row = conn.execute("SELECT value FROM settings WHERE key='navbar_style'").fetchone()
    conn.close()
    return jsonify({
        'items':    [dict(r) for r in rows],
        'position': pos_row['value'] if pos_row else 'top',
        'style':    style_row['value'] if style_row else 'pill',
    })


def create_item(d: dict):
    conn = get_db()
    max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM nav_items").fetchone()[0]
    cur = conn.execute(
        "INSERT INTO nav_items (key, label, icon, enabled, sort_order, is_system, target_url) "
        "VALUES (?,?,?,?,?,0,?)",
        (d['key'], d['label'], d.get('icon', ''),
         d.get('enabled', 1), d.get('sort_order', max_order + 1),
         d.get('target_url', '')),
    )
    conn.commit()
    item = dict(conn.execute(
        "SELECT * FROM nav_items WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    invalidate_nav()
    bump_config_stamp()
    return jsonify(item), 201


def update_item(nid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE nav_items SET label=?, icon=?, enabled=?, target_url=? WHERE id=?",
        (d['label'], d.get('icon', ''), d.get('enabled', 1),
         d.get('target_url', ''), nid),
    )
    conn.commit()
    item = dict(conn.execute(
        "SELECT * FROM nav_items WHERE id=?", (nid,)
    ).fetchone())
    conn.close()
    invalidate_nav()
    bump_config_stamp()
    return jsonify(item)


def toggle_item(nid: int):
    conn = get_db()
    conn.execute(
        "UPDATE nav_items SET enabled = CASE WHEN enabled=1 THEN 0 ELSE 1 END WHERE id=?",
        (nid,),
    )
    conn.commit()
    item = dict(conn.execute(
        "SELECT * FROM nav_items WHERE id=?", (nid,)
    ).fetchone())
    conn.close()
    invalidate_nav()
    bump_config_stamp()
    return jsonify(item)


def delete_item(nid: int):
    conn = get_db()
    conn.execute("DELETE FROM nav_items WHERE id=?", (nid,))
    conn.commit()
    conn.close()
    invalidate_nav()
    bump_config_stamp()
    return jsonify({'ok': True})


def reorder(ids: list):
    conn = get_db()
    for pos, nid in enumerate(ids):
        conn.execute(
            "UPDATE nav_items SET sort_order=? WHERE id=?", (pos, nid)
        )
    conn.commit()
    conn.close()
    invalidate_nav()
    bump_config_stamp()
    return jsonify({'ok': True})


def set_position(d: dict):
    position = d.get('position', 'bottom')
    style    = d.get('style', 'pill')
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('navbar_position',?)",
        (position,),
    )
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('navbar_style',?)",
        (style,),
    )
    conn.commit()
    conn.close()
    invalidate_nav()
    bump_config_stamp()
    return jsonify({'ok': True, 'position': position, 'style': style})
