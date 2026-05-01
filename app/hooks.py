"""
hooks.py — before_request hooks registered by the app factory.
"""

from flask import request, redirect


_TV_UA_SIGNALS = ('SmartTV', 'SMART-TV', 'HbbTV', 'Tizen', 'WebOS',
                  'NetCast', 'PHILIPS', 'BRAVIA', 'SonyDTV', 'Vizio',
                  'OPR/', 'OculusBrowser', 'CrKey', 'Chromecast')


def register_hooks(app):
    @app.before_request
    def track_room_presence():
        token = request.headers.get('X-Room-Token', '').strip()
        if not token:
            return
        try:
            from .extensions import get_db
            conn = get_db()
            conn.execute(
                "UPDATE rooms SET last_seen=CURRENT_TIMESTAMP, online=1 "
                "WHERE room_token=?",
                (token,)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    @app.before_request
    def redirect_tv_clients():
        if request.path.startswith(('/api/', '/vod/', '/admin', '/tv', '/internal/')):
            return
        ua = request.headers.get('User-Agent', '')
        if 'Android' in ua and any(sig in ua for sig in _TV_UA_SIGNALS):
            return redirect('/tv?platform=tv', 302)
