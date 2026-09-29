from datetime import timedelta

from app.extensions import db
from app.models import HeatTransferEvent, Settings, TemperatureReading, WeatherForecast, WeatherObservation, utcnow
from app.services.predictions import MIN_TRAINING_SAMPLES, average_effectiveness, build_roadmap


def _configure(app, delta_threshold_c=3.0):
    with app.app_context():
        settings = Settings(
            id=Settings.SINGLETON_ID,
            location_name="Home",
            latitude=52.52,
            longitude=13.405,
            weather_api_key="demo",
            delta_threshold_c=delta_threshold_c,
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


def _add_forecast(app, forecast_for, temp_c, cloud_pct=20.0, fetched_at=None):
    with app.app_context():
        db.session.add(
            WeatherForecast(
                fetched_at=fetched_at or utcnow(),
                forecast_for=forecast_for,
                temp_c=temp_c,
                cloud_pct=cloud_pct,
                condition="clear sky",
            )
        )
        db.session.commit()


def test_no_forecasts_returns_empty_roadmap(app):
    _configure(app)
    with app.app_context():
        assert build_roadmap() == []


def test_roadmap_uses_heuristic_without_history(app):
    _configure(app)
    forecast_time = (utcnow() + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    _add_forecast(app, forecast_time, temp_c=10.0, cloud_pct=10.0)

    with app.app_context():
        slots = build_roadmap()

    assert len(slots) == 1
    slot = slots[0]
    assert slot["using_model"] is False
    # Sunny midday heuristic: outdoor + 8
    assert slot["predicted_conservatory"] == 18.0


def test_roadmap_dedupes_forecast_by_latest_fetch(app):
    _configure(app)
    forecast_time = (utcnow() + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    _add_forecast(app, forecast_time, temp_c=5.0, fetched_at=utcnow() - timedelta(hours=6))
    _add_forecast(app, forecast_time, temp_c=9.0, fetched_at=utcnow() - timedelta(hours=1))

    with app.app_context():
        slots = build_roadmap()

    assert len(slots) == 1
    assert slots[0]["outdoor_temp"] == 9.0


def test_roadmap_excludes_past_and_far_future_forecasts(app):
    _configure(app)
    _add_forecast(app, utcnow() - timedelta(hours=1), temp_c=10.0)  # past
    _add_forecast(app, utcnow() + timedelta(days=10), temp_c=10.0)  # beyond ROADMAP_DAYS
    _add_forecast(app, utcnow() + timedelta(days=1), temp_c=10.0)  # in range

    with app.app_context():
        slots = build_roadmap()

    assert len(slots) == 1


def test_roadmap_uses_trained_model_with_enough_history(app):
    _configure(app)
    base = utcnow() - timedelta(days=30)

    with app.app_context():
        for i in range(MIN_TRAINING_SAMPLES + 5):
            ts = (base + timedelta(days=i)).replace(hour=12, minute=0, second=0, microsecond=0)
            outdoor_temp = 5.0 + i
            db.session.add(WeatherObservation(fetched_at=ts, temp_c=outdoor_temp, cloud_pct=10.0))
            db.session.add(
                TemperatureReading(location="conservatory", value_c=outdoor_temp + 8.0, source="manual", recorded_at=ts)
            )
            db.session.add(TemperatureReading(location="home", value_c=20.0, source="manual", recorded_at=ts))
        db.session.commit()

    forecast_time = (utcnow() + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    _add_forecast(app, forecast_time, temp_c=15.0, cloud_pct=10.0)

    with app.app_context():
        slots = build_roadmap()

    assert len(slots) == 1
    slot = slots[0]
    assert slot["using_model"] is True
    # conservatory ~= outdoor + 8, home ~= 20, learned from noise-free synthetic data
    assert abs(slot["predicted_conservatory"] - 23.0) < 1.0
    assert abs(slot["predicted_home"] - 20.0) < 1.0
    assert slot["opportunity"] is True


def test_average_effectiveness_ignores_null_and_averages(app):
    with app.app_context():
        db.session.add(HeatTransferEvent(started_at=utcnow(), effectiveness=2.0))
        db.session.add(HeatTransferEvent(started_at=utcnow(), effectiveness=4.0))
        db.session.add(HeatTransferEvent(started_at=utcnow(), effectiveness=None))
        db.session.commit()

        avg, count = average_effectiveness()
        assert count == 2
        assert avg == 3.0


def test_average_effectiveness_with_no_events(app):
    with app.app_context():
        avg, count = average_effectiveness()
        assert avg is None
        assert count == 0


def test_roadmap_page_renders_without_setup_redirect_after_configure(client, app):
    _configure(app)
    resp = client.get("/roadmap")
    assert resp.status_code == 200
    assert b"No weather forecast data yet" in resp.data


def test_roadmap_page_shows_opportunity_badge(client, app):
    _configure(app)
    forecast_time = (utcnow() + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    _add_forecast(app, forecast_time, temp_c=10.0, cloud_pct=10.0)

    resp = client.get("/roadmap")
    assert resp.status_code == 200
    assert b"Opportunity" in resp.data
