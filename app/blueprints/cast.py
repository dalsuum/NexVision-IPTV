from flask import Blueprint, request
from ..services import cast_service

cast_bp = Blueprint('cast', __name__)


@cast_bp.route('/api/cast/session', methods=['POST'])
def cast_session_start():
    return cast_service.start_session(request.json or {})


@cast_bp.route('/api/cast/session/<int:session_id>', methods=['PATCH'])
def cast_session_end(session_id):
    return cast_service.end_session(session_id, request.json or {})
