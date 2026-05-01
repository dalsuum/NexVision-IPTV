"""VOD movie catalogue — the IPTV side (not the streaming/transcoding server)."""
from flask import jsonify
from ..extensions import get_db, invalidate_vod, bump_config_stamp


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def list_movies(genre=None, search='', package_id=None,
                limit=100, offset=0, room_token=''):
    conn   = get_db()
    limit  = _safe_int(limit, 100)
    offset = _safe_int(offset, 0)

    wheres, params = [], []

    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']

    if genre:
        wheres.append('genre=?')
        params.append(genre)
    if search:
        wheres.append('(title LIKE ? OR description LIKE ?)')
        params += [f'%{search}%', f'%{search}%']
    if package_id:
        wheres.append(
            "id IN (SELECT vod_id FROM package_vod WHERE package_id=?)"
        )
        params.append(int(package_id))
    if room_id is not None:
        wheres.append("""(
            EXISTS (
                SELECT 1 FROM package_vod pv
                JOIN room_packages rp ON rp.package_id=pv.package_id
                WHERE pv.vod_id=vod_movies.id AND rp.room_id=?
            )
            OR EXISTS (
                SELECT 1 FROM vip_vod_access vva
                WHERE vva.video_id=vod_movies.id AND vva.room_id=?
            )
        )""")
        params += [room_id, room_id]

    where_clause = (' WHERE ' + ' AND '.join(wheres)) if wheres else ''
    rows = conn.execute(
        f"SELECT * FROM vod_movies{where_clause} ORDER BY id LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def get_movie(mid: int):
    conn = get_db()
    m = conn.execute("SELECT * FROM vod_movies WHERE id=?", (mid,)).fetchone()
    conn.close()
    if not m:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(m))


def create_movie(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO vod_movies (title, description, poster, backdrop, stream_url, "
        "genre, year, language, runtime, rating, price, active) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (d['title'], d.get('description', ''),
         d.get('poster') or d.get('poster_url', ''),
         d.get('backdrop', ''),
         d.get('stream_url') or d.get('video_url', ''),
         d.get('genre', ''), d.get('year', 0),
         d.get('language', 'English'), d.get('runtime', 0),
         d.get('rating', 0), d.get('price', 0), d.get('active', 1)),
    )
    conn.commit()
    m = dict(conn.execute(
        "SELECT * FROM vod_movies WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    invalidate_vod()
    bump_config_stamp()
    return jsonify(m), 201


def update_movie(mid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE vod_movies SET title=?, description=?, poster=?, backdrop=?, "
        "stream_url=?, genre=?, year=?, language=?, runtime=?, rating=?, price=?, active=? "
        "WHERE id=?",
        (d['title'], d.get('description', ''),
         d.get('poster') or d.get('poster_url', ''),
         d.get('backdrop', ''),
         d.get('stream_url') or d.get('video_url', ''),
         d.get('genre', ''), d.get('year', 0),
         d.get('language', 'English'), d.get('runtime', 0),
         d.get('rating', 0), d.get('price', 0), d.get('active', 1), mid),
    )
    conn.commit()
    m = dict(conn.execute(
        "SELECT * FROM vod_movies WHERE id=?", (mid,)
    ).fetchone())
    conn.close()
    invalidate_vod()
    bump_config_stamp()
    return jsonify(m)


def delete_movie(mid: int):
    conn = get_db()
    conn.execute("DELETE FROM vod_movies WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    invalidate_vod()
    bump_config_stamp()
    return jsonify({'ok': True})


def list_genres():
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT genre FROM vod_movies WHERE genre!='' ORDER BY genre"
    ).fetchall()
    conn.close()
    return jsonify([r['genre'] for r in rows])


def list_packages():
    conn = get_db()
    rows = conn.execute("SELECT * FROM vod_packages ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def list_all_packages():
    conn = get_db()
    rows = conn.execute(
        "SELECT p.*, COUNT(pv.vod_id) as movie_count "
        "FROM vod_packages p "
        "LEFT JOIN package_vod pv ON pv.package_id=p.id "
        "GROUP BY p.id ORDER BY p.name"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_package(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO vod_packages (name, description) VALUES (?,?)",
        (d['name'], d.get('description', '')),
    )
    conn.commit()
    p = dict(conn.execute(
        "SELECT * FROM vod_packages WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(p), 201


def update_package(pid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE vod_packages SET name=?, description=? WHERE id=?",
        (d['name'], d.get('description', ''), pid),
    )
    conn.commit()
    p = dict(conn.execute(
        "SELECT * FROM vod_packages WHERE id=?", (pid,)
    ).fetchone())
    conn.close()
    return jsonify(p)


def delete_package(pid: int):
    conn = get_db()
    conn.execute("DELETE FROM vod_packages WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def bulk_delete(ids: list):
    if not ids:
        return jsonify({'ok': True, 'deleted': 0})
    conn = get_db()
    ph = ','.join('?' * len(ids))
    conn.execute(f"DELETE FROM vod_movies WHERE id IN ({ph})", ids)
    conn.commit()
    conn.close()
    invalidate_vod()
    bump_config_stamp()
    return jsonify({'ok': True, 'deleted': len(ids)})


def bulk_add(d: dict):
    movies = d.get('movies', [])
    conn = get_db()
    added = 0
    for m in movies:
        try:
            conn.execute(
                "INSERT INTO vod_movies (title, stream_url, poster, genre) "
                "VALUES (?,?,?,?)",
                (m.get('title', ''),
                 m.get('stream_url') or m.get('video_url', ''),
                 m.get('poster') or m.get('poster_url', ''),
                 m.get('genre', '')),
            )
            added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    invalidate_vod()
    bump_config_stamp()
    return jsonify({'added': added})


def bulk_delete_packages(ids: list):
    if not ids:
        return jsonify({'ok': True, 'deleted': 0})
    conn = get_db()
    ph = ','.join('?' * len(ids))
    conn.execute(f"DELETE FROM vod_packages WHERE id IN ({ph})", ids)
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'deleted': len(ids)})


def bulk_add_packages(d: dict):
    names = d.get('names', [])
    conn = get_db()
    added = 0
    for name in names:
        name = name.strip()
        if not name:
            continue
        try:
            conn.execute(
                "INSERT INTO vod_packages (name) VALUES (?)", (name,)
            )
            added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({'added': added})
