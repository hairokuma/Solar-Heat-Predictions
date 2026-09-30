import re

from flask import flash, redirect, render_template, request, url_for

from . import web_bp
from ..extensions import db
from ..models import CustomLocation, Sensor, TemperatureReading

# Lowercase so it matches how readings, sensors and the API normalise
# locations; "outdoor" is taken by the weather series on the dashboard chart.
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9 _-]{0,19}$")
RESERVED_NAMES = {"outdoor"}


@web_bp.get("/settings/locations")
def list_locations():
    custom = CustomLocation.query.order_by(CustomLocation.created_at.asc(), CustomLocation.id.asc()).all()
    return render_template(
        "web/locations.html", default_locations=TemperatureReading.DEFAULT_LOCATIONS, custom_locations=custom
    )


@web_bp.post("/settings/locations")
def create_location():
    name = " ".join((request.form.get("name") or "").split()).lower()

    if not NAME_PATTERN.match(name):
        flash("Location name must be 1–20 characters: letters, digits, spaces, '-' or '_'.", "error")
    elif name in RESERVED_NAMES or name in TemperatureReading.locations():
        flash(f"Location '{name}' already exists.", "error")
    else:
        db.session.add(CustomLocation(name=name))
        db.session.commit()
        flash(f"Location '{name}' added.", "success")
    return redirect(url_for("web.list_locations"))


@web_bp.post("/settings/locations/<int:location_id>/delete")
def delete_location(location_id):
    location = db.session.get(CustomLocation, location_id)
    if location is None:
        return redirect(url_for("web.list_locations"))

    if Sensor.query.filter_by(location=location.name).count():
        flash(f"Revoke the sensors bound to '{location.name}' before removing it.", "error")
        return redirect(url_for("web.list_locations"))

    db.session.delete(location)
    db.session.commit()
    flash(f"Location '{location.name}' removed. Its past readings are kept.", "success")
    return redirect(url_for("web.list_locations"))
