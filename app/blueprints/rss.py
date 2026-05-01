from flask import Blueprint, request
from ..decorators import admin_required
from ..services import rss_service

rss_bp = Blueprint('rss', __name__, url_prefix='/api/rss')


@rss_bp.route('', methods=['GET'])
@admin_required
def get_rss_feeds():
    return rss_service.list_feeds()


@rss_bp.route('/public', methods=['GET'])
def get_rss_feeds_public():
    return rss_service.get_public_feeds()


@rss_bp.route('', methods=['POST'])
@admin_required
def create_rss_feed():
    return rss_service.create_feed(request.json or {})


@rss_bp.route('/<int:fid>', methods=['PUT'])
@admin_required
def update_rss_feed(fid):
    return rss_service.update_feed(fid, request.json or {})


@rss_bp.route('/<int:fid>', methods=['DELETE'])
@admin_required
def delete_rss_feed(fid):
    return rss_service.delete_feed(fid)
