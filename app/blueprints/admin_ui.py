"""Serves the static Admin CMS and Cast Receiver HTML shells."""
from flask import Blueprint, send_from_directory, redirect
from ..config import ADMIN_DIR, CAST_DIR, TV_DIR

admin_ui_bp = Blueprint('admin_ui', __name__)


@admin_ui_bp.route('/admin')
def redirect_admin():
    return redirect('/admin/', 301)


@admin_ui_bp.route('/admin/')
def serve_admin():
    return send_from_directory(str(ADMIN_DIR), 'index.html')


@admin_ui_bp.route('/admin/<path:filename>')
def serve_admin_static(filename):
    return send_from_directory(str(ADMIN_DIR), filename)


@admin_ui_bp.route('/cast-receiver')
def serve_cast_receiver():
    return send_from_directory(str(CAST_DIR), 'receiver.html')


@admin_ui_bp.route('/cast-receiver/<path:filename>')
def serve_cast_static(filename):
    return send_from_directory(str(CAST_DIR), filename)


@admin_ui_bp.route('/', defaults={'path': ''})
@admin_ui_bp.route('/<path:path>')
def serve_tv(path):
    # Never serve HTML for API paths — return 404 so JS gets an error, not a page.
    if path.startswith('api/') or path.startswith('vod/api/'):
        from flask import abort
        abort(404)
    from ..services import tv_service
    return tv_service.serve(path, request_obj=None)
