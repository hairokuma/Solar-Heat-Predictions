from app.extensions import db
from app.models import Sensor, Settings, TemperatureReading, WeatherObservation, utcnow
from app.web import setup as setup_views


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


def _register_sensor(app, name="esp-01", location="garden", api_key="test-sensor-key"):
    with app.app_context():
        db.session.add(Sensor(name=name, location=location, api_key=api_key))
        db.session.commit()


def test_dashboard_requires_setup(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302


def test_dashboard_has_log_reading_button_per_location(client, app):
    _configure(app)
    resp = client.get("/")
    assert resp.status_code == 200
    for location in TemperatureReading.LOCATIONS:
        assert f'data-location="{location}"'.encode() in resp.data
    assert b'id="reading-dialog"' in resp.data


def test_dashboard_chart_includes_outdoor_observations(client, app):
    _configure(app)
    with app.app_context():
        db.session.add(WeatherObservation(fetched_at=utcnow(), temp_c=7.25))
        db.session.commit()
    resp = client.get("/")
    assert b'"outdoor": [{"t":' in resp.data
    assert b"7.25" in resp.data


def test_rejected_reading_reopens_dialog_with_errors(client, app):
    _configure(app)
    resp = client.post("/readings", data={"location": "garden", "value_c": "999"})
    assert resp.status_code == 400
    assert b"Temperature must be between" in resp.data
    assert b'openReadingDialog("garden", true)' in resp.data


def test_manual_reading_creates_row_and_shows_on_dashboard(client, app):
    _configure(app)

    resp = client.post(
        "/readings", data={"location": "conservatory", "value_c": "25.5", "recorded_at": ""}
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"

    with app.app_context():
        rows = TemperatureReading.query.all()
        assert len(rows) == 1
        assert rows[0].location == "conservatory"
        assert rows[0].value_c == 25.5
        assert rows[0].source == "manual"

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"25.5" in resp.data


def test_manual_reading_rejects_invalid_location(client, app):
    _configure(app)
    resp = client.post("/readings", data={"location": "attic", "value_c": "20"})
    assert resp.status_code == 400


def test_manual_reading_rejects_out_of_range_temperature(client, app):
    _configure(app)
    resp = client.post("/readings", data={"location": "home", "value_c": "999"})
    assert resp.status_code == 400
    with app.app_context():
        assert TemperatureReading.query.count() == 0


def test_sensor_api_rejects_missing_key(client, app):
    _configure(app)
    _register_sensor(app)
    resp = client.post("/api/v1/readings", json={"value_c": "20"})
    assert resp.status_code == 401


def test_sensor_api_rejects_wrong_key(client, app):
    _configure(app)
    _register_sensor(app)
    resp = client.post(
        "/api/v1/readings",
        json={"value_c": 20},
        headers={"X-API-Key": "wrong"},
    )
    assert resp.status_code == 401


def test_sensor_api_rejects_unregistered_key_before_setup(client):
    resp = client.post(
        "/api/v1/readings",
        json={"value_c": 20},
        headers={"X-API-Key": "anything"},
    )
    assert resp.status_code == 401


def test_sensor_api_creates_reading_at_sensors_own_location(client, app):
    _configure(app)
    _register_sensor(app, name="esp-01", location="garden", api_key="test-sensor-key")
    resp = client.post(
        "/api/v1/readings",
        json={"value_c": 12.3},
        headers={"X-API-Key": "test-sensor-key"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["location"] == "garden"
    assert body["value_c"] == 12.3

    with app.app_context():
        row = TemperatureReading.query.filter_by(location="garden").first()
        assert row is not None
        assert row.source == "sensor"
        assert row.sensor_id == "esp-01"


def test_sensor_api_rejects_location_mismatch(client, app):
    _configure(app)
    _register_sensor(app, location="garden", api_key="test-sensor-key")
    resp = client.post(
        "/api/v1/readings",
        json={"location": "home", "value_c": 12.3},
        headers={"X-API-Key": "test-sensor-key"},
    )
    assert resp.status_code == 400


def test_sensor_api_rejects_out_of_range_temperature(client, app):
    _configure(app)
    _register_sensor(app, api_key="test-sensor-key")
    resp = client.post(
        "/api/v1/readings",
        json={"value_c": 999},
        headers={"X-API-Key": "test-sensor-key"},
    )
    assert resp.status_code == 400


def test_settings_test_email_falls_back_to_stored_password(client, app, monkeypatch):
    _configure(app)
    sent = []
    monkeypatch.setattr(setup_views, "send_email", lambda **kwargs: sent.append(kwargs))
    resp = client.post(
        "/settings/email/test",
        json={
            "notify_email": "me@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "me@example.com",
            "smtp_password": "",
            "smtp_use_tls": True,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert sent[0]["password"] == "hunter2"
