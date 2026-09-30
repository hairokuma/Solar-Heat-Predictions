from flask import flash, redirect, render_template, request, url_for

from . import web_bp
from .setup import send_test_email
from ..extensions import db
from ..models import Settings
from ..services.validation import (
    MAX_COOLDOWN_MIN,
    MAX_DELTA_THRESHOLD_C,
    MAX_DESIRED_HOME_TEMP_C,
    MIN_COOLDOWN_MIN,
    MIN_DELTA_THRESHOLD_C,
    MIN_DESIRED_HOME_TEMP_C,
    is_valid_email,
    is_valid_latitude,
    is_valid_longitude,
    is_valid_port,
)


@web_bp.get("/settings")
def settings_form():
    settings = Settings.get()
    return render_template("web/settings.html", settings=settings)


@web_bp.post("/settings/email/test")
def settings_test_email():
    payload = request.get_json(silent=True) or request.form
    settings = Settings.get()
    return send_test_email(
        payload,
        body="This is a test email from the Solar Heat Predictions settings page.",
        fallback_password=settings.smtp_password if settings else None,
    )


@web_bp.post("/settings")
def settings_update():
    settings = Settings.get()
    if settings is None:
        flash("Run the setup wizard first.", "error")
        return redirect(url_for("setup.step", step="location"))

    errors = []
    latitude = longitude = None
    try:
        latitude = float(request.form.get("latitude", ""))
        longitude = float(request.form.get("longitude", ""))
    except ValueError:
        errors.append("Latitude and longitude must be numbers.")
    else:
        if not is_valid_latitude(latitude) or not is_valid_longitude(longitude):
            errors.append("Latitude must be between -90 and 90, longitude between -180 and 180.")

    delta_threshold_c = desired_home_temp_c = renotify_cooldown_min = smtp_port = None
    try:
        delta_threshold_c = float(request.form.get("delta_threshold_c", ""))
        desired_home_temp_c = float(request.form.get("desired_home_temp_c", ""))
        renotify_cooldown_min = int(request.form.get("renotify_cooldown_min", ""))
        smtp_port = int(request.form.get("smtp_port", ""))
    except ValueError:
        errors.append("Threshold, desired temperature, cooldown and SMTP port must be numbers.")
    else:
        if not MIN_DELTA_THRESHOLD_C <= delta_threshold_c <= MAX_DELTA_THRESHOLD_C:
            errors.append(f"Delta threshold must be between {MIN_DELTA_THRESHOLD_C} and {MAX_DELTA_THRESHOLD_C}°C.")
        if not MIN_DESIRED_HOME_TEMP_C <= desired_home_temp_c <= MAX_DESIRED_HOME_TEMP_C:
            errors.append(
                f"Desired home temperature must be between {MIN_DESIRED_HOME_TEMP_C} and {MAX_DESIRED_HOME_TEMP_C}°C."
            )
        if not MIN_COOLDOWN_MIN <= renotify_cooldown_min <= MAX_COOLDOWN_MIN:
            errors.append(f"Re-notify interval must be between {MIN_COOLDOWN_MIN} and {MAX_COOLDOWN_MIN} minutes.")
        if not is_valid_port(smtp_port):
            errors.append("SMTP port must be between 1 and 65535.")

    location_name = request.form.get("location_name", "").strip()
    weather_api_key = request.form.get("weather_api_key", "").strip()
    notify_email = request.form.get("notify_email", "").strip()
    smtp_host = request.form.get("smtp_host", "").strip()
    smtp_username = request.form.get("smtp_username", "").strip()
    smtp_password = request.form.get("smtp_password", "") or settings.smtp_password
    smtp_use_tls = request.form.get("smtp_use_tls") == "on"

    if not location_name or not weather_api_key or not notify_email or not smtp_host or not smtp_username:
        errors.append("All fields except SMTP password (kept if left blank) are required.")
    elif not is_valid_email(notify_email):
        errors.append("Notification email doesn't look like a valid address.")

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template("web/settings.html", settings=settings, form=request.form), 400

    settings.location_name = location_name
    settings.latitude = latitude
    settings.longitude = longitude
    settings.weather_api_key = weather_api_key
    settings.delta_threshold_c = delta_threshold_c
    settings.desired_home_temp_c = desired_home_temp_c
    settings.renotify_cooldown_min = renotify_cooldown_min
    settings.notify_email = notify_email
    settings.smtp_host = smtp_host
    settings.smtp_port = smtp_port
    settings.smtp_username = smtp_username
    settings.smtp_password = smtp_password
    settings.smtp_use_tls = smtp_use_tls

    db.session.commit()
    flash("Settings updated.", "success")
    return redirect(url_for("web.settings_form"))
