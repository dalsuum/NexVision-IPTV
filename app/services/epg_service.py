"""EPG (Electronic Programme Guide) — schedule entries for channels."""
import threading
import urllib.request
from datetime import datetime, timedelta
from flask import jsonify
from ..extensions import get_db


def get_epg(channel_id=None, date=None):
    conn = get_db()
    wheres, params = [], []

    if channel_id:
        wheres.append('channel_id=?')
        params.append(int(channel_id))
    if date:
        wheres.append('DATE(start_time)=?')
        params.append(date)

    where_clause = (' WHERE ' + ' AND '.join(wheres)) if wheres else ''
    rows = conn.execute(
        f"SELECT * FROM epg_entries{where_clause} ORDER BY start_time",
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
    inserted = 0
    for e in entries:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO epg_entries "
                "(channel_id, title, description, start_time, end_time, category) "
                "VALUES (?,?,?,?,?,?)",
                (e['channel_id'], e.get('title', ''), e.get('description', ''),
                 e['start_time'], e['end_time'], e.get('category', '')),
            )
            inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({'inserted': inserted})


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
            "SELECT value FROM settings WHERE key='epg_url'"
        ).fetchone()
        conn.close()
        url = row['value'] if row else ''

    if not url:
        return jsonify({'error': 'No EPG URL configured'}), 400

    threading.Thread(target=_do_sync, args=(url,), daemon=True).start()
    return jsonify({'status': 'sync started', 'url': url})


def _do_sync(url: str):
    try:
        import xml.etree.ElementTree as ET
        req = urllib.request.Request(url, headers={'User-Agent': 'NexVision/1.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)

        conn = get_db()
        inserted = 0
        for prog in root.findall('programme'):
            channel_id_str = prog.get('channel', '')
            start = prog.get('start', '')
            stop  = prog.get('stop', '')
            title = (prog.findtext('title') or '').strip()
            desc  = (prog.findtext('desc') or '').strip()
            cat   = (prog.findtext('category') or '').strip()

            row = conn.execute(
                "SELECT id FROM channels WHERE tvg_id=?", (channel_id_str,)
            ).fetchone()
            if not row:
                continue
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO epg_entries "
                    "(channel_id, title, description, start_time, end_time, category) "
                    "VALUES (?,?,?,?,?,?)",
                    (row['id'], title, desc, start, stop, cat),
                )
                inserted += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
    except Exception:
        pass


def generate_guide(d: dict):
    """Generate a placeholder EPG guide for all active channels."""
    days = int(d.get('days', 3))
    conn = get_db()
    channels = conn.execute(
        "SELECT id, name FROM channels WHERE active=1"
    ).fetchall()
    inserted = 0
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    for ch in channels:
        for hour_offset in range(days * 24):
            start = now + timedelta(hours=hour_offset)
            end   = start + timedelta(hours=1)
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO epg_entries "
                    "(channel_id, title, start_time, end_time) VALUES (?,?,?,?)",
                    (ch['id'], ch['name'],
                     start.strftime('%Y%m%d%H%M%S +0000'),
                     end.strftime('%Y%m%d%H%M%S +0000')),
                )
                inserted += 1
            except Exception:
                pass
    conn.commit()
    conn.close()
    return jsonify({'inserted': inserted})


def get_monitor():
    conn = get_db()
    data = {
        'total_entries': conn.execute("SELECT COUNT(*) FROM epg_entries").fetchone()[0],
        'future_entries': conn.execute(
            "SELECT COUNT(*) FROM epg_entries WHERE end_time > CURRENT_TIMESTAMP"
        ).fetchone()[0],
        'channels_with_epg': conn.execute(
            "SELECT COUNT(DISTINCT channel_id) FROM epg_entries "
            "WHERE end_time > CURRENT_TIMESTAMP"
        ).fetchone()[0],
    }
    conn.close()
    return jsonify(data)
