import jwt
from flask import Blueprint, request, current_app
from ..services import weather_service, user_service

weather_bp = Blueprint('weather', __name__, url_prefix='/api')


@weather_bp.route('/weather', methods=['GET'])
def get_weather():
    lat  = request.args.get('lat')
    lon  = request.args.get('lon')
    city = request.args.get('city')

    # If no explicit location provided, try the requesting user's saved city
    if not lat and not city:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if token:
            try:
                data = jwt.decode(
                    token, current_app.config['SECRET_KEY'], algorithms=['HS256']
                )
                user_city = user_service.get_user_city(data.get('id'))
                if user_city:
                    city = user_city
            except Exception:
                pass

    return weather_service.get_weather(lat=lat, lon=lon, city=city)
