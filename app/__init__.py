import os

from flask import Flask, jsonify, redirect, request, url_for

from .extensions import db, limiter, migrate
from .models import Settings


def create_app(config_object="config.Config"):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    from .services.timezones import localtime_filter

    app.add_template_filter(localtime_filter, "localtime")

    from .api import api_bp
    from .web import web_bp
    from .web.setup import setup_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(setup_bp)
    app.register_blueprint(api_bp)

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    @app.before_request
    def enforce_setup_wizard():
        endpoint = request.endpoint
        if endpoint is None:
            return None
        if endpoint == "health" or endpoint == "static":
            return None
        if endpoint.startswith("setup.") or endpoint.startswith("api."):
            return None
        if not Settings.is_configured():
            return redirect(url_for("setup.step", step="location"))
        return None

    from .scheduler import init_scheduler

    app.extensions["weather_scheduler"] = init_scheduler(app)

    return app
