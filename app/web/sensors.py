import secrets

from flask import flash, redirect, render_template, request, url_for

from . import web_bp
from ..extensions import db
from ..models import Sensor, TemperatureReading


@web_bp.get("/settings/sensors")
def list_sensors():
    sensors = Sensor.query.order_by(Sensor.created_at.asc()).all()
    return render_template("web/sensors.html", sensors=sensors, locations=TemperatureReading.LOCATIONS)


@web_bp.post("/settings/sensors")
def create_sensor():
    name = (request.form.get("name") or "").strip()
    location = (request.form.get("location") or "").strip().lower()

    errors = []
    if not name:
        errors.append("Sensor name is required.")
    if location not in TemperatureReading.LOCATIONS:
        errors.append(f"Location must be one of {TemperatureReading.LOCATIONS}.")

    if errors:
        for error in errors:
            flash(error, "error")
        return redirect(url_for("web.list_sensors"))

    sensor = Sensor(name=name, location=location, api_key=secrets.token_hex(24))
    db.session.add(sensor)
    db.session.commit()
    flash(f"Sensor '{name}' registered.", "success")
    return redirect(url_for("web.list_sensors"))


@web_bp.post("/settings/sensors/<int:sensor_id>/delete")
def delete_sensor(sensor_id):
    sensor = db.session.get(Sensor, sensor_id)
    if sensor is not None:
        db.session.delete(sensor)
        db.session.commit()
        flash(f"Sensor '{sensor.name}' revoked.", "success")
    return redirect(url_for("web.list_sensors"))
