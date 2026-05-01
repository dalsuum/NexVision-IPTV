from flask import Blueprint, request
from ..decorators import admin_required
from ..services import content_service

content_bp = Blueprint('content', __name__, url_prefix='/api/content')


@content_bp.route('', methods=['GET'])
def get_content_pages():
    return content_service.list_pages()


@content_bp.route('/<int:pid>', methods=['GET'])
def get_content_page(pid):
    return content_service.get_page(pid)


@content_bp.route('', methods=['POST'])
@admin_required
def create_content_page():
    return content_service.create_page(request.json or {})


@content_bp.route('/<int:pid>', methods=['PUT'])
@admin_required
def update_content_page(pid):
    return content_service.update_page(pid, request.json or {})


@content_bp.route('/<int:pid>', methods=['DELETE'])
@admin_required
def delete_content_page(pid):
    return content_service.delete_page(pid)


@content_bp.route('/<int:pid>/items', methods=['GET'])
def get_content_items(pid):
    return content_service.list_items(pid)


@content_bp.route('/<int:pid>/items', methods=['POST'])
@admin_required
def create_content_item(pid):
    return content_service.create_item(pid, request.json or {})


@content_bp.route('/<int:pid>/items/full', methods=['GET'])
def get_content_items_full(pid):
    return content_service.list_items_full(pid)


@content_bp.route('/items/<int:iid>', methods=['PUT'])
@admin_required
def update_content_item(iid):
    return content_service.update_item(iid, request.json or {})


@content_bp.route('/items/<int:iid>', methods=['DELETE'])
@admin_required
def delete_content_item(iid):
    return content_service.delete_item(iid)


@content_bp.route('/items/<int:iid>/upload', methods=['POST'])
@admin_required
def upload_content_item_image(iid):
    return content_service.upload_item_image(iid, request)


@content_bp.route('/items/<int:iid>/gallery', methods=['GET'])
def get_item_gallery(iid):
    return content_service.get_gallery(iid)


@content_bp.route('/items/<int:iid>/gallery', methods=['POST'])
@admin_required
def add_item_gallery_url(iid):
    return content_service.add_gallery_url(iid, request.json or {})


@content_bp.route('/items/<int:iid>/gallery/upload', methods=['POST'])
@admin_required
def upload_item_gallery_image(iid):
    return content_service.upload_gallery_image(iid, request)


@content_bp.route('/item-images/<int:imgid>', methods=['DELETE'])
@admin_required
def delete_item_gallery_image(imgid):
    return content_service.delete_gallery_image(imgid)


@content_bp.route('/item-images/<int:imgid>', methods=['PATCH'])
@admin_required
def update_item_gallery_image(imgid):
    return content_service.update_gallery_image(imgid, request.json or {})
