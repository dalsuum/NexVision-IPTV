from flask import Blueprint, request
from ..decorators import admin_required
from ..services import user_service

users_bp = Blueprint('users', __name__, url_prefix='/api/users')


@users_bp.route('', methods=['GET'])
@admin_required
def get_users():
    return user_service.list_users()


@users_bp.route('', methods=['POST'])
@admin_required
def create_user():
    return user_service.create_user(request.json or {})


@users_bp.route('/<int:uid>', methods=['DELETE'])
@admin_required
def delete_user(uid):
    return user_service.delete_user(uid)
