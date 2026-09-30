from datetime import datetime

from flask import flash, redirect, render_template, request, url_for

from . import dashboard_context, web_bp
from ..extensions import db
from ..models import TemperatureReading, utcnow
from ..services.timezones import local_to_utc
from ..services.validation import (
    MAX_HUMIDITY_PCT,
    MAX_REASONABLE_TEMP_C,
    MIN_HUMIDITY_PCT,
    MIN_REASONABLE_TEMP_C,
    is_reasonable_temp,
    is_valid_humidity,
)


@web_bp.post("/readings")
def create_reading():
    location = (request.form.get("location") or "").strip().lower()
    recorded_at_raw = (request.form.get("recorded_at") or "").strip()

    errors = []
    if location not in TemperatureReading.locations():
        errors.append("Choose a valid location.")

    try:
        value_c = float(request.form.get("value_c", ""))
    except ValueError:
        errors.append("Temperature must be a number.")
        value_c = None
    else:
        if not is_reasonable_temp(value_c):
            errors.append(f"Temperature must be between {MIN_REASONABLE_TEMP_C} and {MAX_REASONABLE_TEMP_C}°C.")

    humidity_raw = (request.form.get("humidity_pct") or "").strip()
    humidity_pct = None
    if humidity_raw:
        try:
            humidity_pct = float(humidity_raw)
        except ValueError:
            errors.append("Humidity must be a number.")
        else:
            if not is_valid_humidity(humidity_pct):
                errors.append(f"Humidity must be between {MIN_HUMIDITY_PCT} and {MAX_HUMIDITY_PCT}%.")

    recorded_at = utcnow()
    if recorded_at_raw:
        try:
            recorded_at = local_to_utc(datetime.fromisoformat(recorded_at_raw))
        except ValueError:
            errors.append("Timestamp must be a valid date/time.")

    if errors:
        # Re-render rather than redirect so the dialog reopens with what was
        # typed, showing the errors inside it instead of behind the backdrop.
        return render_template(
            "web/dashboard.html", **dashboard_context(), reading_form=request.form, reading_errors=errors
        ), 400

    reading = TemperatureReading(
        location=location,
        value_c=value_c,
        humidity_pct=humidity_pct,
        source="manual",
        recorded_at=recorded_at,
    )
    db.session.add(reading)
    db.session.commit()

    humidity_note = f" / {humidity_pct}% RH" if humidity_pct is not None else ""
    flash(f"Logged {value_c}°C{humidity_note} for {location}.", "success")
    return redirect(url_for("web.dashboard"))
