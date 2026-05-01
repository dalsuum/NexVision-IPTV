from flask import Blueprint, request
from ..decorators import admin_required
from ..services import nav_service

nav_bp = Blueprint('nav', __name__, url_prefix='/api/nav')


@nav_bp.route('', methods=['GET'])
def get_nav():
    return nav_service.get_nav(
        room_token = request.headers.get('X-Room-Token', '').strip()
    )


@nav_bp.route('/items', methods=['GET'])
@admin_required
def get_nav_items_admin():
    return nav_service.list_items_admin()


@nav_bp.route('/items', methods=['POST'])
@admin_required
def create_nav_item():
    return nav_service.create_item(request.json or {})


@nav_bp.route('/items/<int:nid>', methods=['PUT'])
@admin_required
def update_nav_item(nid):
    return nav_service.update_item(nid, request.json or {})


@nav_bp.route('/items/<int:nid>/toggle', methods=['POST'])
@admin_required
def toggle_nav_item(nid):
    return nav_service.toggle_item(nid)


@nav_bp.route('/items/<int:nid>', methods=['DELETE'])
@admin_required
def delete_nav_item(nid):
    return nav_service.delete_item(nid)


@nav_bp.route('/reorder', methods=['POST'])
@admin_required
def reorder_nav():
    return nav_service.reorder((request.json or {}).get('ids', []))


@nav_bp.route('/position', methods=['POST'])
@admin_required
def set_nav_position():
    return nav_service.set_position(request.json or {})
