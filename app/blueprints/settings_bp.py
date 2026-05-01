from flask import Blueprint, request
from ..decorators import admin_required
from ..services import settings_service

settings_bp = Blueprint('settings', __name__, url_prefix='/api')


@settings_bp.route('/settings', methods=['GET'])
def get_settings():
    return settings_service.get_settings(
        room_token = request.headers.get('X-Room-Token', '').strip()
    )


@settings_bp.route('/settings/stamp', methods=['GET'])
def get_settings_stamp():
    return settings_service.get_stamp()


@settings_bp.route('/settings', methods=['POST'])
@admin_required
def save_settings():
    return settings_service.save_settings(request.json or {})


@settings_bp.route('/admin/editor-config', methods=['GET'])
@admin_required
def get_editor_config():
    return settings_service.get_editor_config()
