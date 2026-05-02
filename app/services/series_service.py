"""VOD series catalogue — series, seasons, and episodes."""
from flask import jsonify
from ..extensions import get_db, invalidate_vod, bump_config_stamp


# ── Series ─────────────────────────────────────────────────────────────────────

def list_series():
    conn = get_db()
    rows = conn.execute("""
        SELECT s.*,
            COUNT(DISTINCT ss.id)               AS season_count,
            COUNT(DISTINCT CASE WHEN e.active=1 THEN e.id END) AS episode_count
        FROM vod_series s
        LEFT JOIN vod_seasons  ss ON ss.series_id = s.id
        LEFT JOIN vod_episodes e  ON e.series_id  = s.id
        WHERE s.active = 1
        GROUP BY s.id
        ORDER BY s.title
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def list_series_admin():
    """All series including inactive, with counts — for admin panel."""
    conn = get_db()
    rows = conn.execute("""
        SELECT s.*,
            COUNT(DISTINCT ss.id) AS season_count,
            COUNT(DISTINCT e.id)  AS episode_count
        FROM vod_series s
        LEFT JOIN vod_seasons  ss ON ss.series_id = s.id
        LEFT JOIN vod_episodes e  ON e.series_id  = s.id
        GROUP BY s.id
        ORDER BY s.title
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def get_series(sid):
    conn = get_db()
    s = conn.execute("SELECT * FROM vod_series WHERE id=?", (sid,)).fetchone()
    if not s:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    seasons  = conn.execute(
        "SELECT * FROM vod_seasons WHERE series_id=? ORDER BY season_number", (sid,)
    ).fetchall()
    episodes = conn.execute(
        "SELECT * FROM vod_episodes WHERE series_id=? AND active=1 "
        "ORDER BY season_id, episode_number", (sid,)
    ).fetchall()
    conn.close()
    result = dict(s)
    result['seasons'] = []
    for sn in seasons:
        season = dict(sn)
        season['episodes'] = [dict(e) for e in episodes if e['season_id'] == sn['id']]
        result['seasons'].append(season)
    return jsonify(result)


def create_series(d):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO vod_series "
        "(title, description, genre, year, language, rating, poster, backdrop, price, active) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (d['title'], d.get('description', ''), d.get('genre', ''),
         d.get('year', 0), d.get('language', 'English'), d.get('rating', 0),
         d.get('poster', ''), d.get('backdrop', ''),
         d.get('price', 0), d.get('active', 1)),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM vod_series WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    invalidate_vod()
    bump_config_stamp()
    return jsonify(row), 201


def update_series(sid, d):
    conn = get_db()
    conn.execute(
        "UPDATE vod_series SET title=?, description=?, genre=?, year=?, language=?, "
        "rating=?, poster=?, backdrop=?, price=?, active=? WHERE id=?",
        (d['title'], d.get('description', ''), d.get('genre', ''),
         d.get('year', 0), d.get('language', 'English'), d.get('rating', 0),
         d.get('poster', ''), d.get('backdrop', ''),
         d.get('price', 0), d.get('active', 1), sid),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM vod_series WHERE id=?", (sid,)).fetchone())
    conn.close()
    invalidate_vod()
    bump_config_stamp()
    return jsonify(row)


def delete_series(sid):
    conn = get_db()
    conn.execute("DELETE FROM vod_episodes WHERE series_id=?", (sid,))
    conn.execute("DELETE FROM vod_seasons  WHERE series_id=?", (sid,))
    conn.execute("DELETE FROM vod_series   WHERE id=?",        (sid,))
    conn.commit()
    conn.close()
    invalidate_vod()
    bump_config_stamp()
    return jsonify({'ok': True})


# ── Seasons ────────────────────────────────────────────────────────────────────

def create_season(sid, d):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO vod_seasons (series_id, season_number, title, year) VALUES (?,?,?,?)",
        (sid, d.get('season_number', 1), d.get('title', ''), d.get('year', 0)),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM vod_seasons WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(row), 201


def update_season(ssid, d):
    conn = get_db()
    conn.execute(
        "UPDATE vod_seasons SET season_number=?, title=?, year=? WHERE id=?",
        (d.get('season_number', 1), d.get('title', ''), d.get('year', 0), ssid),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM vod_seasons WHERE id=?", (ssid,)).fetchone())
    conn.close()
    return jsonify(row)


def delete_season(ssid):
    conn = get_db()
    conn.execute("DELETE FROM vod_episodes WHERE season_id=?", (ssid,))
    conn.execute("DELETE FROM vod_seasons  WHERE id=?",        (ssid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def get_season_episodes(ssid):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM vod_episodes WHERE season_id=? ORDER BY episode_number", (ssid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── Episodes ───────────────────────────────────────────────────────────────────

def create_episode(ssid, d):
    conn = get_db()
    sn = conn.execute("SELECT series_id FROM vod_seasons WHERE id=?", (ssid,)).fetchone()
    if not sn:
        conn.close()
        return jsonify({'error': 'Season not found'}), 404
    cur = conn.execute(
        "INSERT INTO vod_episodes "
        "(series_id, season_id, episode_number, title, description, "
        " thumbnail, stream_url, runtime, active) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (sn['series_id'], ssid, d.get('episode_number', 1), d['title'],
         d.get('description', ''), d.get('thumbnail', ''),
         d.get('stream_url', ''), d.get('runtime', 0), d.get('active', 1)),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM vod_episodes WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return jsonify(row), 201


def update_episode(eid, d):
    conn = get_db()
    conn.execute(
        "UPDATE vod_episodes SET episode_number=?, title=?, description=?, "
        "thumbnail=?, stream_url=?, runtime=?, active=? WHERE id=?",
        (d.get('episode_number', 1), d['title'], d.get('description', ''),
         d.get('thumbnail', ''), d.get('stream_url', ''),
         d.get('runtime', 0), d.get('active', 1), eid),
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM vod_episodes WHERE id=?", (eid,)).fetchone())
    conn.close()
    return jsonify(row)


def delete_episode(eid):
    conn = get_db()
    conn.execute("DELETE FROM vod_episodes WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
