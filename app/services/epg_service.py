"""EPG (Electronic Programme Guide) — schedule entries for channels."""
import os
import threading
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from flask import jsonify
from ..extensions import get_db


def get_epg(channel_id=None, date=None, hours=None):
    conn = get_db()
    wheres, params = [], []

    # Default to next 48 hours if no date filter specified
    h = 48
    try:
        h = int(hours) if hours is not None else 48
    except (ValueError, TypeError):
        pass

    if channel_id:
        wheres.append('e.channel_id=?')
        params.append(int(channel_id))
        if not date:
            wheres.append("REPLACE(e.end_time,'T',' ') >= datetime('now')")
            wheres.append(f"REPLACE(e.start_time,'T',' ') <= datetime('now','+{h} hours')")
    else:
        if date:
            wheres.append('DATE(e.start_time)=?')
            params.append(date)
        else:
            wheres.append("REPLACE(e.end_time,'T',' ') >= datetime('now')")
            wheres.append(f"REPLACE(e.start_time,'T',' ') <= datetime('now','+{h} hours')")

    where_clause = (' WHERE ' + ' AND '.join(wheres)) if wheres else ''
    rows = conn.execute(
        f"SELECT e.*, c.name as channel_name FROM epg_entries e"
        f" JOIN channels c ON c.id=e.channel_id"
        f"{where_clause} ORDER BY e.channel_id, e.start_time",
        params,
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_entry(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO epg_entries (channel_id, title, description, "
        "start_time, end_time, category) VALUES (?,?,?,?,?,?)",
        (d['channel_id'], d.get('title', ''), d.get('description', ''),
         d['start_time'], d['end_time'], d.get('category', '')),
    )
    conn.commit()
    entry = dict(conn.execute(
        "SELECT * FROM epg_entries WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(entry), 201


def bulk_create(d: dict):
    entries = d.get('entries', [])
    conn = get_db()
    added = 0
    for e in entries:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO epg_entries "
                "(channel_id, title, description, start_time, end_time, category) "
                "VALUES (?,?,?,?,?,?)",
                (e['channel_id'], e.get('title', ''), e.get('description', ''),
                 e['start_time'], e['end_time'], e.get('category', '')),
            )
            added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'added': added})


def update_entry(eid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE epg_entries SET title=?, description=?, "
        "start_time=?, end_time=?, category=? WHERE id=?",
        (d.get('title', ''), d.get('description', ''),
         d['start_time'], d['end_time'], d.get('category', ''), eid),
    )
    conn.commit()
    entry = dict(conn.execute(
        "SELECT * FROM epg_entries WHERE id=?", (eid,)
    ).fetchone())
    conn.close()
    return jsonify(entry)


def delete_entry(eid: int):
    conn = get_db()
    conn.execute("DELETE FROM epg_entries WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def clear_old():
    conn = get_db()
    result = conn.execute(
        "DELETE FROM epg_entries WHERE end_time < datetime('now','-1 day')"
    )
    deleted = result.rowcount
    conn.commit()
    conn.close()
    return jsonify({'deleted': deleted})


def sync_now(d: dict):
    """Trigger an async EPG sync from configured XMLTV/M3U sources."""
    url = d.get('url', '').strip()
    if not url:
        conn = get_db()
        row = conn.execute(
            "SELECT value FROM settings WHERE key='epg_auto_url'"
        ).fetchone()
        conn.close()
        url = row['value'] if row else ''

    if not url:
        return jsonify({'error': 'No EPG URL configured'}), 400

    threading.Thread(target=_do_sync, args=(url,), daemon=True).start()
    return jsonify({'status': 'sync started', 'url': url})


def _do_sync(url: str):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'NexVision/1.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)

        # Build channel maps from XML display-name elements
        xml_channel_names = {}
        for ch_elem in root.findall('.//channel'):
            ch_id = ch_elem.get('id', '').strip()
            dn = ch_elem.findtext('display-name', '').strip()
            if ch_id and dn:
                xml_channel_names[ch_id] = dn

        conn = get_db()
        tvg_map, name_map, id_map = {}, {}, {}
        for row in conn.execute("SELECT id, tvg_id, name FROM channels").fetchall():
            if row['tvg_id']:
                tvg_map[row['tvg_id'].strip()] = row['id']
            if row['name']:
                name_map[row['name'].strip().lower()] = row['id']
            id_map[row['id']] = row['id']

        entries = []
        for prog in root.findall('.//programme'):
            channel_id_str = prog.get('channel', '').strip()
            start = prog.get('start', '').strip()
            stop  = prog.get('stop', '').strip()
            title = (prog.findtext('title') or '').strip()
            desc  = (prog.findtext('desc') or '').strip()
            cat   = (prog.findtext('category') or '').strip()

            if not (channel_id_str and title and start and stop):
                continue

            ch_id = tvg_map.get(channel_id_str)
            if not ch_id and 'nexvision-' in channel_id_str:
                try:
                    ch_id = id_map.get(int(channel_id_str.replace('nexvision-', '')))
                except ValueError:
                    pass
            if not ch_id:
                dn = xml_channel_names.get(channel_id_str, '').strip().lower()
                if dn:
                    ch_id = name_map.get(dn)

            if ch_id:
                entries.append((ch_id, title, desc, start, stop, cat))

        conn.execute("DELETE FROM epg_entries WHERE end_time < datetime('now','-1 day')")
        conn.executemany(
            "INSERT OR REPLACE INTO epg_entries "
            "(channel_id, title, description, start_time, end_time, category) "
            "VALUES (?,?,?,?,?,?)",
            entries,
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def generate_guide(d: dict):
    """Generate guide.xml from database EPG entries."""
    days = int(d.get('days', 2))
    path = d.get('path', '/opt/nexvision/epg/public/guide.xml').strip()

    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT e.channel_id, c.name, e.title, e.description, e.start_time, e.end_time"
            " FROM epg_entries e JOIN channels c ON c.id=e.channel_id"
            " WHERE e.end_time > datetime('now','-1 day')"
            " ORDER BY e.channel_id, e.start_time"
        ).fetchall()
        conn.close()

        tv = ET.Element('tv', {'generator-info-name': 'NexVision'})
        seen_channels = {}
        for row in rows:
            ch_id = row['channel_id']
            if ch_id not in seen_channels:
                seen_channels[ch_id] = row['name']
                ch = ET.SubElement(tv, 'channel', {'id': f'nexvision-{ch_id}'})
                ET.SubElement(ch, 'display-name').text = row['name']

        for row in rows:
            prog = ET.SubElement(tv, 'programme', {
                'channel': f'nexvision-{row["channel_id"]}',
                'start': str(row['start_time']).replace(' ', '').replace('-', '').replace(':', ''),
                'stop':  str(row['end_time']).replace(' ', '').replace('-', '').replace(':', ''),
            })
            ET.SubElement(prog, 'title').text = row['title']
            if row['description']:
                ET.SubElement(prog, 'desc').text = row['description']

        out_dir = os.path.dirname(path) or '.'
        try:
            os.makedirs(out_dir, exist_ok=True)
            ET.ElementTree(tv).write(path, encoding='UTF-8', xml_declaration=True)
        except PermissionError:
            path = '/opt/nexvision/epg/public/guide.xml'
            os.makedirs('/opt/nexvision/epg/public', exist_ok=True)
            ET.ElementTree(tv).write(path, encoding='UTF-8', xml_declaration=True)

        size = os.path.getsize(path)
        return jsonify({'path': path, 'size_bytes': size})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def get_monitor():
    conn = get_db()
    settings = {}
    for row in conn.execute(
        "SELECT key, value FROM settings WHERE key LIKE 'epg_%'"
    ).fetchall():
        settings[row['key'].replace('epg_', '')] = row['value']
    conn.close()

    return jsonify({
        'auto_url': settings.get('auto_url', ''),
        'auto_enabled': int(settings.get('auto_enabled', 0)),
        'auto_interval_minutes': int(settings.get('auto_interval_minutes', 360)),
        'last_sync_at': settings.get('last_sync_at', 'Never'),
        'last_message': settings.get('last_message', ''),
        'last_status': settings.get('last_status', ''),
        'last_imported': int(settings.get('last_imported', 0)),
        'last_parsed': int(settings.get('last_parsed', 0)),
        'last_unmatched': int(settings.get('last_unmatched', 0)),
        'last_duration_ms': settings.get('last_duration_ms', ''),
    })
