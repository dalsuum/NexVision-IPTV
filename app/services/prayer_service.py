import json
import urllib.request
from datetime import date
from flask import jsonify
from ..extensions import get_db, cache


def _get_settings() -> dict:
    conn = get_db()
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key LIKE 'prayer%'"
    ).fetchall()
    conn.close()
    return {r['key']: r['value'] for r in rows}


def get_times(lat=None, lon=None, method=None):
    settings = _get_settings()

    if settings.get('prayer_enabled', '1') == '0':
        return jsonify({'enabled': False, 'timings': {}})

    method = method or settings.get('prayer_method', '3')
    today  = date.today().strftime('%d-%m-%Y')

    # Prefer explicit lat/lon, fall back to saved lat/lon, then city/country
    lat = lat or settings.get('prayer_lat')
    lon = lon or settings.get('prayer_lon')
    city    = settings.get('prayer_city')
    country = settings.get('prayer_country')

    if lat and lon:
        cache_key = f'nv:prayer:{lat}:{lon}:{method}'
        url = (
            f'https://api.aladhan.com/v1/timings/{today}'
            f'?latitude={lat}&longitude={lon}&method={method}'
        )
    elif city and country:
        cache_key = f'nv:prayer:{city}:{country}:{method}'
        url = (
            f'https://api.aladhan.com/v1/timingsByCity/{today}'
            f'?city={city}&country={country}&method={method}'
        )
    else:
        return jsonify({'enabled': True, 'timings': {}, 'note': 'location not configured'})

    cached = cache.get(cache_key)
    if cached:
        return jsonify(json.loads(cached))

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'NexVision/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        raw = data.get('data', {}) if isinstance(data.get('data'), dict) else {}
        timings = raw.get('timings', {})
        date_info = raw.get('date', {})
        hijri = date_info.get('hijri', {})
        result = {
            'enabled':    True,
            'city':       city or '',
            'country':    country or '',
            'date':       today,
            'hijri':      hijri.get('date', '') if isinstance(hijri, dict) else '',
            'hijri_month': hijri.get('month', {}).get('en', '') if isinstance(hijri, dict) else '',
            'timings': {
                'Fajr':    timings.get('Fajr',    ''),
                'Sunrise': timings.get('Sunrise', ''),
                'Dhuhr':   timings.get('Dhuhr',   ''),
                'Asr':     timings.get('Asr',     ''),
                'Maghrib': timings.get('Maghrib', ''),
                'Isha':    timings.get('Isha',    ''),
            },
        }
        cache.set(cache_key, json.dumps(result), timeout=3600)
        return jsonify(result)
    except Exception:
        return jsonify({
            'enabled': True,
            'city':    city or '',
            'date':    today,
            'hijri':   '',
            'hijri_month': '',
            'offline': True,
            'timings': {
                'Fajr':    '05:13',
                'Sunrise': '06:33',
                'Dhuhr':   '12:22',
                'Asr':     '15:46',
                'Maghrib': '18:10',
                'Isha':    '19:40',
            },
        })


def save_settings(d: dict):
    old = _get_settings()
    conn = get_db()
    for key in ('prayer_lat', 'prayer_lon', 'prayer_method', 'prayer_enabled',
                'prayer_city', 'prayer_country', 'prayer_notify'):
        if key in d:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                (key, str(d[key])),
            )
    conn.commit()
    conn.close()
    # Bust old and new cache keys so next request fetches fresh times
    for city, country, method in [
        (old.get('prayer_city', ''), old.get('prayer_country', ''), old.get('prayer_method', '3')),
        (d.get('prayer_city', old.get('prayer_city', '')),
         d.get('prayer_country', old.get('prayer_country', '')),
         d.get('prayer_method', old.get('prayer_method', '3'))),
    ]:
        try:
            cache.delete(f'nv:prayer:{city}:{country}:{method}')
        except Exception:
            pass
    return jsonify({'ok': True})
