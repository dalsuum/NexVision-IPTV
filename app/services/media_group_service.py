from flask import jsonify
from ..extensions import get_db


def list_groups():
    conn = get_db()
    rows = conn.execute(
        "SELECT mg.*, COUNT(c.id) as channel_count "
        "FROM media_groups mg "
        "LEFT JOIN channels c ON c.media_group_id=mg.id "
        "GROUP BY mg.id ORDER BY mg.name"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_group(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO media_groups (name, active) VALUES (?,?)",
        (d['name'], d.get('active', 1)),
    )
    conn.commit()
    g = dict(conn.execute(
        "SELECT mg.*, COUNT(c.id) as channel_count "
        "FROM media_groups mg LEFT JOIN channels c ON c.media_group_id=mg.id "
        "WHERE mg.id=? GROUP BY mg.id",
        (cur.lastrowid,),
    ).fetchone())
    conn.close()
    return jsonify(g), 201


def update_group(gid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE media_groups SET name=?, active=? WHERE id=?",
        (d['name'], d.get('active', 1), gid),
    )
    conn.commit()
    g = dict(conn.execute(
        "SELECT mg.*, COUNT(c.id) as channel_count "
        "FROM media_groups mg LEFT JOIN channels c ON c.media_group_id=mg.id "
        "WHERE mg.id=? GROUP BY mg.id",
        (gid,),
    ).fetchone())
    conn.close()
    return jsonify(g)


def delete_group(gid: int):
    conn = get_db()
    conn.execute("DELETE FROM media_groups WHERE id=?", (gid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def bulk_delete(ids: list):
    if not ids:
        return jsonify({'deleted': 0})
    conn = get_db()
    ph = ','.join('?' * len(ids))
    conn.execute(f"DELETE FROM media_groups WHERE id IN ({ph})", ids)
    conn.commit()
    conn.close()
    return jsonify({'deleted': len(ids)})


def bulk_add(names: list):
    conn = get_db()
    added = 0
    for name in names:
        name = name.strip()
        if not name:
            continue
        try:
            conn.execute("INSERT INTO media_groups (name) VALUES (?)", (name,))
            added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({'added': added})
