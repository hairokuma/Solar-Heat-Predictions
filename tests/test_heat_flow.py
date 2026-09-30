from datetime import timedelta

import pytest

from app.extensions import db
from app.models import Settings, TemperatureReading, utcnow
from app.web import hourly_trend


def _configure(app):
    with app.app_context():
        db.session.add(
            Settings(
                id=Settings.SINGLETON_ID,
                location_name="Home",
                latitude=52.52,
                longitude=13.405,
                weather_api_key="demo",
                setup_complete=True,
            )
        )
        db.session.commit()


def _add_reading(location, value_c, minutes_ago):
    reading = TemperatureReading(
        location=location, value_c=value_c, source="manual", recorded_at=utcnow() - timedelta(minutes=minutes_ago)
    )
    db.session.add(reading)
    db.session.commit()
    return reading


def test_hourly_trend_scales_to_degrees_per_hour(app):
    _add_reading("home", 18.0, minutes_ago=90)
    latest = _add_reading("home", 19.5, minutes_ago=0)
    assert hourly_trend("home", latest) == pytest.approx(1.0)


def test_hourly_trend_uses_newest_reading_at_least_an_hour_old(app):
    _add_reading("conservatory", 30.0, minutes_ago=110)
    _add_reading("conservatory", 28.0, minutes_ago=60)
    _add_reading("conservatory", 27.8, minutes_ago=30)  # too recent to be the baseline
    latest = _add_reading("conservatory", 27.0, minutes_ago=0)
    assert hourly_trend("conservatory", latest) == pytest.approx(-1.0)


def test_hourly_trend_is_none_without_history_or_when_stale(app):
    assert hourly_trend("home", None) is None
    _add_reading("home", 18.0, minutes_ago=30)
    assert hourly_trend("home", _add_reading("home", 18.5, minutes_ago=0)) is None

    _add_reading("conservatory", 20.0, minutes_ago=240)
    assert hourly_trend("conservatory", _add_reading("conservatory", 22.0, minutes_ago=180)) is None


def test_dashboard_heat_flow_idle(client, app):
    _configure(app)
    with app.app_context():
        _add_reading("home", 21.0, minutes_ago=60)
        _add_reading("home", 21.0, minutes_ago=0)
        _add_reading("conservatory", 28.0, minutes_ago=0)

    resp = client.get("/")
    assert resp.status_code == 200
    assert b'class="hf-card"' in resp.data
    assert "28.0°C".encode() in resp.data
    assert "Δ +7.0 °C".encode() in resp.data
    assert b"hf-trend-flat" in resp.data  # home: 21.0 -> 21.0
    assert b"hf-trend-none" in resp.data  # conservatory: no reading an hour back


def test_dashboard_heat_flow_active_with_trends(client, app):
    _configure(app)
    with app.app_context():
        _add_reading("home", 20.0, minutes_ago=60)
        _add_reading("home", 21.5, minutes_ago=0)
        _add_reading("conservatory", 30.0, minutes_ago=60)
        _add_reading("conservatory", 28.0, minutes_ago=0)
    client.post("/transfers/start")

    resp = client.get("/")
    assert b'class="hf-card hf-active"' in resp.data
    assert "▲ +1.5 °C/h".encode() in resp.data
    assert "▼ −2.0 °C/h".encode() in resp.data
    assert b"Running" in resp.data
