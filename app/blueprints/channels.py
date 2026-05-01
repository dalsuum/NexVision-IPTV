from flask import Blueprint, request, jsonify
from ..decorators import admin_required
from ..services import channel_service

channels_bp = Blueprint('channels', __name__, url_prefix='/api/channels')


@channels_bp.route('', methods=['GET'])
def get_channels():
    return channel_service.list_channels(
        group_id    = request.args.get('group_id'),
        active_only = request.args.get('active', '1'),
        search      = request.args.get('search', '').strip(),
        limit       = request.args.get('limit', 500),
        offset      = request.args.get('offset', 0),
        room_token  = request.headers.get('X-Room-Token', '').strip(),
        envelope    = request.args.get('envelope') == '1',
    )


@channels_bp.route('/<int:cid>', methods=['GET'])
def get_channel(cid):
    return channel_service.get_channel(cid)


@channels_bp.route('', methods=['POST'])
@admin_required
def create_channel():
    return channel_service.create_channel(request.json or {})


@channels_bp.route('/<int:cid>', methods=['PUT'])
@admin_required
def update_channel(cid):
    return channel_service.update_channel(cid, request.json or {})


@channels_bp.route('/<int:cid>', methods=['DELETE'])
@admin_required
def delete_channel(cid):
    return channel_service.delete_channel(cid)


@channels_bp.route('/preview-m3u', methods=['POST'])
@admin_required
def preview_m3u():
    return channel_service.preview_m3u(request)


@channels_bp.route('/import-m3u', methods=['POST'])
@admin_required
def import_m3u():
    return channel_service.import_m3u(request)


@channels_bp.route('/export-m3u', methods=['GET'])
def export_m3u():
    return channel_service.export_m3u()


@channels_bp.route('/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_channels():
    return channel_service.bulk_delete((request.json or {}).get('ids', []))


@channels_bp.route('/bulk-import-csv', methods=['POST'])
@admin_required
def bulk_import_csv():
    return channel_service.bulk_import_csv(request)
