from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from ..extensions import db
from ..models import Settings
from ..scheduler import fetch_and_store_current_weather, fetch_and_store_forecast
from ..services.geocoding import GeocodingError, geocode_address
from ..services.notifications import EmailSendError, send_email
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
from ..services.weather import WeatherProviderError, fetch_current_weather

setup_bp = Blueprint("setup", __name__, url_prefix="/setup")

STEPS = ["location", "weather", "notifications", "email", "review"]
SESSION_KEY = "wizard_data"

REQUIRED_FOR_FINISH = [
    "location_name",
    "latitude",
    "longitude",
    "weather_api_key",
    "delta_threshold_c",
    "desired_home_temp_c",
    "renotify_cooldown_min",
    "notify_email",
    "smtp_host",
    "smtp_port",
    "smtp_username",
]


def _data():
    return session.setdefault(SESSION_KEY, {})


def _save(step_data):
    data = _data()
    data.update(step_data)
    session[SESSION_KEY] = data
    session.modified = True


@setup_bp.get("/")
def index():
    return redirect(url_for("setup.step", step=STEPS[0]))


@setup_bp.get("/<step>")
def step(step):
    if step not in STEPS:
        return redirect(url_for("setup.step", step=STEPS[0]))
    return render_template(f"setup/{step}.html", data=_data(), steps=STEPS, current=step)


@setup_bp.post("/<step>")
def step_post(step):
    if step not in STEPS:
        return redirect(url_for("setup.step", step=STEPS[0]))

    if step == "review":
        if request.form.get("action") == "finish":
            return _finish()
        return redirect(url_for("setup.step", step="review"))

    errors, cleaned = _validate_step(step, request.form)

    if errors:
        for error in errors:
            flash(error, "error")
        merged = {**_data(), **request.form}
        return render_template(f"setup/{step}.html", data=merged, steps=STEPS, current=step), 400

    _save(cleaned)
    next_index = min(STEPS.index(step) + 1, len(STEPS) - 1)
    return redirect(url_for("setup.step", step=STEPS[next_index]))


def _validate_step(step, form):
    errors = []
    cleaned = {}

    if step == "location":
        location_name = form.get("location_name", "").strip()
        try:
            latitude = float(form.get("latitude", ""))
            longitude = float(form.get("longitude", ""))
        except ValueError:
            errors.append("Latitude and longitude must be numbers.")
        else:
            if not is_valid_latitude(latitude) or not is_valid_longitude(longitude):
                errors.append("Latitude must be between -90 and 90, longitude between -180 and 180.")
            else:
                cleaned["latitude"] = latitude
                cleaned["longitude"] = longitude
        if not location_name:
            errors.append("Location name is required.")
        else:
            cleaned["location_name"] = location_name

    elif step == "weather":
        api_key = form.get("weather_api_key", "").strip()
        if not api_key:
            errors.append("Weather API key is required.")
        else:
            cleaned["weather_api_key"] = api_key

    elif step == "notifications":
        try:
            delta_threshold_c = float(form.get("delta_threshold_c", ""))
            desired_home_temp_c = float(form.get("desired_home_temp_c", ""))
            renotify_cooldown_min = int(form.get("renotify_cooldown_min", ""))
        except ValueError:
            errors.append("Threshold, desired temperature and cooldown must be numbers.")
        else:
            if not MIN_DELTA_THRESHOLD_C <= delta_threshold_c <= MAX_DELTA_THRESHOLD_C:
                errors.append(f"Delta threshold must be between {MIN_DELTA_THRESHOLD_C} and {MAX_DELTA_THRESHOLD_C}°C.")
            if not MIN_DESIRED_HOME_TEMP_C <= desired_home_temp_c <= MAX_DESIRED_HOME_TEMP_C:
                errors.append(
                    f"Desired home temperature must be between {MIN_DESIRED_HOME_TEMP_C} and {MAX_DESIRED_HOME_TEMP_C}°C."
                )
            if not MIN_COOLDOWN_MIN <= renotify_cooldown_min <= MAX_COOLDOWN_MIN:
                errors.append(f"Re-notify interval must be between {MIN_COOLDOWN_MIN} and {MAX_COOLDOWN_MIN} minutes.")
            if not errors:
                cleaned["delta_threshold_c"] = delta_threshold_c
                cleaned["desired_home_temp_c"] = desired_home_temp_c
                cleaned["renotify_cooldown_min"] = renotify_cooldown_min

    elif step == "email":
        notify_email = form.get("notify_email", "").strip()
        smtp_host = form.get("smtp_host", "").strip()
        smtp_username = form.get("smtp_username", "").strip()
        smtp_password = form.get("smtp_password", "")
        try:
            smtp_port = int(form.get("smtp_port", "587"))
        except ValueError:
            errors.append("SMTP port must be a number.")
            smtp_port = None
        else:
            if not is_valid_port(smtp_port):
                errors.append("SMTP port must be between 1 and 65535.")
        if not notify_email or not smtp_host or not smtp_username:
            errors.append("Recipient email, SMTP host and SMTP username are required.")
        elif not is_valid_email(notify_email):
            errors.append("Recipient email doesn't look like a valid address.")
        if not errors:
            cleaned.update(
                notify_email=notify_email,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                smtp_username=smtp_username,
                smtp_password=smtp_password,
                smtp_use_tls=form.get("smtp_use_tls") == "on",
            )

    return errors, cleaned


