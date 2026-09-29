from app import scheduler as scheduler_module
from app.extensions import db
from app.models import Settings, WeatherForecast, WeatherObservation
from app.services.weather import WeatherProviderError

FAKE_CURRENT = {
    "main": {"temp": 12.3, "humidity": 80},
    "clouds": {"all": 40},
    "wind": {"speed": 3.2},
    "weather": [{"description": "scattered clouds"}],
}

FAKE_FORECAST = {
    "list": [
        {
            "dt": 1700000000,
            "main": {"temp": 5.0},
            "clouds": {"all": 10},
            "weather": [{"description": "clear sky"}],
        },
        {
            "dt": 1700010800,
            "main": {"temp": 6.5},
            "clouds": {"all": 20},
            "weather": [{"description": "few clouds"}],
        },
    ]
}


def _configure(app):
    with app.app_context():
        settings = Settings(
            id=Settings.SINGLETON_ID,
            location_name="Home",
            latitude=52.52,
            longitude=13.405,
            weather_api_key="demo",
            delta_threshold_c=3.0,
            desired_home_temp_c=21.0,
            renotify_cooldown_min=60,
            notify_email="me@example.com",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="me@example.com",
            smtp_password="hunter2",
            smtp_use_tls=True,
            setup_complete=True,
        )
        db.session.add(settings)
        db.session.commit()


def test_current_weather_job_skips_when_not_configured(app):
    scheduler_module.fetch_and_store_current_weather(app)
    with app.app_context():
        assert WeatherObservation.query.count() == 0


def test_current_weather_job_stores_observation(app, monkeypatch):
    _configure(app)
    monkeypatch.setattr(scheduler_module, "fetch_current_weather", lambda *a, **k: FAKE_CURRENT)

    scheduler_module.fetch_and_store_current_weather(app)

    with app.app_context():
        obs = WeatherObservation.query.one()
        assert obs.temp_c == 12.3
        assert obs.cloud_pct == 40
        assert obs.humidity == 80
        assert obs.wind_speed == 3.2
        assert obs.condition == "scattered clouds"


def test_current_weather_job_handles_provider_error(app, monkeypatch):
    _configure(app)

    def raise_error(*args, **kwargs):
        raise WeatherProviderError("boom")

    monkeypatch.setattr(scheduler_module, "fetch_current_weather", raise_error)

    scheduler_module.fetch_and_store_current_weather(app)

    with app.app_context():
        assert WeatherObservation.query.count() == 0


def test_forecast_job_stores_multiple_rows(app, monkeypatch):
    _configure(app)
    monkeypatch.setattr(scheduler_module, "fetch_forecast", lambda *a, **k: FAKE_FORECAST)

    scheduler_module.fetch_and_store_forecast(app)

    with app.app_context():
        rows = WeatherForecast.query.order_by(WeatherForecast.forecast_for.asc()).all()
        assert len(rows) == 2
        assert rows[0].temp_c == 5.0
        assert rows[1].temp_c == 6.5


def test_dashboard_shows_weather_tile(client, app):
    _configure(app)
    with app.app_context():
        db.session.add(
            WeatherObservation(temp_c=9.5, cloud_pct=15, humidity=70, wind_speed=2.1, condition="clear sky")
        )
        db.session.commit()

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"9.5" in resp.data
