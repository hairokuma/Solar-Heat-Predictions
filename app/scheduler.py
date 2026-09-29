import atexit
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from .extensions import db
from .models import (
    HeatTransferEvent,
    NotificationLog,
    Settings,
    TemperatureReading,
    WeatherForecast,
    WeatherObservation,
    utcnow,
)
from .services.notifications import EmailSendError, send_email
from .services.weather import WeatherProviderError, fetch_current_weather, fetch_forecast

logger = logging.getLogger(__name__)

CURRENT_WEATHER_INTERVAL_MINUTES = 30
FORECAST_INTERVAL_HOURS = 3
NOTIFICATION_CHECK_INTERVAL_MINUTES = 5

# In-process only: tracks whether we've already sent a start notification for
# the *current* uninterrupted warm spell, so a sustained delta only produces
# one email (then periodic re-notifies) instead of one per poll. Resets to
# False whenever the delta drops back below threshold or a transfer becomes
# active, so the next crossing notifies immediately rather than waiting out
# the re-notify cooldown from an unrelated earlier spell. Lost on restart -
# worst case is one extra notification if the app restarts mid-window, which
# is harmless for a single-user home app.
_warm_window_notified = False


def fetch_and_store_current_weather(app):
    with app.app_context():
        settings = Settings.get()
        if not settings or not settings.setup_complete:
            return

        try:
            data = fetch_current_weather(settings.latitude, settings.longitude, settings.weather_api_key)
        except WeatherProviderError as exc:
            logger.warning("Failed to fetch current weather: %s", exc)
            return

        main = data.get("main") or {}
        weather_list = data.get("weather") or [{}]
        observation = WeatherObservation(
            fetched_at=utcnow(),
            temp_c=main.get("temp"),
            cloud_pct=(data.get("clouds") or {}).get("all"),
            humidity=main.get("humidity"),
            wind_speed=(data.get("wind") or {}).get("speed"),
            condition=weather_list[0].get("description"),
            raw_json=json.dumps(data),
        )
        db.session.add(observation)
        db.session.commit()


def fetch_and_store_forecast(app):
    with app.app_context():
        settings = Settings.get()
        if not settings or not settings.setup_complete:
            return

        try:
            data = fetch_forecast(settings.latitude, settings.longitude, settings.weather_api_key)
        except WeatherProviderError as exc:
            logger.warning("Failed to fetch forecast: %s", exc)
            return

        fetched_at = utcnow()
        for entry in data.get("list") or []:
            main = entry.get("main") or {}
            weather_list = entry.get("weather") or [{}]
            forecast = WeatherForecast(
                fetched_at=fetched_at,
                # Naive UTC, to match utcnow() and every other stored timestamp.
                forecast_for=datetime.fromtimestamp(entry["dt"], tz=timezone.utc).replace(tzinfo=None),
                temp_c=main.get("temp"),
                cloud_pct=(entry.get("clouds") or {}).get("all"),
                condition=weather_list[0].get("description"),
                raw_json=json.dumps(entry),
            )
            db.session.add(forecast)
        db.session.commit()


def _latest_reading(location):
    return (
        TemperatureReading.query.filter_by(location=location)
        .order_by(TemperatureReading.recorded_at.desc())
        .first()
    )


def _send_notification(settings, kind, subject, body, delta_c, home_temp):
    success = True
    try:
        send_email(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            from_addr=settings.smtp_username,
            to_addr=settings.notify_email,
            subject=subject,
            body=body,
        )
    except EmailSendError as exc:
        logger.warning("Failed to send %s notification: %s", kind, exc)
        success = False

    db.session.add(NotificationLog(kind=kind, delta_c=delta_c, home_temp=home_temp, success=success))
    db.session.commit()


