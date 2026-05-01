from flask import Blueprint, request
from ..decorators import admin_required
from ..services import media_group_service

media_groups_bp = Blueprint('media_groups', __name__, url_prefix='/api/media-groups')


@media_groups_bp.route('', methods=['GET'])
def get_media_groups():
    return media_group_service.list_groups()


@media_groups_bp.route('', methods=['POST'])
@admin_required
def create_media_group():
    return media_group_service.create_group(request.json or {})


@media_groups_bp.route('/<int:gid>', methods=['PUT'])
@admin_required
def update_media_group(gid):
    return media_group_service.update_group(gid, request.json or {})


@media_groups_bp.route('/<int:gid>', methods=['DELETE'])
@admin_required
def delete_media_group(gid):
    return media_group_service.delete_group(gid)


@media_groups_bp.route('/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_groups():
    return media_group_service.bulk_delete((request.json or {}).get('ids', []))


@media_groups_bp.route('/bulk-add', methods=['POST'])
@admin_required
def bulk_add_groups():
    return media_group_service.bulk_add((request.json or {}).get('names', []))
