from flask import Blueprint, request
from ..decorators import admin_required
from ..services import room_service

rooms_bp = Blueprint('rooms', __name__, url_prefix='/api/rooms')


@rooms_bp.route('', methods=['GET'])
@admin_required
def get_rooms():
    return room_service.list_rooms(
        search = request.args.get('search', '').strip(),
        limit  = request.args.get('limit', 500),
        offset = request.args.get('offset', 0),
    )


@rooms_bp.route('', methods=['POST'])
@admin_required
def create_room():
    return room_service.create_room(request.json or {})


@rooms_bp.route('/<int:rid>', methods=['PUT'])
@admin_required
def update_room(rid):
    return room_service.update_room(rid, request.json or {})


@rooms_bp.route('/<int:rid>', methods=['DELETE'])
@admin_required
def delete_room(rid):
    return room_service.delete_room(rid)


@rooms_bp.route('/<int:rid>/token', methods=['POST'])
@admin_required
def regenerate_token(rid):
    return room_service.regenerate_token(rid)


@rooms_bp.route('/setup/<token>', methods=['GET'])
def room_setup(token):
    return room_service.room_setup(token)


@rooms_bp.route('/register', methods=['POST'])
def room_register():
    return room_service.room_register(request.json or {}, request.headers.get('User-Agent', ''))


@rooms_bp.route('/<int:rid>/packages', methods=['GET'])
def get_room_packages(rid):
    return room_service.get_room_packages(rid)


@rooms_bp.route('/<int:rid>/packages', methods=['POST'])
@admin_required
def set_room_packages(rid):
    return room_service.set_room_packages(rid, request.json or {})


@rooms_bp.route('/packages-map', methods=['GET'])
@admin_required
def get_rooms_packages_map():
    return room_service.get_rooms_packages_map()


@rooms_bp.route('/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_rooms():
    return room_service.bulk_delete((request.json or {}).get('ids', []))


@rooms_bp.route('/bulk-add', methods=['POST'])
@admin_required
def bulk_add_rooms():
    return room_service.bulk_add(request.json or {})
