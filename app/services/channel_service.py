"""
channel_service.py — IPTV channel catalogue business logic.

All DB queries live here; blueprints/channels.py only handles HTTP
request parsing and response serialisation.
"""

import re
import urllib.request
from collections import Counter

from flask import jsonify, Response

from ..extensions import get_db, invalidate_channels, bump_config_stamp


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_int(val, default=0):
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def _parse_m3u(text: str) -> list:
    """Parse M3U/M3U8 playlist text into a list of channel dicts."""
    results = []
    lines = text.replace('\r\n', '\n').replace('\r', '\n').splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF'):
            m_id   = re.search(r'tvg-id="([^"]*)"',      line)
            m_logo = re.search(r'tvg-logo="([^"]*)"',     line)
            m_grp  = re.search(r'group-title="([^"]*)"',  line)
            m_name = re.search(r',(.+)$',                 line)
            url    = lines[i + 1].strip() if i + 1 < len(lines) else ''
            if url and not url.startswith('#'):
                results.append({
                    'name':         m_name.group(1).strip() if m_name  else 'Unknown',
                    'tvg_id':       m_id.group(1)           if m_id    else '',
                    'tvg_logo_url': m_logo.group(1)         if m_logo  else '',
                    'group_title':  m_grp.group(1)          if m_grp   else 'Undefined',
                    'stream_url':   url,
                })
            i += 2
        else:
            i += 1
    return results


# ── Read operations ───────────────────────────────────────────────────────────

def list_channels(group_id=None, active_only='1', search='',
                  limit=500, offset=0, room_token='', envelope=False):
    conn = get_db()
    limit  = _safe_int(limit, 500)
    offset = _safe_int(offset, 0)

    room_id = None
    if room_token:
        row = conn.execute(
            "SELECT id FROM rooms WHERE room_token=?", (room_token,)
        ).fetchone()
        if row:
            room_id = row['id']

    wheres, params = [], []

    if active_only == '1':
        wheres.append('c.active = 1')
    if group_id:
        wheres.append('c.media_group_id = ?')
        params.append(int(group_id))
    if search:
        wheres.append('(c.name LIKE ? OR c.logo LIKE ?)')
        params += [f'%{search}%', f'%{search}%']
    if room_id is not None:
        wheres.append("""(
            EXISTS (
                SELECT 1 FROM package_channels pc
                JOIN room_packages rp ON rp.package_id=pc.package_id
                WHERE pc.channel_id=c.id AND rp.room_id=?
            )
            OR EXISTS (
                SELECT 1 FROM vip_channel_access vca
                WHERE vca.channel_id=c.id AND vca.room_id=?
            )
        )""")
        params += [room_id, room_id]

    base         = ("SELECT c.*, mg.name as group_name "
                    "FROM channels c "
                    "LEFT JOIN media_groups mg ON c.media_group_id = mg.id")
    where_clause = (' WHERE ' + ' AND '.join(wheres)) if wheres else ''
    order_clause = ' ORDER BY COALESCE(c.direct_play_num, 9999), c.id'

    rows = conn.execute(
        base + where_clause + order_clause + ' LIMIT ? OFFSET ?',
        params + [limit, offset],
    ).fetchall()
    channels = [dict(r) for r in rows]

    if envelope:
        total = conn.execute(
            'SELECT COUNT(*) FROM channels c' + where_clause, params
        ).fetchone()[0]
        conn.close()
        return jsonify({'channels': channels, 'total': total,
                        'limit': limit, 'offset': offset})

    conn.close()
    return jsonify(channels)


def get_channel(cid: int):
    conn = get_db()
    ch = conn.execute(
        "SELECT c.*, mg.name as group_name "
        "FROM channels c LEFT JOIN media_groups mg ON c.media_group_id=mg.id "
        "WHERE c.id=?",
        (cid,),
    ).fetchone()
    conn.close()
    if not ch:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(ch))


# ── Write operations ──────────────────────────────────────────────────────────

