from flask import Blueprint, request
from ..decorators import admin_required
from ..services import skin_service

skins_bp = Blueprint('skins', __name__, url_prefix='/api')


@skins_bp.route('/skins', methods=['GET'])
@admin_required
def get_skins():
    return skin_service.list_skins()


@skins_bp.route('/skins', methods=['POST'])
@admin_required
def create_skin():
    return skin_service.create_skin(request.json or {})


@skins_bp.route('/skin', methods=['GET'])
def get_room_skin():
    return skin_service.get_room_skin(
        request.headers.get('X-Room-Token', '').strip()
    )


@skins_bp.route('/skins/<int:sid>', methods=['PUT'])
@admin_required
def update_skin(sid):
    return skin_service.update_skin(sid, request.json or {})


@skins_bp.route('/skins/<int:sid>', methods=['DELETE'])
@admin_required
def delete_skin(sid):
    return skin_service.delete_skin(sid)
