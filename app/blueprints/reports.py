from flask import Blueprint, request
from ..decorators import admin_required
from ..services import report_service

reports_bp = Blueprint('reports', __name__, url_prefix='/api/reports')


@reports_bp.route('/rooms', methods=['GET'])
@admin_required
def report_rooms():
    return report_service.rooms_report(
        limit  = request.args.get('limit', 100),
        offset = request.args.get('offset', 0),
    )


@reports_bp.route('/channels', methods=['GET'])
@admin_required
def report_channels():
    return report_service.channels_report()


@reports_bp.route('/vod', methods=['GET'])
@admin_required
def report_vod():
    return report_service.vod_report()


@reports_bp.route('/radio', methods=['GET'])
@admin_required
def report_radio():
    return report_service.radio_report()


@reports_bp.route('/pages', methods=['GET'])
@admin_required
def report_pages():
    return report_service.pages_report()


@reports_bp.route('/summary', methods=['GET'])
@admin_required
def report_summary():
    return report_service.summary_report(days=request.args.get('days', 7))


@reports_bp.route('/devices', methods=['GET'])
@admin_required
def report_devices():
    return report_service.devices_report()
