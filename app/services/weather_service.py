import json
import urllib.request
import urllib.parse
from datetime import datetime
from flask import jsonify
from ..extensions import cache, TTL_WEATHER, get_db

_WMO = {
    0:  ('☀️',  'Clear sky'),
    1:  ('🌤️', 'Mainly clear'),
    2:  ('⛅',  'Partly cloudy'),
    3:  ('☁️',  'Overcast'),
    45: ('🌫️', 'Foggy'),
    48: ('🌫️', 'Icy fog'),
    51: ('🌦️', 'Light drizzle'),
    53: ('🌦️', 'Drizzle'),
    55: ('🌧️', 'Heavy drizzle'),
    61: ('🌧️', 'Light rain'),
    63: ('🌧️', 'Rain'),
    65: ('🌧️', 'Heavy rain'),
    71: ('❄️',  'Light snow'),
    73: ('❄️',  'Snow'),
    75: ('❄️',  'Heavy snow'),
    77: ('❄️',  'Snow grains'),
    80: ('🌦️', 'Light showers'),
    81: ('🌧️', 'Showers'),
    82: ('🌧️', 'Heavy showers'),
    85: ('🌨️', 'Snow showers'),
    86: ('🌨️', 'Heavy snow showers'),
    95: ('⛈️',  'Thunderstorm'),
    96: ('⛈️',  'Thunderstorm w/ hail'),
    99: ('⛈️',  'Thunderstorm w/ heavy hail'),
}

_DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']


def _get_settings() -> dict:
    conn = get_db()
    rows = conn.execute(
        "SELECT key, value FROM settings WHERE key LIKE 'weather%'"
    ).fetchall()
    conn.close()
    return {r['key']: r['value'] for r in rows}


def get_weather(lat=None, lon=None, city=None):
    settings = _get_settings()

    lat  = lat  or settings.get('weather_lat')
    lon  = lon  or settings.get('weather_lon')
    city = city or settings.get('weather_city')

    if not lat and not city:
        return jsonify({'enabled': False, 'note': 'weather location not configured'})

    cache_key = f'nv:weather:{lat}:{lon}:{city}'
    cached = cache.get(cache_key)
    if cached:
        return jsonify(json.loads(cached))

    try:
        # Resolve city → lat/lon via Nominatim if needed
        if not (lat and lon):
            geo_url = (
                f'https://nominatim.openstreetmap.org/search'
                f'?q={urllib.parse.quote(city)}&format=json&limit=1'
            )
            req = urllib.request.Request(geo_url, headers={'User-Agent': 'NexVision/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                geo = json.loads(resp.read())
            if not geo:
                return jsonify({'error': 'City not found'}), 404
            lat, lon = geo[0]['lat'], geo[0]['lon']

        # Fetch current conditions + 7-day forecast from Open-Meteo
        url = (
            f'https://api.open-meteo.com/v1/forecast'
            f'?latitude={lat}&longitude={lon}'
            f'&current=temperature_2m,relative_humidity_2m,apparent_temperature,'
            f'weather_code,wind_speed_10m,uv_index'
            f'&daily=weather_code,temperature_2m_max,temperature_2m_min'
            f'&forecast_days=7&timezone=auto'
        )
        req2 = urllib.request.Request(url, headers={'User-Agent': 'NexVision/1.0'})
        with urllib.request.urlopen(req2, timeout=10) as resp:
            data = json.loads(resp.read())

        cur  = data.get('current', {})
        code = int(cur.get('weather_code', 0))
        icon, condition = _WMO.get(code, ('🌡️', 'Unknown'))

        # Build 7-day forecast array
        daily      = data.get('daily', {})
        dates      = daily.get('time', [])
        d_codes    = daily.get('weather_code', [])
        d_highs    = daily.get('temperature_2m_max', [])
        d_lows     = daily.get('temperature_2m_min', [])
        forecast = []
        for i, d in enumerate(dates):
            try:
                # weekday() returns 0=Mon…6=Sun; _DAYS is Sun-indexed, so shift by +1
                wd  = datetime.strptime(d, '%Y-%m-%d').weekday()
                dow = _DAYS[(wd + 1) % 7]
            except Exception:
                dow = d
            fc_code = int(d_codes[i]) if i < len(d_codes) else 0
            fc_icon, fc_cond = _WMO.get(fc_code, ('🌡️', 'Unknown'))
            forecast.append({
                'day':       dow,
                'icon':      fc_icon,
                'condition': fc_cond,
                'high':      round(d_highs[i]) if i < len(d_highs) else '--',
                'low':       round(d_lows[i])  if i < len(d_lows)  else '--',
            })

        result = {
            'enabled':      True,
            'icon':         icon,
            'condition':    condition,
            'temperature':  round(cur.get('temperature_2m', 0)),
            'feels_like':   round(cur.get('apparent_temperature', 0)),
            'humidity':     round(cur.get('relative_humidity_2m', 0)),
            'wind_speed':   round(cur.get('wind_speed_10m', 0)),
            'uv_index':     round(cur.get('uv_index', 0)),
            'city':         city or '',
            'last_updated': cur.get('time', '').replace('T', ' '),
            'forecast':     forecast,
        }
        cache.set(cache_key, json.dumps(result), timeout=TTL_WEATHER)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 502