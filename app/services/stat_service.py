from flask import jsonify
from ..extensions import get_db


def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def overview():
    conn = get_db()
    total_vod = conn.execute("SELECT COUNT(*) FROM vod_movies WHERE active=1").fetchone()[0]
    watch_minutes = conn.execute(
        "SELECT COALESCE(SUM(duration_minutes),0) FROM watch_history"
    ).fetchone()[0]
    data = {
        'total_rooms':       conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0],
        'online_rooms':      conn.execute(
            "SELECT COUNT(*) FROM rooms WHERE online=1 AND "
            "last_seen >= datetime('now','-10 minutes')"
        ).fetchone()[0],
        'total_channels':    conn.execute("SELECT COUNT(*) FROM channels WHERE active=1").fetchone()[0],
        'total_vod':         total_vod,
        'total_movies':      total_vod,  # alias for admin dashboard
        'total_radio':       conn.execute("SELECT COUNT(*) FROM radio_stations WHERE active=1").fetchone()[0],
        'watch_today':       conn.execute(
            "SELECT COUNT(*) FROM watch_history WHERE started_at >= date('now')"
        ).fetchone()[0],
        'watch_week':        conn.execute(
            "SELECT COUNT(*) FROM watch_history WHERE started_at >= date('now','-7 days')"
        ).fetchone()[0],
        'total_watch_hours': round(watch_minutes / 60, 1),
    }
    conn.close()
    return jsonify(data)


def channels_stats(limit=10):
    conn = get_db()
    rows = conn.execute(
        "SELECT c.id, c.name, COUNT(wh.id) as views "
        "FROM channels c LEFT JOIN watch_history wh ON wh.channel_id=c.id "
        "GROUP BY c.id ORDER BY views DESC LIMIT ?",
        (_safe_int(limit, 10),),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def rooms_stats(limit=10):
    conn = get_db()
    rows = conn.execute(
        "SELECT r.id, r.room_number, r.tv_name, r.online, r.last_seen, "
        "COUNT(wh.id) as views "
        "FROM rooms r LEFT JOIN watch_history wh ON wh.room_id=r.id "
        "GROUP BY r.id ORDER BY views DESC LIMIT ?",
        (_safe_int(limit, 10),),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])
