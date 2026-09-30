from datetime import datetime

from flask import flash, redirect, render_template, request, url_for

from . import web_bp
from ..extensions import db
from ..models import HeatTransferEvent, TemperatureReading, utcnow
from ..services.timezones import local_to_utc


def _latest_reading(location):
    return (
        TemperatureReading.query.filter_by(location=location)
        .order_by(TemperatureReading.recorded_at.desc())
        .first()
    )


def active_transfer():
    return (
        HeatTransferEvent.query.filter_by(ended_at=None)
        .order_by(HeatTransferEvent.started_at.desc())
        .first()
    )


@web_bp.get("/transfers")
def list_transfers():
    transfers = HeatTransferEvent.query.order_by(HeatTransferEvent.started_at.desc()).all()
    return render_template("web/transfers.html", transfers=transfers)


@web_bp.post("/transfers/start")
def start_transfer():
    if active_transfer():
        flash("A transfer is already active.", "error")
        return redirect(url_for("web.dashboard"))

    home = _latest_reading("home")
    conservatory = _latest_reading("conservatory")
    if home is None or conservatory is None:
        flash("Log a Home and Conservatory reading first.", "error")
        return redirect(url_for("web.dashboard"))

    transfer = HeatTransferEvent(
        started_at=utcnow(),
        home_temp_start=home.value_c,
        conservatory_temp_start=conservatory.value_c,
    )
    db.session.add(transfer)
    db.session.commit()
    flash("Transfer started.", "success")
    return redirect(url_for("web.dashboard"))


@web_bp.post("/transfers/<int:transfer_id>/stop")
def stop_transfer(transfer_id):
    transfer = db.session.get(HeatTransferEvent, transfer_id)
    if transfer is None or transfer.ended_at is not None:
        flash("That transfer isn't active.", "error")
        return redirect(url_for("web.dashboard"))

    home = _latest_reading("home")
    conservatory = _latest_reading("conservatory")

    transfer.ended_at = utcnow()
    transfer.home_temp_end = home.value_c if home else None
    transfer.conservatory_temp_end = conservatory.value_c if conservatory else None
    if transfer.home_temp_end is not None and transfer.home_temp_start is not None:
        transfer.effectiveness = transfer.home_temp_end - transfer.home_temp_start

    db.session.commit()
    flash("Transfer stopped.", "success")
    return redirect(url_for("web.dashboard"))


@web_bp.get("/transfers/<int:transfer_id>")
def transfer_detail(transfer_id):
    transfer = db.session.get(HeatTransferEvent, transfer_id)
    if transfer is None:
        flash("Transfer not found.", "error")
        return redirect(url_for("web.list_transfers"))
    return render_template("web/transfer_detail.html", transfer=transfer)


@web_bp.post("/transfers/<int:transfer_id>/edit")
def edit_transfer(transfer_id):
    transfer = db.session.get(HeatTransferEvent, transfer_id)
    if transfer is None:
        flash("Transfer not found.", "error")
        return redirect(url_for("web.list_transfers"))

    errors = []

    def parse_dt(raw):
        raw = (raw or "").strip()
        if not raw:
            return None
        try:
            return local_to_utc(datetime.fromisoformat(raw))
        except ValueError:
            errors.append("Timestamps must be valid date/times.")
            return None

    def parse_float(raw):
        raw = (raw or "").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            errors.append("Temperatures must be numbers.")
            return None

    started_at = parse_dt(request.form.get("started_at"))
    ended_at = parse_dt(request.form.get("ended_at"))
    home_temp_start = parse_float(request.form.get("home_temp_start"))
    home_temp_end = parse_float(request.form.get("home_temp_end"))
    conservatory_temp_start = parse_float(request.form.get("conservatory_temp_start"))
    conservatory_temp_end = parse_float(request.form.get("conservatory_temp_end"))
    notes = (request.form.get("notes") or "").strip()

    if started_at is None and "Timestamps must be valid date/times." not in errors:
        errors.append("Start time is required.")

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template("web/transfer_detail.html", transfer=transfer, form=request.form), 400

    transfer.started_at = started_at
    transfer.ended_at = ended_at
    transfer.home_temp_start = home_temp_start
    transfer.home_temp_end = home_temp_end
    transfer.conservatory_temp_start = conservatory_temp_start
    transfer.conservatory_temp_end = conservatory_temp_end
    transfer.notes = notes or None
    transfer.effectiveness = (
        home_temp_end - home_temp_start if home_temp_end is not None and home_temp_start is not None else None
    )

    db.session.commit()
    flash("Transfer updated.", "success")
    return redirect(url_for("web.transfer_detail", transfer_id=transfer.id))


@web_bp.post("/transfers/<int:transfer_id>/delete")
def delete_transfer(transfer_id):
    transfer = db.session.get(HeatTransferEvent, transfer_id)
    if transfer is not None:
        db.session.delete(transfer)
        db.session.commit()
        flash("Transfer deleted.", "success")
    return redirect(url_for("web.list_transfers"))
