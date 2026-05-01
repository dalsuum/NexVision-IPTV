from flask import Blueprint, request
from ..services import weather_service

weather_bp = Blueprint('weather', __name__, url_prefix='/api')


@weather_bp.route('/weather', methods=['GET'])
def get_weather():
    return weather_service.get_weather(
        lat  = request.args.get('lat'),
        lon  = request.args.get('lon'),
        city = request.args.get('city'),
    )
