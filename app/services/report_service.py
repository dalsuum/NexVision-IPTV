from flask import jsonify
from ..extensions import get_db


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def rooms_report(limit=100, offset=0):
    conn   = get_db()
    limit  = _safe_int(limit, 100)
    offset = _safe_int(offset, 0)
    rows = conn.execute(
        "SELECT r.*, "
        "(SELECT COUNT(*) FROM watch_history wh WHERE wh.room_id=r.id) as watch_count "
        "FROM rooms r ORDER BY watch_count DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def channels_report():
    conn = get_db()
    rows = conn.execute(
        "SELECT c.id, c.name, c.stream_url, c.active, "
        "COUNT(wh.id) as watch_count "
        "FROM channels c LEFT JOIN watch_history wh ON wh.channel_id=c.id "
        "GROUP BY c.id ORDER BY watch_count DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def vod_report():
    conn = get_db()
    rows = conn.execute(
        "SELECT m.id, m.title, m.genre, "
        "COUNT(wh.id) as watch_count "
        "FROM vod_movies m LEFT JOIN watch_history wh ON wh.movie_id=m.id "
        "GROUP BY m.id ORDER BY watch_count DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def radio_report():
    conn = get_db()
    rows = conn.execute(
        "SELECT rs.id, rs.name, rs.country, "
        "COUNT(wh.id) as watch_count "
        "FROM radio_stations rs "
        "LEFT JOIN watch_history wh ON wh.radio_id=rs.id "
        "GROUP BY rs.id ORDER BY watch_count DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def pages_report():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, group_name, active, "
        "(SELECT COUNT(*) FROM content_items ci WHERE ci.page_id=content_pages.id) as item_count "
        "FROM content_pages ORDER BY name"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def summary_report(days=7):
    days = _safe_int(days, 7)
    conn = get_db()

    top_channels = conn.execute(
        "SELECT c.name, COALESCE(SUM(wh.duration_minutes),0) as total_minutes "
        "FROM channels c LEFT JOIN watch_history wh ON wh.channel_id=c.id "
        "AND wh.started_at >= date('now',?) "
        "GROUP BY c.id ORDER BY total_minutes DESC LIMIT 6",
        (f'-{days} days',),
    ).fetchall()

    top_rooms = conn.execute(
        "SELECT r.room_number, COALESCE(SUM(wh.duration_minutes),0) as total_minutes "
        "FROM rooms r LEFT JOIN watch_history wh ON wh.room_id=r.id "
        "AND wh.started_at >= date('now',?) "
        "GROUP BY r.id ORDER BY total_minutes DESC LIMIT 6",
        (f'-{days} days',),
    ).fetchall()

    top_vod = conn.execute(
        "SELECT m.title, COUNT(wh.id) as sessions "
        "FROM vod_movies m LEFT JOIN watch_history wh ON wh.movie_id=m.id "
        "AND wh.started_at >= date('now',?) "
        "GROUP BY m.id ORDER BY sessions DESC LIMIT 6",
        (f'-{days} days',),
    ).fetchall()

    daily = conn.execute(
        "SELECT date(started_at) as day, COALESCE(SUM(duration_minutes),0) as total_minutes "
        "FROM watch_history WHERE started_at >= date('now',?) "
        "GROUP BY day ORDER BY day",
        (f'-{days} days',),
    ).fetchall()

    hourly = conn.execute(
        "SELECT strftime('%H',started_at) as hour, COALESCE(SUM(duration_minutes),0) as total_minutes "
        "FROM watch_history WHERE started_at >= date('now',?) "
        "GROUP BY hour ORDER BY hour",
        (f'-{days} days',),
    ).fetchall()

    conn.close()
    return jsonify({
        'top_channels': [dict(r) for r in top_channels],
        'top_rooms':    [dict(r) for r in top_rooms],
        'top_vod':      [dict(r) for r in top_vod],
        'daily':        [dict(r) for r in daily],
        'hourly':       [dict(r) for r in hourly],
    })


def devices_report():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, mac_address, room_number, device_name, app_version, "
            "status, last_seen, created_at FROM devices "
            "ORDER BY last_seen DESC LIMIT 200"
        ).fetchall()
        conn.close()
        return jsonify([dict(r) for r in rows])
    except Exception:
        conn.close()
        return jsonify([])
