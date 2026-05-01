"""
blueprints/__init__.py — registers every domain blueprint with the Flask app.
"""


def register_blueprints(app):
    from .auth         import auth_bp
    from .channels     import channels_bp
    from .media_groups import media_groups_bp
    from .vod_api      import vod_api_bp
    from .radio        import radio_bp
    from .content      import content_bp
    from .rooms        import rooms_bp
    from .packages     import packages_bp
    from .skins        import skins_bp
    from .devices      import devices_bp
    from .reports      import reports_bp
    from .stats        import stats_bp
    from .weather      import weather_bp
    from .rss          import rss_bp
    from .messages     import messages_bp
    from .birthdays    import birthdays_bp
    from .prayer       import prayer_bp
    from .uploads      import uploads_bp
    from .slides       import slides_bp
    from .ads          import ads_bp
    from .nav          import nav_bp
    from .settings_bp  import settings_bp
    from .epg          import epg_bp
    from .services_bp  import services_bp
    from .users        import users_bp
    from .cast         import cast_bp
    from .admin_ui     import admin_ui_bp
    from .vod_server   import vod_server_bp
    from .clock_alarm  import clock_alarm_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(channels_bp)
    app.register_blueprint(media_groups_bp)
    app.register_blueprint(vod_api_bp)
    app.register_blueprint(radio_bp)
    app.register_blueprint(content_bp)
    app.register_blueprint(rooms_bp)
    app.register_blueprint(packages_bp)
    app.register_blueprint(skins_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(rss_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(birthdays_bp)
    app.register_blueprint(prayer_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(slides_bp)
    app.register_blueprint(ads_bp)
    app.register_blueprint(nav_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(epg_bp)
    app.register_blueprint(services_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(cast_bp)
    app.register_blueprint(admin_ui_bp)
    app.register_blueprint(vod_server_bp)
    app.register_blueprint(clock_alarm_bp)
