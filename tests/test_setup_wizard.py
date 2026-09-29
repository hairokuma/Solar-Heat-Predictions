from app.models import Settings
from app.web import setup as setup_routes


def test_geocode_requires_address(client):
    resp = client.post("/setup/location/geocode", json={"address": ""})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_geocode_returns_matches(client, monkeypatch):
    fake_results = [
        {"name": "Berlin", "admin1": "Berlin", "country": "Germany", "latitude": 52.52, "longitude": 13.405}
    ]
    monkeypatch.setattr(setup_routes, "geocode_address", lambda query, **kwargs: fake_results)

    resp = client.post("/setup/location/geocode", json={"address": "Berlin"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["results"] == fake_results


def test_geocode_handles_no_matches(client, monkeypatch):
    monkeypatch.setattr(setup_routes, "geocode_address", lambda query, **kwargs: [])

    resp = client.post("/setup/location/geocode", json={"address": "Nowhereville"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is False


def test_root_redirects_to_setup_when_unconfigured(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/setup/location"


def test_healthz_bypasses_setup_gate(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_location_step_rejects_invalid_numbers(client):
    resp = client.post(
        "/setup/location",
        data={"location_name": "Home", "latitude": "not-a-number", "longitude": "13.405"},
    )
    assert resp.status_code == 400


def test_location_step_rejects_out_of_range_coordinates(client):
    resp = client.post(
        "/setup/location",
        data={"location_name": "Home", "latitude": "200", "longitude": "13.405"},
    )
    assert resp.status_code == 400


def test_notifications_step_rejects_out_of_range_threshold(client):
    resp = client.post(
        "/setup/notifications",
        data={"delta_threshold_c": "100", "desired_home_temp_c": "21.0", "renotify_cooldown_min": "60"},
    )
    assert resp.status_code == 400


def test_email_step_rejects_invalid_email_format(client):
    resp = client.post(
        "/setup/email",
        data={
            "notify_email": "not-an-email",
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "me@example.com",
            "smtp_password": "hunter2",
        },
    )
    assert resp.status_code == 400


def test_email_step_rejects_out_of_range_port(client):
    resp = client.post(
        "/setup/email",
        data={
            "notify_email": "me@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_port": "99999",
            "smtp_username": "me@example.com",
            "smtp_password": "hunter2",
        },
    )
    assert resp.status_code == 400


def test_wizard_finish_fails_without_all_steps(client):
    resp = client.post("/setup/review", data={"action": "finish"}, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/setup/location"


def test_full_wizard_flow_creates_settings(client, app):
    resp = client.post(
        "/setup/location",
        data={"location_name": "Home", "latitude": "52.52", "longitude": "13.405"},
    )
    assert resp.headers["Location"] == "/setup/weather"

    resp = client.post("/setup/weather", data={"weather_api_key": "test-key"})
    assert resp.headers["Location"] == "/setup/notifications"

    resp = client.post(
        "/setup/notifications",
        data={
            "delta_threshold_c": "3.0",
            "desired_home_temp_c": "21.0",
            "renotify_cooldown_min": "60",
        },
    )
    assert resp.headers["Location"] == "/setup/email"

    resp = client.post(
        "/setup/email",
        data={
            "notify_email": "me@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "me@example.com",
            "smtp_password": "hunter2",
            "smtp_use_tls": "on",
        },
    )
    assert resp.headers["Location"] == "/setup/review"

    resp = client.post("/setup/review", data={"action": "finish"})
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"

    with app.app_context():
        settings = Settings.get()
        assert settings is not None
        assert settings.setup_complete is True
        assert settings.location_name == "Home"
        assert settings.desired_home_temp_c == 21.0
        assert settings.smtp_username == "me@example.com"

    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 200
