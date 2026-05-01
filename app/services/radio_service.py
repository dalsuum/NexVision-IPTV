from flask import jsonify
from ..extensions import get_db


def list_stations(country=None, genre=None, search='', room_token=''):
    conn = get_db()
    wheres, params = [], []

    if country:
        wheres.append('country=?')
        params.append(country)
    if genre:
        wheres.append('genre=?')
        params.append(genre)
    if search:
        wheres.append('(name LIKE ? OR country LIKE ?)')
        params += [f'%{search}%', f'%{search}%']

    where_clause = (' WHERE ' + ' AND '.join(wheres)) if wheres else ''
    rows = conn.execute(
        f"SELECT * FROM radio_stations{where_clause} ORDER BY name",
        params,
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def list_countries():
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT country FROM radio_stations "
        "WHERE country!='' ORDER BY country"
    ).fetchall()
    conn.close()
    return jsonify([r['country'] for r in rows])


def create_station(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO radio_stations (name, country, genre, stream_url, logo, active) "
        "VALUES (?,?,?,?,?,?)",
        (d['name'], d.get('country', ''), d.get('genre', ''),
         d['stream_url'], d.get('logo', ''), d.get('active', 1)),
    )
    conn.commit()
    s = dict(conn.execute(
        "SELECT * FROM radio_stations WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(s), 201


def update_station(sid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE radio_stations SET name=?, country=?, genre=?, "
        "stream_url=?, logo=?, active=? WHERE id=?",
        (d['name'], d.get('country', ''), d.get('genre', ''),
         d['stream_url'], d.get('logo', ''), d.get('active', 1), sid),
    )
    conn.commit()
    s = dict(conn.execute(
        "SELECT * FROM radio_stations WHERE id=?", (sid,)
    ).fetchone())
    conn.close()
    return jsonify(s)


def delete_station(sid: int):
    conn = get_db()
    conn.execute("DELETE FROM radio_stations WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def bulk_delete(ids: list):
    if not ids:
        return jsonify({'ok': True, 'deleted': 0})
    conn = get_db()
    ph = ','.join('?' * len(ids))
    conn.execute(f"DELETE FROM radio_stations WHERE id IN ({ph})", ids)
    conn.commit()
    conn.close()
    return jsonify({'ok': True, 'deleted': len(ids)})


def bulk_add(d: dict):
    stations = d.get('stations', [])
    conn = get_db()
    added = 0
    for s in stations:
        try:
            conn.execute(
                "INSERT INTO radio_stations (name, stream_url, country, genre) "
                "VALUES (?,?,?,?)",
                (s.get('name', ''), s.get('stream_url', ''),
                 s.get('country', ''), s.get('genre', '')),
            )
            added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return jsonify({'added': added})