def create_channel(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO channels "
        "(name, stream_url, logo, tvg_id, tvg_logo_url, group_title, "
        "media_group_id, direct_play_num, active, channel_type) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (d['name'], d['stream_url'], d.get('logo', ''), d.get('tvg_id', ''),
         d.get('tvg_logo_url', ''), d.get('group_title', ''),
         d.get('media_group_id', 1), d.get('direct_play_num'),
         d.get('active', 1), d.get('channel_type', 'stream_udp')),
    )
    conn.commit()
    ch = dict(conn.execute(
        "SELECT * FROM channels WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    invalidate_channels()
    bump_config_stamp()
    return jsonify(ch), 201


def update_channel(cid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE channels SET name=?, stream_url=?, logo=?, tvg_id=?, "
        "tvg_logo_url=?, group_title=?, media_group_id=?, direct_play_num=?, "
        "active=?, temporarily_unavailable=?, channel_type=? WHERE id=?",
        (d['name'], d['stream_url'], d.get('logo', ''), d.get('tvg_id', ''),
         d.get('tvg_logo_url', ''), d.get('group_title', ''),
         d.get('media_group_id', 1), d.get('direct_play_num'),
         d.get('active', 1), d.get('temporarily_unavailable', 0),
         d.get('channel_type', 'stream_udp'), cid),
    )
    conn.commit()
    ch = dict(conn.execute(
        "SELECT * FROM channels WHERE id=?", (cid,)
    ).fetchone())
    conn.close()
    invalidate_channels()
    bump_config_stamp()
    return jsonify(ch)


def delete_channel(cid: int):
    conn = get_db()
    conn.execute("DELETE FROM channels WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    invalidate_channels()
    bump_config_stamp()
    return jsonify({'ok': True})


def bulk_delete(ids: list):
    if not ids:
        return jsonify({'deleted': 0})
    conn = get_db()
    placeholders = ','.join('?' * len(ids))
    conn.execute(f"DELETE FROM channels WHERE id IN ({placeholders})", ids)
    conn.commit()
    conn.close()
    invalidate_channels()
    bump_config_stamp()
    return jsonify({'deleted': len(ids)})


# ── M3U import / export ───────────────────────────────────────────────────────

def preview_m3u(request):
    if request.content_type and 'multipart' in request.content_type:
        f    = request.files.get('file')
        text = f.read().decode('utf-8', errors='replace') if f else ''
    else:
        text = (request.json or {}).get('m3u', '')

    parsed = _parse_m3u(text)
    groups = Counter()
    for ch in parsed:
        for g in ch['group_title'].split(';'):
            groups[g.strip()] += 1
    return jsonify({
        'total':  len(parsed),
        'groups': [{'name': k, 'count': v}
                   for k, v in sorted(groups.items(), key=lambda x: -x[1])],
    })


def import_m3u(request):
    import os
    from ..extensions import BASE_DIR

    if request.content_type and 'multipart' in request.content_type:
        f            = request.files.get('file')
        text         = f.read().decode('utf-8', errors='replace') if f else ''
        mode         = request.form.get('mode', 'append')
        group_filter = request.form.get('group_filter', '').strip()
        max_ch       = _safe_int(request.form.get('max_channels'), 0)
        ctype        = request.form.get('channel_type', 'm3u')
    else:
        body         = request.json or {}
        text         = body.get('m3u', '')
        url          = body.get('url', '').strip()
        mode         = body.get('mode', 'append')
        group_filter = body.get('group_filter', '').strip()
        max_ch       = int(body.get('max_channels', 0) or 0)
        ctype        = body.get('channel_type', 'm3u')

        if url and not text:
            try:
                req2 = urllib.request.Request(url, headers={'User-Agent': 'NexVision/1.0'})
                with urllib.request.urlopen(req2, timeout=30) as resp:
                    text = resp.read().decode('utf-8', errors='replace')
            except Exception as e:
                return jsonify({'error': f'Failed to fetch M3U: {e}'}), 400

        if not text:
            server_m3u = BASE_DIR / 'iptv-org-channels.m3u'
            if server_m3u.exists():
                text = server_m3u.read_text(encoding='utf-8', errors='replace')
            else:
                return jsonify({'error': 'No M3U content provided'}), 400

    channels = _parse_m3u(text)
    if group_filter:
        allowed = {g.strip() for g in group_filter.split(',')}
        channels = [c for c in channels
                    if any(g in allowed for g in c['group_title'].split(';'))]
    if max_ch:
        channels = channels[:max_ch]

    conn = get_db()
    if mode == 'replace':
        conn.execute("DELETE FROM channels")

    inserted = 0
    for ch in channels:
        try:
            conn.execute(
                "INSERT INTO channels (name, stream_url, tvg_id, tvg_logo_url, "
                "group_title, active, channel_type) VALUES (?,?,?,?,?,1,?)",
                (ch['name'], ch['stream_url'], ch['tvg_id'],
                 ch['tvg_logo_url'], ch['group_title'], ctype),
            )
            inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    invalidate_channels()
    bump_config_stamp()
    return jsonify({'inserted': inserted, 'total': len(channels)})


def export_m3u():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM channels WHERE active=1 ORDER BY COALESCE(direct_play_num,9999), id"
    ).fetchall()
    conn.close()

    lines = ['#EXTM3U']
    for ch in rows:
        lines.append(
            f'#EXTINF:-1 tvg-id="{ch["tvg_id"] or ""}" '
            f'tvg-logo="{ch["tvg_logo_url"] or ""}" '
            f'group-title="{ch["group_title"] or ""}",{ch["name"]}'
        )
        lines.append(ch['stream_url'])

    return Response('\n'.join(lines), mimetype='application/x-mpegURL',
                    headers={'Content-Disposition': 'attachment; filename=channels.m3u'})


def bulk_import_csv(request):
    import csv, io
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file'}), 400
    text = f.read().decode('utf-8', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    conn = get_db()
    inserted = 0
    for row in reader:
        try:
            conn.execute(
                "INSERT INTO channels (name, stream_url, logo, group_title, active) "
                "VALUES (?,?,?,?,1)",
                (row.get('name', ''), row.get('stream_url', ''),
                 row.get('logo', ''), row.get('group_title', '')),
            )
            inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    invalidate_channels()
    bump_config_stamp()
    return jsonify({'inserted': inserted})
