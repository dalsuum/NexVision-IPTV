from flask import Blueprint, request
from ..decorators import admin_required
from ..services import ad_service

ads_bp = Blueprint('ads', __name__, url_prefix='/api/ads')


@ads_bp.route('', methods=['GET'])
def get_ads_public():
    placement = request.args.get('placement', 'both')
    return ad_service.get_active(placement)


@ads_bp.route('/all', methods=['GET'])
@admin_required
def get_ads_all():
    return ad_service.list_all()


@ads_bp.route('', methods=['POST'])
@admin_required
def create_ad():
    return ad_service.create_ad(request.json or {})


@ads_bp.route('/<int:aid>', methods=['PUT'])
@admin_required
def update_ad(aid):
    return ad_service.update_ad(aid, request.json or {})


@ads_bp.route('/<int:aid>', methods=['DELETE'])
@admin_required
def delete_ad(aid):
    return ad_service.delete_ad(aid)


@ads_bp.route('/reorder', methods=['POST'])
@admin_required
def reorder_ads():
    return ad_service.reorder((request.json or {}).get('ids', []))
