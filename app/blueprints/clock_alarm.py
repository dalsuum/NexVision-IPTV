from flask import Blueprint, request
from ..decorators import admin_required
from ..services import clock_alarm_service

clock_alarm_bp = Blueprint('clock_alarm', __name__, url_prefix='/api/alarms')


@clock_alarm_bp.route('', methods=['GET'])
@admin_required
def list_alarms():
    return clock_alarm_service.list_all()


@clock_alarm_bp.route('/active', methods=['GET'])
def active_alarms():
    return clock_alarm_service.get_active()


@clock_alarm_bp.route('', methods=['POST'])
@admin_required
def create_alarm():
    return clock_alarm_service.create_alarm(request.json or {})


@clock_alarm_bp.route('/<int:aid>', methods=['PUT'])
@admin_required
def update_alarm(aid):
    return clock_alarm_service.update_alarm(aid, request.json or {})


@clock_alarm_bp.route('/<int:aid>', methods=['DELETE'])
@admin_required
def delete_alarm(aid):
    return clock_alarm_service.delete_alarm(aid)
