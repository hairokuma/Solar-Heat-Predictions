from datetime import datetime

from flask import Blueprint, jsonify, request

from ..extensions import db, limiter
from ..models import Sensor, TemperatureReading, utcnow
from ..services.validation import MAX_REASONABLE_TEMP_C, MIN_REASONABLE_TEMP_C, is_reasonable_temp

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


@api_bp.get("/ping")
def ping():
    return jsonify(status="ok")


@api_bp.post("/readings")
@limiter.limit("60/minute")
def create_reading():
    provided_key = request.headers.get("X-API-Key", "")
    sensor = Sensor.query.filter_by(api_key=provided_key).first() if provided_key else None
    if sensor is None:
        return jsonify(error="Invalid or missing X-API-Key header."), 401

    payload = request.get_json(silent=True) or {}

    body_location = (payload.get("location") or "").strip().lower()
    if body_location and body_location != sensor.location:
        return jsonify(error=f"This sensor is registered for '{sensor.location}', not '{body_location}'."), 400

    try:
        value_c = float(payload.get("value_c"))
    except (TypeError, ValueError):
        return jsonify(error="value_c must be a number."), 400
    if not is_reasonable_temp(value_c):
        return jsonify(error=f"value_c must be between {MIN_REASONABLE_TEMP_C} and {MAX_REASONABLE_TEMP_C}."), 400

    recorded_at = utcnow()
    if payload.get("recorded_at"):
        try:
            recorded_at = datetime.fromisoformat(payload["recorded_at"])
        except ValueError:
            return jsonify(error="recorded_at must be an ISO 8601 timestamp."), 400

    reading = TemperatureReading(
        location=sensor.location,
        value_c=value_c,
        source="sensor",
        sensor_id=sensor.name,
        recorded_at=recorded_at,
    )
    sensor.last_seen_at = utcnow()
    db.session.add(reading)
    db.session.commit()

    return jsonify(id=reading.id, location=reading.location, value_c=reading.value_c), 201
