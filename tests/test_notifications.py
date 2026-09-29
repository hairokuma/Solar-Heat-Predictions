from datetime import timedelta

from app import scheduler as scheduler_module
from app.extensions import db
from app.models import HeatTransferEvent, NotificationLog, Settings, TemperatureReading, utcnow


def _configure(app, delta_threshold_c=3.0, desired_home_temp_c=21.0, renotify_cooldown_min=60):
    with app.app_context():
        settings = Settings(
            id=Settings.SINGLETON_ID,
            location_name="Home",
            latitude=52.52,
            longitude=13.405,
            weather_api_key="demo",
            delta_threshold_c=delta_threshold_c,
            desired_home_temp_c=desired_home_temp_c,
            renotify_cooldown_min=renotify_cooldown_min,
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


def _sent_emails(monkeypatch):
    sent = []
    monkeypatch.setattr(scheduler_module, "send_email", lambda **kwargs: sent.append(kwargs))
    return sent


def _reset_warm_window(monkeypatch):
    monkeypatch.setattr(scheduler_module, "_warm_window_notified", False)


def test_no_notification_without_readings(app, monkeypatch):
    _configure(app)
    _reset_warm_window(monkeypatch)
    sent = _sent_emails(monkeypatch)

    scheduler_module.evaluate_notifications(app)

    assert sent == []
    with app.app_context():
        assert NotificationLog.query.count() == 0


def test_no_notification_below_threshold(app, monkeypatch):
    _configure(app)
    _add_reading(app, "home", 18.0)
    _add_reading(app, "conservatory", 19.5)  # delta 1.5 < 3.0
    _reset_warm_window(monkeypatch)
    sent = _sent_emails(monkeypatch)

    scheduler_module.evaluate_notifications(app)

    assert sent == []
    with app.app_context():
        assert NotificationLog.query.count() == 0


def test_start_notification_sent_once_for_sustained_delta(app, monkeypatch):
    _configure(app)
    _add_reading(app, "home", 15.0)
    _add_reading(app, "conservatory", 20.0)  # delta 5.0 >= 3.0
    _reset_warm_window(monkeypatch)
    sent = _sent_emails(monkeypatch)

    scheduler_module.evaluate_notifications(app)
    assert len(sent) == 1

    with app.app_context():
        logs = NotificationLog.query.all()
        assert len(logs) == 1
        assert logs[0].kind == "start"

    # Same warm window, well within the cooldown window: no new email.
    scheduler_module.evaluate_notifications(app)
    assert len(sent) == 1
    with app.app_context():
        assert NotificationLog.query.count() == 1


def test_start_notification_resends_after_cooldown(app, monkeypatch):
    _configure(app, renotify_cooldown_min=30)
    _add_reading(app, "home", 15.0)
    _add_reading(app, "conservatory", 20.0)
    _reset_warm_window(monkeypatch)
    sent = _sent_emails(monkeypatch)

    scheduler_module.evaluate_notifications(app)
    assert len(sent) == 1

    with app.app_context():
        log = NotificationLog.query.one()
        log.sent_at = utcnow() - timedelta(minutes=31)
        db.session.commit()

    scheduler_module.evaluate_notifications(app)
    assert len(sent) == 2


def test_start_notification_suppressed_at_desired_home_temp(app, monkeypatch):
    _configure(app, desired_home_temp_c=21.0)
    _add_reading(app, "home", 21.5)  # already at/above desired
    _add_reading(app, "conservatory", 26.0)  # delta well above threshold
    _reset_warm_window(monkeypatch)
    sent = _sent_emails(monkeypatch)

    scheduler_module.evaluate_notifications(app)

    assert sent == []
    with app.app_context():
        assert NotificationLog.query.count() == 0


def test_new_warm_window_after_drop_notifies_immediately(app, monkeypatch):
    _configure(app, renotify_cooldown_min=60)
    _add_reading(app, "home", 15.0)
    _add_reading(app, "conservatory", 20.0)
    _reset_warm_window(monkeypatch)
    sent = _sent_emails(monkeypatch)

    scheduler_module.evaluate_notifications(app)
    assert len(sent) == 1

    # Delta drops below threshold: resets the warm-window flag.
    _add_reading(app, "conservatory", 16.0)  # delta now 1.0 < 3.0
    scheduler_module.evaluate_notifications(app)
    assert len(sent) == 1

    # Crosses back above threshold moments later: should notify again
    # immediately, not wait out the 60 min cooldown from the earlier spell.
    _add_reading(app, "conservatory", 20.0)
    scheduler_module.evaluate_notifications(app)
    assert len(sent) == 2


def test_no_start_notification_while_transfer_active(app, monkeypatch):
    _configure(app)
    _add_reading(app, "home", 15.0)
    _add_reading(app, "conservatory", 20.0)
    with app.app_context():
        db.session.add(HeatTransferEvent(home_temp_start=15.0, conservatory_temp_start=20.0))
        db.session.commit()
    _reset_warm_window(monkeypatch)
    sent = _sent_emails(monkeypatch)

    scheduler_module.evaluate_notifications(app)

    assert sent == []
    with app.app_context():
        assert NotificationLog.query.count() == 0


def test_stop_notification_sent_once_when_transfer_active_and_desired_reached(app, monkeypatch):
    _configure(app, desired_home_temp_c=21.0)
    _add_reading(app, "home", 21.2)
    _add_reading(app, "conservatory", 23.0)
    with app.app_context():
        db.session.add(HeatTransferEvent(home_temp_start=18.0, conservatory_temp_start=23.0))
        db.session.commit()
    _reset_warm_window(monkeypatch)
    sent = _sent_emails(monkeypatch)

    scheduler_module.evaluate_notifications(app)
    assert len(sent) == 1
    with app.app_context():
        logs = NotificationLog.query.all()
        assert len(logs) == 1
        assert logs[0].kind == "stop"

    # Still active and still at/above desired temp: don't resend.
    scheduler_module.evaluate_notifications(app)
    assert len(sent) == 1
    with app.app_context():
        assert NotificationLog.query.count() == 1


def test_notification_log_records_failure_without_crashing(app, monkeypatch):
    from app.services.notifications import EmailSendError

    _configure(app)
    _add_reading(app, "home", 15.0)
    _add_reading(app, "conservatory", 20.0)
    _reset_warm_window(monkeypatch)

    def raise_error(**kwargs):
        raise EmailSendError("smtp down")

    monkeypatch.setattr(scheduler_module, "send_email", raise_error)

    scheduler_module.evaluate_notifications(app)

    with app.app_context():
        log = NotificationLog.query.one()
        assert log.kind == "start"
        assert log.success is False
