from datetime import timedelta

from flask import Blueprint, render_template

from ..models import HeatTransferEvent, Settings, TemperatureReading, WeatherObservation, utcnow
from ..services.timezones import utc_iso
from ..services.validation import MAX_HUMIDITY_PCT, MAX_REASONABLE_TEMP_C, MIN_HUMIDITY_PCT, MIN_REASONABLE_TEMP_C

web_bp = Blueprint("web", __name__)

HISTORY_HOURS = 48


@web_bp.get("/")
def dashboard():
    return render_template("web/dashboard.html", **dashboard_context())


def dashboard_context():
    """Everything web/dashboard.html needs, shared with routes that re-render
    the dashboard (e.g. a rejected reading from the log-reading dialog)."""
    latest = {
        location: TemperatureReading.query.filter_by(location=location)
        .order_by(TemperatureReading.recorded_at.desc())
        .first()
        for location in TemperatureReading.LOCATIONS
    }

    cutoff = utcnow() - timedelta(hours=HISTORY_HOURS)
    history_rows = (
        TemperatureReading.query.filter(TemperatureReading.recorded_at >= cutoff)
        .order_by(TemperatureReading.recorded_at.asc())
        .all()
    )
    history = {
        location: [
            {"t": utc_iso(row.recorded_at), "v": row.value_c}
            for row in history_rows
            if row.location == location
        ]
        for location in TemperatureReading.LOCATIONS
    }
    # Humidity is optional per reading, so only locations that actually
    # report it get a series (plotted on the chart's right-hand axis).
    humidity_history = {}
    for row in history_rows:
        if row.humidity_pct is not None:
            humidity_history.setdefault(row.location, []).append(
                {"t": utc_iso(row.recorded_at), "v": row.humidity_pct}
            )
    # Outdoor temperature comes from the weather observations the scheduler
    # stores every 30 minutes, not from TemperatureReading.
    history["outdoor"] = [
        {"t": utc_iso(row.fetched_at), "v": row.temp_c}
        for row in WeatherObservation.query.filter(WeatherObservation.fetched_at >= cutoff)
        .order_by(WeatherObservation.fetched_at.asc())
        .all()
        if row.temp_c is not None
    ]

    weather = WeatherObservation.query.order_by(WeatherObservation.fetched_at.desc()).first()

    active = (
        HeatTransferEvent.query.filter_by(ended_at=None).order_by(HeatTransferEvent.started_at.desc()).first()
    )
    active_duration_minutes = None
    if active:
        active_duration_minutes = int((utcnow() - active.started_at).total_seconds() // 60)

    transfer_windows = [
        {"start": utc_iso(t.started_at), "end": utc_iso(t.ended_at) if t.ended_at else None}
        for t in HeatTransferEvent.query.filter(HeatTransferEvent.started_at >= cutoff).all()
    ]

    should_highlight_start = False
    settings = Settings.get()
    home_reading = latest.get("home")
    conservatory_reading = latest.get("conservatory")
    if settings and not active and home_reading and conservatory_reading:
        delta = conservatory_reading.value_c - home_reading.value_c
        should_highlight_start = (
            delta >= settings.delta_threshold_c and home_reading.value_c < settings.desired_home_temp_c
        )

    return dict(
        latest=latest,
        history=history,
        humidity_history=humidity_history,
        history_hours=HISTORY_HOURS,
        weather=weather,
        active_transfer=active,
        active_duration_minutes=active_duration_minutes,
        transfer_windows=transfer_windows,
        should_highlight_start=should_highlight_start,
        roadmap=roadmap_context(),
        min_temp_c=MIN_REASONABLE_TEMP_C,
        max_temp_c=MAX_REASONABLE_TEMP_C,
        min_humidity_pct=MIN_HUMIDITY_PCT,
        max_humidity_pct=MAX_HUMIDITY_PCT,
    )


from . import readings, roadmap, sensors, settings, transfers  # noqa: E402,F401  (register routes on web_bp)
from .roadmap import roadmap_context  # noqa: E402
