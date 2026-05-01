"""VOD metadata routes — IPTV movie catalogue (not the streaming server)."""
from flask import Blueprint, request
from ..decorators import admin_required
from ..services import vod_service

vod_api_bp = Blueprint('vod_api', __name__, url_prefix='/api/vod')


@vod_api_bp.route('', methods=['GET'])
def get_vod():
    return vod_service.list_movies(
        genre       = request.args.get('genre'),
        search      = request.args.get('search', '').strip(),
        package_id  = request.args.get('package_id'),
        limit       = request.args.get('limit', 100),
        offset      = request.args.get('offset', 0),
        room_token  = request.headers.get('X-Room-Token', '').strip(),
    )


@vod_api_bp.route('/<int:mid>', methods=['GET'])
def get_movie(mid):
    return vod_service.get_movie(mid)


@vod_api_bp.route('', methods=['POST'])
@admin_required
def create_movie():
    return vod_service.create_movie(request.json or {})


@vod_api_bp.route('/<int:mid>', methods=['PUT'])
@admin_required
def update_movie(mid):
    return vod_service.update_movie(mid, request.json or {})


@vod_api_bp.route('/<int:mid>', methods=['DELETE'])
@admin_required
def delete_movie(mid):
    return vod_service.delete_movie(mid)


@vod_api_bp.route('/genres', methods=['GET'])
def get_genres():
    return vod_service.list_genres()


@vod_api_bp.route('/packages', methods=['GET'])
def get_packages():
    return vod_service.list_packages()


@vod_api_bp.route('/packages', methods=['POST'])
@admin_required
def create_package():
    return vod_service.create_package(request.json or {})


@vod_api_bp.route('/packages/all', methods=['GET'])
@admin_required
def get_all_packages():
    return vod_service.list_all_packages()


@vod_api_bp.route('/packages/<int:pid>', methods=['PUT'])
@admin_required
def update_package(pid):
    return vod_service.update_package(pid, request.json or {})


@vod_api_bp.route('/packages/<int:pid>', methods=['DELETE'])
@admin_required
def delete_package(pid):
    return vod_service.delete_package(pid)


@vod_api_bp.route('/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_vod():
    return vod_service.bulk_delete((request.json or {}).get('ids', []))


@vod_api_bp.route('/bulk-add', methods=['POST'])
@admin_required
def bulk_add_vod():
    return vod_service.bulk_add(request.json or {})


@vod_api_bp.route('/packages/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_packages():
    return vod_service.bulk_delete_packages((request.json or {}).get('ids', []))


@vod_api_bp.route('/packages/bulk-add', methods=['POST'])
@admin_required
def bulk_add_packages():
    return vod_service.bulk_add_packages(request.json or {})