def _finish():
    data = _data()
    missing = [field for field in REQUIRED_FOR_FINISH if data.get(field) in (None, "")]
    if missing:
        flash("Please complete all steps before finishing setup.", "error")
        return redirect(url_for("setup.step", step=STEPS[0]))

    settings = Settings.get() or Settings(id=Settings.SINGLETON_ID)
    settings.location_name = data["location_name"]
    settings.latitude = data["latitude"]
    settings.longitude = data["longitude"]
    settings.weather_api_key = data["weather_api_key"]
    settings.delta_threshold_c = data["delta_threshold_c"]
    settings.desired_home_temp_c = data["desired_home_temp_c"]
    settings.renotify_cooldown_min = data["renotify_cooldown_min"]
    settings.notify_email = data["notify_email"]
    settings.smtp_host = data["smtp_host"]
    settings.smtp_port = data["smtp_port"]
    settings.smtp_username = data["smtp_username"]
    settings.smtp_password = data.get("smtp_password", "")
    settings.smtp_use_tls = bool(data.get("smtp_use_tls", True))
    settings.setup_complete = True

    db.session.add(settings)
    db.session.commit()
    session.pop(SESSION_KEY, None)
    _kick_off_weather_fetch()
    flash("Setup complete.", "success")
    return redirect(url_for("web.dashboard"))


def _kick_off_weather_fetch():
    """Fetch weather once immediately so the dashboard isn't empty for up to
    CURRENT_WEATHER_INTERVAL_MINUTES after finishing the wizard."""
    scheduler = current_app.extensions.get("weather_scheduler")
    if scheduler is None:
        return
    app_obj = current_app._get_current_object()
    scheduler.add_job(fetch_and_store_current_weather, args=[app_obj], id="fetch_current_weather_kickoff", replace_existing=True)
    scheduler.add_job(fetch_and_store_forecast, args=[app_obj], id="fetch_forecast_kickoff", replace_existing=True)


@setup_bp.post("/location/geocode")
def geocode_location():
    payload = request.get_json(silent=True) or request.form
    query = (payload.get("address") or "").strip()
    if not query:
        return jsonify(ok=False, message="Enter an address or city first."), 400

    try:
        results = geocode_address(query)
    except GeocodingError as exc:
        return jsonify(ok=False, message=str(exc)), 502

    if not results:
        return jsonify(ok=False, message="No matches found. Try a different search or enter coordinates manually.")

    return jsonify(ok=True, results=results)


@setup_bp.post("/weather/test")
def test_weather():
    payload = request.get_json(silent=True) or request.form
    try:
        latitude = float(payload.get("latitude"))
        longitude = float(payload.get("longitude"))
    except (TypeError, ValueError):
        return jsonify(ok=False, message="Enter a valid latitude/longitude first."), 400

    api_key = (payload.get("weather_api_key") or "").strip()
    if not api_key:
        return jsonify(ok=False, message="Enter an API key first."), 400

    try:
        result = fetch_current_weather(latitude, longitude, api_key)
    except WeatherProviderError as exc:
        return jsonify(ok=False, message=str(exc)), 502

    temp = result.get("main", {}).get("temp")
    return jsonify(ok=True, message=f"Connected. Current temperature: {temp}°C")


@setup_bp.post("/email/test")
def test_email():
    payload = request.get_json(silent=True) or request.form

    required = ["notify_email", "smtp_host", "smtp_username", "smtp_password"]
    if any(not str(payload.get(field) or "").strip() for field in required):
        return jsonify(ok=False, message="Fill in SMTP host, username, password and recipient first."), 400

    try:
        port = int(payload.get("smtp_port", 587))
    except (TypeError, ValueError):
        return jsonify(ok=False, message="SMTP port must be a number."), 400

    use_tls = payload.get("smtp_use_tls")
    use_tls = use_tls in (True, "true", "on", "1")

    try:
        send_email(
            host=payload["smtp_host"],
            port=port,
            username=payload["smtp_username"],
            password=payload["smtp_password"],
            use_tls=use_tls,
            from_addr=payload["smtp_username"],
            to_addr=payload["notify_email"],
            subject="Solar Heat Predictions - test email",
            body="This is a test email from the Solar Heat Predictions setup wizard.",
        )
    except EmailSendError as exc:
        return jsonify(ok=False, message=str(exc)), 502

    return jsonify(ok=True, message="Test email sent.")
