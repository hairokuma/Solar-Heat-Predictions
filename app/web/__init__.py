from datetime import timedelta

from flask import Blueprint, render_template

from ..models import HeatTransferEvent, Settings, TemperatureReading, WeatherObservation, utcnow
from ..services.timezones import utc_iso
from ..services.validation import MAX_HUMIDITY_PCT, MAX_REASONABLE_TEMP_C, MIN_HUMIDITY_PCT, MIN_REASONABLE_TEMP_C

web_bp = Blueprint("web", __name__)

HISTORY_HOURS = 48
TREND_WINDOW = timedelta(hours=1)


@web_bp.get("/")
def dashboard():
    return render_template("web/dashboard.html", **dashboard_context())


def dashboard_context():
    """Everything web/dashboard.html needs, shared with routes that re-render
    the dashboard (e.g. a rejected reading from the log-reading dialog)."""
    locations = TemperatureReading.locations()
    latest = {
        location: TemperatureReading.query.filter_by(location=location)
        .order_by(TemperatureReading.recorded_at.desc())
        .first()
        for location in locations
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
        for location in locations
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

    trends = {location: hourly_trend(location, latest.get(location)) for location in ("conservatory", "home")}

    return dict(
        locations=locations,
        latest=latest,
        history=history,
        humidity_history=humidity_history,
        history_hours=HISTORY_HOURS,
        weather=weather,
        active_transfer=active,
        active_duration_minutes=active_duration_minutes,
        transfer_windows=transfer_windows,
        should_highlight_start=should_highlight_start,
        trends=trends,
        roadmap=roadmap_context(),
        min_temp_c=MIN_REASONABLE_TEMP_C,
        max_temp_c=MAX_REASONABLE_TEMP_C,
        min_humidity_pct=MIN_HUMIDITY_PCT,
        max_humidity_pct=MAX_HUMIDITY_PCT,
    )


def hourly_trend(location, latest):
    """How fast ``location`` is warming (+) or cooling (-), in °C per hour.

    Compares the latest reading with the newest one at least TREND_WINDOW
    older, scaled to a per-hour rate. None when there is no reading that far
    back (within two windows), or when the latest reading is itself more than
    two windows old, since a stale rate would say nothing about "now".
    """
    if latest is None or latest.recorded_at < utcnow() - 2 * TREND_WINDOW:
        return None
    baseline = (
        TemperatureReading.query.filter(
            TemperatureReading.location == location,
            TemperatureReading.recorded_at <= latest.recorded_at - TREND_WINDOW,
            TemperatureReading.recorded_at >= latest.recorded_at - 2 * TREND_WINDOW,
        )
        .order_by(TemperatureReading.recorded_at.desc())
        .first()
    )
    if baseline is None:
        return None
    hours = (latest.recorded_at - baseline.recorded_at).total_seconds() / 3600
    return (latest.value_c - baseline.value_c) / hours


from . import locations, readings, roadmap, sensors, settings, transfers  # noqa: E402,F401  (register routes on web_bp)
from .roadmap import roadmap_context  # noqa: E402
