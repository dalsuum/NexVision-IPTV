"""Content packages and VIP per-room access grants."""
from flask import Blueprint, request
from ..decorators import admin_required, token_required
from ..services import package_service

packages_bp = Blueprint('packages', __name__)


# ── Content packages (channels + VOD + radio bundles) ─────────────────────────

@packages_bp.route('/api/packages', methods=['GET'])
@admin_required
def list_packages():
    return package_service.list_packages()


@packages_bp.route('/api/packages', methods=['POST'])
@admin_required
def create_package():
    return package_service.create_package(request.json or {})


@packages_bp.route('/api/packages/<int:pid>', methods=['PUT'])
@admin_required
def update_package(pid):
    return package_service.update_package(pid, request.json or {})


@packages_bp.route('/api/packages/<int:pid>', methods=['DELETE'])
@admin_required
def delete_package(pid):
    return package_service.delete_package(pid)


@packages_bp.route('/api/my-packages', methods=['GET'])
def get_my_packages():
    return package_service.get_my_packages(
        request.headers.get('X-Room-Token', '').strip()
    )


# ── VIP per-channel access ─────────────────────────────────────────────────────

@packages_bp.route('/api/vip/channels', methods=['GET'])
@admin_required
def get_vip_channels():
    return package_service.get_vip_channels(request.args.get('room_id'))


@packages_bp.route('/api/vip/access', methods=['POST'])
@admin_required
def grant_vip_access():
    return package_service.grant_vip_channel_access(request.json or {})


@packages_bp.route('/api/vip/access', methods=['DELETE'])
@admin_required
def revoke_vip_access():
    return package_service.revoke_vip_channel_access(request.json or {})


@packages_bp.route('/api/vip/my-channels', methods=['GET'])
def get_my_vip_channels():
    return package_service.get_my_vip_channels(
        request.headers.get('X-Room-Token', '').strip()
    )


# ── VIP per-VOD access ────────────────────────────────────────────────────────

@packages_bp.route('/api/vip/vod', methods=['GET'])
@admin_required
def get_vip_vod():
    return package_service.get_vip_vod(request.args.get('room_id'))


@packages_bp.route('/api/vip/vod-access', methods=['POST'])
@admin_required
def grant_vip_vod_access():
    return package_service.grant_vip_vod_access(request.json or {})


@packages_bp.route('/api/vip/vod-access', methods=['DELETE'])
@admin_required
def revoke_vip_vod_access():
    return package_service.revoke_vip_vod_access(request.json or {})


@packages_bp.route('/api/vip/my-vod', methods=['GET'])
def get_my_vip_vod():
    return package_service.get_my_vip_vod(
        request.headers.get('X-Room-Token', '').strip()
    )
