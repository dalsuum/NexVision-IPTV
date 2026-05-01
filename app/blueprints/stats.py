from flask import Blueprint, request
from ..decorators import admin_required
from ..services import stat_service

stats_bp = Blueprint('stats', __name__, url_prefix='/api/stats')


@stats_bp.route('/overview', methods=['GET'])
@admin_required
def stats_overview():
    return stat_service.overview()


@stats_bp.route('/channels', methods=['GET'])
@admin_required
def stats_channels():
    return stat_service.channels_stats(
        limit = request.args.get('limit', 10),
    )


@stats_bp.route('/rooms', methods=['GET'])
@admin_required
def stats_rooms():
    return stat_service.rooms_stats(
        limit = request.args.get('limit', 10),
    )
