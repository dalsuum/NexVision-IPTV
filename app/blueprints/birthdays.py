from flask import Blueprint, request
from ..decorators import admin_required
from ..services import birthday_service

birthdays_bp = Blueprint('birthdays', __name__, url_prefix='/api/birthdays')


@birthdays_bp.route('', methods=['GET'])
@admin_required
def get_birthdays():
    return birthday_service.list_birthdays()


@birthdays_bp.route('/today', methods=['GET'])
def get_birthdays_today():
    return birthday_service.get_today()


@birthdays_bp.route('', methods=['POST'])
@admin_required
def create_birthday():
    return birthday_service.create_birthday(request.json or {})


@birthdays_bp.route('/<int:bid>', methods=['PUT'])
@admin_required
def update_birthday(bid):
    return birthday_service.update_birthday(bid, request.json or {})


@birthdays_bp.route('/<int:bid>', methods=['DELETE'])
@admin_required
def delete_birthday(bid):
    return birthday_service.delete_birthday(bid)
