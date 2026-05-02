"""VOD series routes — series, seasons, and episodes."""
from flask import Blueprint, request
from ..decorators import admin_required
from ..services import series_service

vod_series_bp = Blueprint('vod_series', __name__, url_prefix='/api/vod/series')


# ── Series ─────────────────────────────────────────────────────────────────────

@vod_series_bp.route('', methods=['GET'])
def get_series_list():
    return series_service.list_series()


@vod_series_bp.route('/admin', methods=['GET'])
@admin_required
def get_series_list_admin():
    return series_service.list_series_admin()


@vod_series_bp.route('/<int:sid>', methods=['GET'])
def get_series(sid):
    return series_service.get_series(sid)


@vod_series_bp.route('', methods=['POST'])
@admin_required
def create_series():
    return series_service.create_series(request.json or {})


@vod_series_bp.route('/<int:sid>', methods=['PUT'])
@admin_required
def update_series(sid):
    return series_service.update_series(sid, request.json or {})


@vod_series_bp.route('/<int:sid>', methods=['DELETE'])
@admin_required
def delete_series(sid):
    return series_service.delete_series(sid)


# ── Seasons ────────────────────────────────────────────────────────────────────

@vod_series_bp.route('/<int:sid>/seasons', methods=['POST'])
@admin_required
def create_season(sid):
    return series_service.create_season(sid, request.json or {})


@vod_series_bp.route('/seasons/<int:ssid>', methods=['GET'])
def get_season_episodes(ssid):
    return series_service.get_season_episodes(ssid)


@vod_series_bp.route('/seasons/<int:ssid>', methods=['PUT'])
@admin_required
def update_season(ssid):
    return series_service.update_season(ssid, request.json or {})


@vod_series_bp.route('/seasons/<int:ssid>', methods=['DELETE'])
@admin_required
def delete_season(ssid):
    return series_service.delete_season(ssid)


# ── Episodes ───────────────────────────────────────────────────────────────────

@vod_series_bp.route('/seasons/<int:ssid>/episodes', methods=['POST'])
@admin_required
def create_episode(ssid):
    return series_service.create_episode(ssid, request.json or {})


@vod_series_bp.route('/episodes/<int:eid>', methods=['PUT'])
@admin_required
def update_episode(eid):
    return series_service.update_episode(eid, request.json or {})


@vod_series_bp.route('/episodes/<int:eid>', methods=['DELETE'])
@admin_required
def delete_episode(eid):
    return series_service.delete_episode(eid)
