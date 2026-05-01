from flask import Blueprint, request, jsonify
from ..decorators import token_required
from ..services import auth_service

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/login', methods=['POST'])
def login():
    d = request.json or {}
    return auth_service.login(d.get('username', ''), d.get('password', ''))


@auth_bp.route('/me', methods=['GET'])
@token_required
def me():
    return jsonify(request.user)
