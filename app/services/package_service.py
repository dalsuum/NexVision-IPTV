"""Content packages and VIP per-room access grants."""
from flask import jsonify
from ..extensions import get_db


def _sync_package_content(conn, pid, channel_ids, vod_ids, radio_ids=None, select_all_channels=False):
    conn.execute("DELETE FROM package_channels WHERE package_id=?", (pid,))
    conn.execute("DELETE FROM package_vod WHERE package_id=?", (pid,))
    if radio_ids is not None:
        conn.execute("DELETE FROM package_radio WHERE package_id=?", (pid,))

    if select_all_channels:
        conn.execute(
            "INSERT OR IGNORE INTO package_channels (package_id, channel_id) SELECT ?, id FROM channels",
            (pid,),
        )
    else:
        for cid in (channel_ids or []):
            conn.execute(
                "INSERT OR IGNORE INTO package_channels (package_id, channel_id) VALUES (?,?)",
                (pid, cid),
            )
    for vid in (vod_ids or []):
        conn.execute(
            "INSERT OR IGNORE INTO package_vod (package_id, vod_id) VALUES (?,?)",
            (pid, vid),
        )
    for rid in (radio_ids or []):
        conn.execute(
            "INSERT OR IGNORE INTO package_radio (package_id, radio_id) VALUES (?,?)",
            (pid, rid),
        )


def list_packages():
    conn = get_db()
    total_chs = (conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0]) or 0
    rows = conn.execute(
        "SELECT p.*, "
        "COUNT(DISTINCT pc.channel_id) as channel_count, "
        "COUNT(DISTINCT pv.vod_id) as vod_count, "
        "COUNT(DISTINCT pr.radio_id) as radio_count, "
        "GROUP_CONCAT(DISTINCT pc.channel_id) as _channel_ids, "
        "GROUP_CONCAT(DISTINCT pv.vod_id) as _vod_ids, "
        "GROUP_CONCAT(DISTINCT pr.radio_id) as _radio_ids "
        "FROM content_packages p "
        "LEFT JOIN package_channels pc ON pc.package_id=p.id "
        "LEFT JOIN package_vod pv ON pv.package_id=p.id "
        "LEFT JOIN package_radio pr ON pr.package_id=p.id "
        "GROUP BY p.id ORDER BY p.name"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        ch_count = d.get('channel_count', 0)
        # When all channels are assigned, skip sending the full ID list — use the flag instead
        if total_chs > 0 and ch_count >= total_chs:
            d['select_all_channels'] = True
            d['channel_ids'] = []
            d.pop('_channel_ids', None)
        else:
            d['select_all_channels'] = False
            d['channel_ids'] = [int(x) for x in d.pop('_channel_ids').split(',')] if d.get('_channel_ids') else []
        d['vod_ids']   = [int(x) for x in d.pop('_vod_ids').split(',')]   if d.get('_vod_ids')   else []
        d['radio_ids'] = [int(x) for x in d.pop('_radio_ids').split(',')]  if d.get('_radio_ids')  else []
        result.append(d)
    return jsonify(result)


def create_package(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO content_packages (name, description, active) VALUES (?,?,?)",
        (d['name'], d.get('description', ''), d.get('active', 1)),
    )
    pid = cur.lastrowid
    _sync_package_content(conn, pid,
                          d.get('channel_ids', []),
                          d.get('vod_ids', []),
                          d.get('radio_ids', []),
                          select_all_channels=bool(d.get('select_all_channels')))
    conn.commit()
    pkg = dict(conn.execute("SELECT * FROM content_packages WHERE id=?", (pid,)).fetchone())
    conn.close()
    return jsonify(pkg), 201


def update_package(pid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE content_packages SET name=?, description=?, active=? WHERE id=?",
        (d['name'], d.get('description', ''), d.get('active', 1), pid),
    )
    if 'channel_ids' in d or 'vod_ids' in d or d.get('select_all_channels'):
        _sync_package_content(conn, pid,
                              d.get('channel_ids', []),
                              d.get('vod_ids', []),
                              d.get('radio_ids'),
                              select_all_channels=bool(d.get('select_all_channels')))
    conn.commit()
    pkg = dict(conn.execute("SELECT * FROM content_packages WHERE id=?", (pid,)).fetchone())
    conn.close()
    return jsonify(pkg)


def delete_package(pid: int):
    conn = get_db()
    conn.execute("DELETE FROM content_packages WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def get_my_packages(room_token: str):
    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']

    if room_id:
        rows = conn.execute(
            "SELECT p.* FROM content_packages p "
            "JOIN room_packages rp ON rp.package_id=p.id "
            "WHERE rp.room_id=?",
            (room_id,),
        ).fetchall()
    else:
        rows = []
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── VIP per-channel ───────────────────────────────────────────────────────────

def get_vip_channels(room_id=None):
    conn = get_db()
    if room_id:
        rows = conn.execute(
            "SELECT c.*, vca.room_id "
            "FROM channels c "
            "JOIN vip_channel_access vca ON vca.channel_id=c.id "
            "WHERE vca.room_id=?",
            (int(room_id),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT c.*, vca.room_id "
            "FROM channels c "
            "JOIN vip_channel_access vca ON vca.channel_id=c.id"
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def grant_vip_channel_access(d: dict):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO vip_channel_access (channel_id, room_id) VALUES (?,?)",
        (d['channel_id'], d['room_id']),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def revoke_vip_channel_access(d: dict):
    conn = get_db()
    conn.execute(
        "DELETE FROM vip_channel_access WHERE channel_id=? AND room_id=?",
        (d['channel_id'], d['room_id']),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def get_my_vip_channels(room_token: str):
    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']
    if room_id:
        rows = conn.execute(
            "SELECT c.* FROM channels c "
            "JOIN vip_channel_access vca ON vca.channel_id=c.id "
            "WHERE vca.room_id=?",
            (room_id,),
        ).fetchall()
    else:
        rows = []
    conn.close()
    return jsonify([dict(r) for r in rows])


# ── VIP per-VOD ───────────────────────────────────────────────────────────────

def get_vip_vod(room_id=None):
    conn = get_db()
    if room_id:
        rows = conn.execute(
            "SELECT m.*, vva.room_id "
            "FROM vod_movies m "
            "JOIN vip_vod_access vva ON vva.video_id=m.id "
            "WHERE vva.room_id=?",
            (int(room_id),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT m.*, vva.room_id "
            "FROM vod_movies m "
            "JOIN vip_vod_access vva ON vva.video_id=m.id"
        ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def grant_vip_vod_access(d: dict):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO vip_vod_access (video_id, room_id) VALUES (?,?)",
        (d['vod_id'], d['room_id']),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def revoke_vip_vod_access(d: dict):
    conn = get_db()
    conn.execute(
        "DELETE FROM vip_vod_access WHERE video_id=? AND room_id=?",
        (d['vod_id'], d['room_id']),
    )
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def get_my_vip_vod(room_token: str):
    conn = get_db()
    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']
    if room_id:
        rows = conn.execute(
            "SELECT m.* FROM vod_movies m "
            "JOIN vip_vod_access vva ON vva.video_id=m.id "
            "WHERE vva.room_id=?",
            (room_id,),
        ).fetchall()
    else:
        rows = []
    conn.close()
    return jsonify([dict(r) for r in rows])
