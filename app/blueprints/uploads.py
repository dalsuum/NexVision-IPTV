from flask import Blueprint, request, send_from_directory
from ..decorators import admin_required
from ..config import UPLOAD_DIR
from ..services import upload_service

uploads_bp = Blueprint('uploads', __name__)


@uploads_bp.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


@uploads_bp.route('/api/upload', methods=['POST'])
@admin_required
def upload_file():
    return upload_service.upload(request)


@uploads_bp.route('/api/watch-event', methods=['POST'])
def record_watch_event():
    return upload_service.record_watch_event(request.json or {})
