from flask import render_template

from . import web_bp
from ..services.predictions import MIN_TRAINING_SAMPLES, average_effectiveness, build_roadmap


@web_bp.get("/roadmap")
def roadmap():
    slots = build_roadmap()
    avg_effectiveness, effectiveness_count = average_effectiveness()

    days = {}
    for slot in slots:
        day_key = slot["forecast_for"].date()
        days.setdefault(day_key, []).append(slot)

    return render_template(
        "web/roadmap.html",
        days=days,
        has_forecasts=bool(slots),
        using_model=slots[0]["using_model"] if slots else False,
        min_training_samples=MIN_TRAINING_SAMPLES,
        avg_effectiveness=avg_effectiveness,
        effectiveness_count=effectiveness_count,
    )
