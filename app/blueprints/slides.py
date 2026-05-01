from flask import Blueprint, request
from ..decorators import admin_required
from ..services import slide_service

slides_bp = Blueprint('slides', __name__, url_prefix='/api/slides')


@slides_bp.route('', methods=['GET'])
def get_slides_public():
    return slide_service.get_public(
        room_token = request.headers.get('X-Room-Token', '').strip()
    )


@slides_bp.route('/all', methods=['GET'])
@admin_required
def get_slides_all():
    return slide_service.list_all()


@slides_bp.route('', methods=['POST'])
@admin_required
def create_slide():
    return slide_service.create_slide(request.json or {})


@slides_bp.route('/<int:sid>', methods=['PUT'])
@admin_required
def update_slide(sid):
    return slide_service.update_slide(sid, request.json or {})


@slides_bp.route('/<int:sid>', methods=['DELETE'])
@admin_required
def delete_slide(sid):
    return slide_service.delete_slide(sid)


@slides_bp.route('/reorder', methods=['POST'])
@admin_required
def reorder_slides():
    return slide_service.reorder((request.json or {}).get('ids', []))
