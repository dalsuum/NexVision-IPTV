import json
import urllib.request
import xml.etree.ElementTree as ET
from flask import jsonify
from ..extensions import get_db, cache, TTL_RSS, invalidate_rss, bump_config_stamp


def list_feeds():
    conn = get_db()
    rows = conn.execute("SELECT * FROM rss_feeds ORDER BY sort_order, id").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def get_public_feeds():
    cached = cache.get('nv:rss_public')
    if cached:
        return jsonify(json.loads(cached))

    conn = get_db()
    feeds = conn.execute(
        "SELECT * FROM rss_feeds WHERE active=1 ORDER BY sort_order, id"
    ).fetchall()
    conn.close()

    result = []
    for feed in feeds:
        items = _fetch_feed(feed['url'], limit=feed['refresh_minutes'] or 10)
        result.append({**dict(feed), 'items': items})

    cache.set('nv:rss_public', json.dumps(result), timeout=TTL_RSS)
    return jsonify(result)


def _fetch_feed(url: str, limit: int = 10) -> list:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'NexVision/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_text = resp.read()
        root = ET.fromstring(xml_text)
        channel = root.find('channel')
        if channel is None:
            return []
        items = []
        for item in channel.findall('item')[:limit]:
            items.append({
                'title':       (item.findtext('title') or '').strip(),
                'description': (item.findtext('description') or '').strip(),
                'link':        (item.findtext('link') or '').strip(),
                'pubDate':     (item.findtext('pubDate') or '').strip(),
            })
        return items
    except Exception:
        return []


def create_feed(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO rss_feeds (title, url, type, active, refresh_minutes, "
        "text_color, bg_color, bg_opacity) VALUES (?,?,?,?,?,?,?,?)",
        (d['title'], d['url'], d.get('type', 'normal'), d.get('active', 1),
         d.get('refresh_minutes', 15), d.get('text_color', '#ffffff'),
         d.get('bg_color', '#09090f'), d.get('bg_opacity', 92)),
    )
    conn.commit()
    feed = dict(conn.execute(
        "SELECT * FROM rss_feeds WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    invalidate_rss()
    bump_config_stamp()
    return jsonify(feed), 201


def update_feed(fid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE rss_feeds SET title=?, url=?, type=?, active=?, "
        "refresh_minutes=?, text_color=?, bg_color=?, bg_opacity=? WHERE id=?",
        (d['title'], d['url'], d.get('type', 'normal'), d.get('active', 1),
         d.get('refresh_minutes', 15), d.get('text_color', '#ffffff'),
         d.get('bg_color', '#09090f'), d.get('bg_opacity', 92), fid),
    )
    conn.commit()
    feed = dict(conn.execute(
        "SELECT * FROM rss_feeds WHERE id=?", (fid,)
    ).fetchone())
    conn.close()
    invalidate_rss()
    bump_config_stamp()
    return jsonify(feed)


def delete_feed(fid: int):
    conn = get_db()
    conn.execute("DELETE FROM rss_feeds WHERE id=?", (fid,))
    conn.commit()
    conn.close()
    invalidate_rss()
    bump_config_stamp()
    return jsonify({'ok': True})
