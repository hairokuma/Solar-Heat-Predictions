from app.extensions import db
from app.models import Sensor, Settings


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


def test_sensors_page_requires_setup(client):
    resp = client.get("/settings/sensors", follow_redirects=False)
    assert resp.status_code == 302


def test_create_sensor_generates_unique_key(client, app):
    _configure(app)
    resp = client.post("/settings/sensors", data={"name": "Conservatory ESP", "location": "conservatory"})
    assert resp.status_code == 302

    with app.app_context():
        sensor = Sensor.query.one()
        assert sensor.name == "Conservatory ESP"
        assert sensor.location == "conservatory"
        assert len(sensor.api_key) >= 32


def test_create_sensor_rejects_invalid_location(client, app):
    _configure(app)
    resp = client.post("/settings/sensors", data={"name": "Bad sensor", "location": "attic"})
    assert resp.status_code == 302
    with app.app_context():
        assert Sensor.query.count() == 0


def test_create_sensor_requires_name(client, app):
    _configure(app)
    resp = client.post("/settings/sensors", data={"name": "", "location": "home"})
    assert resp.status_code == 302
    with app.app_context():
        assert Sensor.query.count() == 0


def test_delete_sensor_revokes_key(client, app):
    _configure(app)
    with app.app_context():
        sensor = Sensor(name="Old sensor", location="home", api_key="revoke-me")
        db.session.add(sensor)
        db.session.commit()
        sensor_id = sensor.id

    resp = client.post(f"/settings/sensors/{sensor_id}/delete")
    assert resp.status_code == 302

    with app.app_context():
        assert db.session.get(Sensor, sensor_id) is None

    resp = client.post(
        "/api/v1/readings", json={"value_c": 20}, headers={"X-API-Key": "revoke-me"}
    )
    assert resp.status_code == 401


def test_sensor_last_seen_updates_on_reading(client, app):
    _configure(app)
    with app.app_context():
        sensor = Sensor(name="s1", location="home", api_key="key1")
        db.session.add(sensor)
        db.session.commit()
        sensor_id = sensor.id
        assert sensor.last_seen_at is None

    client.post("/api/v1/readings", json={"value_c": 18.0}, headers={"X-API-Key": "key1"})

    with app.app_context():
        assert db.session.get(Sensor, sensor_id).last_seen_at is not None


def test_sensor_readings_rate_limited(client, app):
    _configure(app)
    with app.app_context():
        db.session.add(Sensor(name="s1", location="home", api_key="key1"))
        db.session.commit()

    statuses = [
        client.post("/api/v1/readings", json={"value_c": 18.0}, headers={"X-API-Key": "key1"}).status_code
        for _ in range(65)
    ]
    assert 429 in statuses
