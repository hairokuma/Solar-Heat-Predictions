from datetime import datetime

from app.extensions import db
from app.models import HeatTransferEvent, Settings, TemperatureReading, utcnow


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


def _add_reading(app, location, value_c):
    with app.app_context():
        db.session.add(TemperatureReading(location=location, value_c=value_c, source="manual"))
        db.session.commit()


def test_start_transfer_requires_readings(client, app):
    _configure(app)
    resp = client.post("/transfers/start", follow_redirects=False)
    assert resp.status_code == 302
    with app.app_context():
        assert HeatTransferEvent.query.count() == 0


def test_start_transfer_snapshots_temps(client, app):
    _configure(app)
    _add_reading(app, "home", 18.0)
    _add_reading(app, "conservatory", 23.0)

    resp = client.post("/transfers/start")
    assert resp.status_code == 302

    with app.app_context():
        transfer = HeatTransferEvent.query.one()
        assert transfer.home_temp_start == 18.0
        assert transfer.conservatory_temp_start == 23.0
        assert transfer.ended_at is None


def test_start_transfer_rejects_duplicate_active(client, app):
    _configure(app)
    _add_reading(app, "home", 18.0)
    _add_reading(app, "conservatory", 23.0)

    client.post("/transfers/start")
    client.post("/transfers/start")

    with app.app_context():
        assert HeatTransferEvent.query.count() == 1


def test_stop_transfer_computes_effectiveness(client, app):
    _configure(app)
    _add_reading(app, "home", 18.0)
    _add_reading(app, "conservatory", 23.0)
    client.post("/transfers/start")

    with app.app_context():
        transfer_id = HeatTransferEvent.query.one().id

    _add_reading(app, "home", 20.5)
    _add_reading(app, "conservatory", 22.0)

    resp = client.post(f"/transfers/{transfer_id}/stop")
    assert resp.status_code == 302

    with app.app_context():
        transfer = db.session.get(HeatTransferEvent, transfer_id)
        assert transfer.ended_at is not None
        assert transfer.home_temp_end == 20.5
        assert transfer.conservatory_temp_end == 22.0
        assert round(transfer.effectiveness, 1) == 2.5


def test_stop_transfer_rejects_already_ended(client, app):
    _configure(app)
    with app.app_context():
        transfer = HeatTransferEvent(
            started_at=utcnow(), ended_at=utcnow(), home_temp_start=18.0, conservatory_temp_start=23.0
        )
        db.session.add(transfer)
        db.session.commit()
        transfer_id = transfer.id

    resp = client.post(f"/transfers/{transfer_id}/stop")
    assert resp.status_code == 302
    with app.app_context():
        assert db.session.get(HeatTransferEvent, transfer_id).home_temp_end is None


def test_edit_transfer_updates_fields_and_effectiveness(client, app):
    _configure(app)
    with app.app_context():
        transfer = HeatTransferEvent(started_at=utcnow(), home_temp_start=18.0, conservatory_temp_start=23.0)
        db.session.add(transfer)
        db.session.commit()
        transfer_id = transfer.id

    resp = client.post(
        f"/transfers/{transfer_id}/edit",
        data={
            "started_at": "2026-01-01T10:00",
            "ended_at": "2026-01-01T11:30",
            "home_temp_start": "17.5",
            "home_temp_end": "20.0",
            "conservatory_temp_start": "24.0",
            "conservatory_temp_end": "21.0",
            "notes": "Cloudy afterwards",
        },
    )
    assert resp.status_code == 302

    with app.app_context():
        transfer = db.session.get(HeatTransferEvent, transfer_id)
        assert transfer.home_temp_start == 17.5
        assert transfer.home_temp_end == 20.0
        assert transfer.notes == "Cloudy afterwards"
        assert round(transfer.effectiveness, 1) == 2.5


def test_edit_transfer_rejects_missing_start_time(client, app):
    _configure(app)
    with app.app_context():
        transfer = HeatTransferEvent(started_at=utcnow(), home_temp_start=18.0, conservatory_temp_start=23.0)
        db.session.add(transfer)
        db.session.commit()
        transfer_id = transfer.id

    resp = client.post(f"/transfers/{transfer_id}/edit", data={"started_at": ""})
    assert resp.status_code == 400


def test_delete_transfer_removes_row(client, app):
    _configure(app)
    with app.app_context():
        transfer = HeatTransferEvent(started_at=utcnow(), home_temp_start=18.0, conservatory_temp_start=23.0)
        db.session.add(transfer)
        db.session.commit()
        transfer_id = transfer.id

    resp = client.post(f"/transfers/{transfer_id}/delete")
    assert resp.status_code == 302
    with app.app_context():
        assert db.session.get(HeatTransferEvent, transfer_id) is None


def test_dashboard_shows_active_transfer_and_stop_button(client, app):
    _configure(app)
    _add_reading(app, "home", 18.0)
    _add_reading(app, "conservatory", 23.0)
    client.post("/transfers/start")

    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Stop Transfer" in resp.data
    assert b"Active" in resp.data


def test_dashboard_highlights_start_when_condition_met(client, app):
    _configure(app)
    _add_reading(app, "home", 15.0)
    _add_reading(app, "conservatory", 20.0)  # delta 5 >= 3 threshold, home < 21 desired

    resp = client.get("/")
    assert resp.status_code == 200
    assert b'class="cta"' in resp.data


def test_transfer_list_and_detail_pages_render(client, app):
    _configure(app)
    with app.app_context():
        transfer = HeatTransferEvent(started_at=utcnow(), home_temp_start=18.0, conservatory_temp_start=23.0)
        db.session.add(transfer)
        db.session.commit()
        transfer_id = transfer.id

    resp = client.get("/transfers")
    assert resp.status_code == 200

    resp = client.get(f"/transfers/{transfer_id}")
    assert resp.status_code == 200


def test_edit_transfer_round_trips_browser_local_times(client, app):
    _configure(app)
    with app.app_context():
        transfer = HeatTransferEvent(started_at=utcnow(), home_temp_start=18.0, conservatory_temp_start=23.0)
        db.session.add(transfer)
        db.session.commit()
        transfer_id = transfer.id

    client.set_cookie("tz", "Europe/Berlin")
    resp = client.post(
        f"/transfers/{transfer_id}/edit",
        data={"started_at": "2026-01-01T10:00", "ended_at": "2026-01-01T11:30"},
    )
    assert resp.status_code == 302

    with app.app_context():
        transfer = db.session.get(HeatTransferEvent, transfer_id)
        assert transfer.started_at == datetime(2026, 1, 1, 9, 0)  # CET is UTC+1 in winter
        assert transfer.ended_at == datetime(2026, 1, 1, 10, 30)

    # The edit form shows the same local times back.
    resp = client.get(f"/transfers/{transfer_id}")
    assert b'value="2026-01-01T10:00"' in resp.data
    assert b'value="2026-01-01T11:30"' in resp.data
