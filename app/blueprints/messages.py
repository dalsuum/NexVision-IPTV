from flask import Blueprint, request
from ..decorators import admin_required
from ..services import message_service

messages_bp = Blueprint('messages', __name__, url_prefix='/api/messages')


@messages_bp.route('', methods=['GET'])
@admin_required
def get_messages():
    return message_service.list_messages()


@messages_bp.route('/active', methods=['GET'])
def get_active_messages():
    return message_service.get_active(
        room_token = request.headers.get('X-Room-Token', '').strip()
    )


@messages_bp.route('/inbox', methods=['GET'])
def get_message_inbox():
    return message_service.get_inbox(
        room_token = request.headers.get('X-Room-Token', '').strip(),
        limit      = request.args.get('limit', 50),
        offset     = request.args.get('offset', 0),
    )


@messages_bp.route('/unread-count', methods=['GET'])
def get_unread_count():
    return message_service.get_unread_count(
        room_token = request.headers.get('X-Room-Token', '').strip()
    )


@messages_bp.route('', methods=['POST'])
@admin_required
def create_message():
    return message_service.create_message(request.json or {})


@messages_bp.route('/<int:mid>', methods=['PUT'])
@admin_required
def update_message(mid):
    return message_service.update_message(mid, request.json or {})


@messages_bp.route('/<int:mid>', methods=['DELETE'])
@admin_required
def delete_message(mid):
    return message_service.delete_message(mid)


@messages_bp.route('/<int:mid>/dismiss', methods=['POST'])
def dismiss_message(mid):
    return message_service.dismiss_message(
        mid, request.headers.get('X-Room-Token', '').strip()
    )


@messages_bp.route('/<int:mid>/read', methods=['POST'])
def mark_message_read(mid):
    return message_service.mark_read(
        mid, request.headers.get('X-Room-Token', '').strip()
    )


@messages_bp.route('/mark-all-read', methods=['POST'])
def mark_all_messages_read():
    return message_service.mark_all_read(
        request.headers.get('X-Room-Token', '').strip()
    )