def _send_start_notification(settings, home, conservatory, delta):
    subject = f"Solar Heat: Conservatory is {delta:.1f}°C warmer than Home"
    body = (
        f"Conservatory: {conservatory.value_c:.1f}°C\n"
        f"Home: {home.value_c:.1f}°C\n"
        f"Delta: {delta:.1f}°C (threshold: {settings.delta_threshold_c:.1f}°C)\n"
        f"As of {home.recorded_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        "Consider starting the heat transfer from the Conservatory to the Home."
    )
    _send_notification(settings, "start", subject, body, delta_c=delta, home_temp=home.value_c)


def _send_stop_notification(settings, home, delta, active_transfer):
    duration_min = int((utcnow() - active_transfer.started_at).total_seconds() // 60)
    subject = "Solar Heat: Home has reached your desired temperature"
    body = (
        f"Home: {home.value_c:.1f}°C (desired: {settings.desired_home_temp_c:.1f}°C)\n"
        f"Transfer running for about {duration_min} minutes.\n\n"
        "Consider stopping the heat transfer now."
    )
    _send_notification(settings, "stop", subject, body, delta_c=delta, home_temp=home.value_c)


def evaluate_notifications(app):
    global _warm_window_notified

    with app.app_context():
        settings = Settings.get()
        if not settings or not settings.setup_complete:
            return

        home = _latest_reading("home")
        conservatory = _latest_reading("conservatory")
        if home is None or conservatory is None:
            return

        delta = conservatory.value_c - home.value_c
        active_transfer = (
            HeatTransferEvent.query.filter_by(ended_at=None).order_by(HeatTransferEvent.started_at.desc()).first()
        )

        if active_transfer:
            _warm_window_notified = False
            if home.value_c >= settings.desired_home_temp_c:
                already_notified = NotificationLog.query.filter(
                    NotificationLog.kind == "stop",
                    NotificationLog.sent_at >= active_transfer.started_at,
                ).first()
                if not already_notified:
                    _send_stop_notification(settings, home, delta, active_transfer)
            return

        if delta < settings.delta_threshold_c:
            _warm_window_notified = False
            return

        if home.value_c >= settings.desired_home_temp_c:
            return

        if not _warm_window_notified:
            _send_start_notification(settings, home, conservatory, delta)
            _warm_window_notified = True
            return

        last_start = NotificationLog.query.filter_by(kind="start").order_by(NotificationLog.sent_at.desc()).first()
        if last_start and utcnow() - last_start.sent_at >= timedelta(minutes=settings.renotify_cooldown_min):
            _send_start_notification(settings, home, conservatory, delta)


def should_run_scheduler(app):
    if app.config.get("TESTING"):
        return False
    # Under the Werkzeug reloader, the parent process re-execs a child with
    # WERKZEUG_RUN_MAIN=true to do the actual serving; only that child should
    # run the scheduler, or jobs fire twice.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return False
    return True


def init_scheduler(app):
    """Start the background weather-ingestion and notification jobs, once per process.

    Assumes a single worker process (see entrypoint.sh) - APScheduler has no
    cross-process coordination, so multiple workers would each run their own
    copy of these jobs and duplicate every fetch/notification.
    """
    if not should_run_scheduler(app):
        return None

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        fetch_and_store_current_weather,
        "interval",
        minutes=CURRENT_WEATHER_INTERVAL_MINUTES,
        args=[app],
        id="fetch_current_weather",
        next_run_time=datetime.now(),
        misfire_grace_time=60,
    )
    scheduler.add_job(
        fetch_and_store_forecast,
        "interval",
        hours=FORECAST_INTERVAL_HOURS,
        args=[app],
        id="fetch_forecast",
        next_run_time=datetime.now(),
        misfire_grace_time=60,
    )
    scheduler.add_job(
        evaluate_notifications,
        "interval",
        minutes=NOTIFICATION_CHECK_INTERVAL_MINUTES,
        args=[app],
        id="evaluate_notifications",
        next_run_time=datetime.now(),
        misfire_grace_time=60,
    )
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))
    return scheduler
