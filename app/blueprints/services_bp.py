"""Hotel services (room service, spa, etc.) — different from Python services layer."""
from flask import Blueprint, request
from ..decorators import admin_required
from ..services import hotel_service

services_bp = Blueprint('hotel_services', __name__, url_prefix='/api/services')


@services_bp.route('', methods=['GET'])
def get_services():
    return hotel_service.get_active(
        room_token = request.headers.get('X-Room-Token', '').strip()
    )


@services_bp.route('/all', methods=['GET'])
@admin_required
def get_all_services():
    return hotel_service.list_all()


@services_bp.route('', methods=['POST'])
@admin_required
def create_service():
    return hotel_service.create_service(request.json or {})


@services_bp.route('/<int:sid>', methods=['PUT'])
@admin_required
def update_service(sid):
    return hotel_service.update_service(sid, request.json or {})


@services_bp.route('/<int:sid>', methods=['DELETE'])
@admin_required
def delete_service(sid):
    return hotel_service.delete_service(sid)


@services_bp.route('/reorder', methods=['POST'])
@admin_required
def reorder_services():
    return hotel_service.reorder((request.json or {}).get('ids', []))


@services_bp.route('/<int:sid>/upload', methods=['POST'])
@admin_required
def upload_service_image(sid):
    return hotel_service.upload_image(sid, request)
