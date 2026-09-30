from datetime import datetime

from flask import flash, redirect, render_template, request, url_for

from . import dashboard_context, web_bp
from ..extensions import db
from ..models import TemperatureReading, utcnow
from ..services.validation import MAX_REASONABLE_TEMP_C, MIN_REASONABLE_TEMP_C, is_reasonable_temp


@web_bp.post("/readings")
def create_reading():
    location = (request.form.get("location") or "").strip().lower()
    recorded_at_raw = (request.form.get("recorded_at") or "").strip()

    errors = []
    if location not in TemperatureReading.LOCATIONS:
        errors.append("Choose a valid location.")

    try:
        value_c = float(request.form.get("value_c", ""))
    except ValueError:
        errors.append("Temperature must be a number.")
        value_c = None
    else:
        if not is_reasonable_temp(value_c):
            errors.append(f"Temperature must be between {MIN_REASONABLE_TEMP_C} and {MAX_REASONABLE_TEMP_C}°C.")

    recorded_at = utcnow()
    if recorded_at_raw:
        try:
            recorded_at = datetime.fromisoformat(recorded_at_raw)
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
        source="manual",
        recorded_at=recorded_at,
    )
    db.session.add(reading)
    db.session.commit()

    flash(f"Logged {value_c}°C for {location}.", "success")
    return redirect(url_for("web.dashboard"))
