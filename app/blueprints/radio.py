from flask import Blueprint, request
from ..decorators import admin_required
from ..services import radio_service

radio_bp = Blueprint('radio', __name__, url_prefix='/api/radio')


@radio_bp.route('', methods=['GET'])
def get_radio():
    return radio_service.list_stations(
        country    = request.args.get('country'),
        genre      = request.args.get('genre'),
        search     = request.args.get('search', '').strip(),
        room_token = request.headers.get('X-Room-Token', '').strip(),
    )


@radio_bp.route('/countries', methods=['GET'])
def get_radio_countries():
    return radio_service.list_countries()


@radio_bp.route('', methods=['POST'])
@admin_required
def create_station():
    return radio_service.create_station(request.json or {})


@radio_bp.route('/<int:sid>', methods=['PUT'])
@admin_required
def update_station(sid):
    return radio_service.update_station(sid, request.json or {})


@radio_bp.route('/<int:sid>', methods=['DELETE'])
@admin_required
def delete_station(sid):
    return radio_service.delete_station(sid)


@radio_bp.route('/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_radio():
    return radio_service.bulk_delete((request.json or {}).get('ids', []))


@radio_bp.route('/bulk-add', methods=['POST'])
@admin_required
def bulk_add_radio():
    return radio_service.bulk_add(request.json or {})
