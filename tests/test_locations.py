from app.extensions import db
from app.models import CustomLocation, Sensor, Settings, TemperatureReading


def _configure(app):
    with app.app_context():
        db.session.add(
            Settings(
                id=Settings.SINGLETON_ID,
                location_name="Home",
                latitude=52.52,
                longitude=13.405,
                weather_api_key="demo",
                notify_email="me@example.com",
                smtp_host="smtp.example.com",
                smtp_username="me@example.com",
                setup_complete=True,
            )
        )
        db.session.commit()


def test_only_home_and_conservatory_by_default(client, app):
    _configure(app)
    assert TemperatureReading.locations() == ["home", "conservatory"]
    resp = client.get("/")
    assert b'data-location="home"' in resp.data
    assert b'data-location="conservatory"' in resp.data
    assert b'data-location="garden"' not in resp.data


def test_garden_is_rejected_until_added(client, app):
    _configure(app)
    assert client.post("/readings", data={"location": "garden", "value_c": "15"}).status_code == 400


def test_add_custom_location_enables_readings_and_sensors(client, app):
    _configure(app)
    resp = client.post("/settings/locations", data={"name": "  Attic  "})
    assert resp.status_code == 302
    with app.app_context():
        assert TemperatureReading.locations() == ["home", "conservatory", "attic"]

    assert b'data-location="attic"' in client.get("/").data
    assert client.post("/readings", data={"location": "attic", "value_c": "30"}).status_code == 302
    client.post("/settings/sensors", data={"name": "Attic ESP", "location": "attic"})
    with app.app_context():
        assert Sensor.query.one().location == "attic"


def test_rejects_duplicate_reserved_and_invalid_names(client, app):
    _configure(app)
    for name in ("Home", "outdoor", "", "x" * 21, "<script>"):
        client.post("/settings/locations", data={"name": name})
    with app.app_context():
        assert CustomLocation.query.count() == 0


def test_delete_location_keeps_readings(client, app):
    _configure(app)
    with app.app_context():
        location = CustomLocation(name="garden")
        db.session.add(location)
        db.session.add(TemperatureReading(location="garden", value_c=12.0))
        db.session.commit()
        location_id = location.id

    assert client.post(f"/settings/locations/{location_id}/delete").status_code == 302
    with app.app_context():
        assert CustomLocation.query.count() == 0
        assert TemperatureReading.query.filter_by(location="garden").count() == 1


def test_delete_location_refused_while_sensor_bound(client, app):
    _configure(app)
    with app.app_context():
        location = CustomLocation(name="garden")
        db.session.add(location)
        db.session.add(Sensor(name="esp", location="garden", api_key="k"))
        db.session.commit()
        location_id = location.id

    client.post(f"/settings/locations/{location_id}/delete")
    with app.app_context():
        assert db.session.get(CustomLocation, location_id) is not None
