from flask import Blueprint, request
from ..decorators import admin_required
from ..services import device_service

devices_bp = Blueprint('devices', __name__, url_prefix='/api')


@devices_bp.route('/device/heartbeat', methods=['POST'])
def device_heartbeat():
    return device_service.heartbeat(request.json or {}, request.headers.get('User-Agent', ''))


@devices_bp.route('/devices', methods=['GET'])
@admin_required
def get_devices():
    return device_service.list_devices(
        limit  = request.args.get('limit', 100),
        offset = request.args.get('offset', 0),
    )
