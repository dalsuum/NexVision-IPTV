from flask import Blueprint, request
from ..decorators import admin_required
from ..services import prayer_service

prayer_bp = Blueprint('prayer', __name__, url_prefix='/api/prayer')


@prayer_bp.route('', methods=['GET'])
def get_prayer_times():
    return prayer_service.get_times(
        lat    = request.args.get('lat'),
        lon    = request.args.get('lon'),
        method = request.args.get('method', '3'),
    )


@prayer_bp.route('/settings', methods=['POST'])
@admin_required
def save_prayer_settings():
    return prayer_service.save_settings(request.json or {})
