from flask import Blueprint, request
from ..decorators import admin_required
from ..services import epg_service

epg_bp = Blueprint('epg', __name__, url_prefix='/api/epg')


@epg_bp.route('', methods=['GET'])
def get_epg():
    return epg_service.get_epg(
        channel_id = request.args.get('channel_id'),
        date       = request.args.get('date'),
    )


@epg_bp.route('', methods=['POST'])
@admin_required
def create_epg():
    return epg_service.create_entry(request.json or {})


@epg_bp.route('/bulk', methods=['POST'])
@admin_required
def bulk_create_epg():
    return epg_service.bulk_create(request.json or {})


@epg_bp.route('/<int:eid>', methods=['PUT'])
@admin_required
def update_epg(eid):
    return epg_service.update_entry(eid, request.json or {})


@epg_bp.route('/<int:eid>', methods=['DELETE'])
@admin_required
def delete_epg(eid):
    return epg_service.delete_entry(eid)


@epg_bp.route('/clear-old', methods=['POST'])
@admin_required
def clear_old_epg():
    return epg_service.clear_old()


@epg_bp.route('/sync-now', methods=['POST'])
@admin_required
def sync_epg_now():
    return epg_service.sync_now(request.json or {})


@epg_bp.route('/generate-guide', methods=['POST'])
@admin_required
def generate_epg_guide():
    return epg_service.generate_guide(request.json or {})


@epg_bp.route('/monitor', methods=['GET'])
@admin_required
def get_epg_monitor():
    return epg_service.get_monitor()
