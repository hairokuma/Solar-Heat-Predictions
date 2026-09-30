from flask import render_template

from . import web_bp
from ..services.predictions import MIN_TRAINING_SAMPLES, average_effectiveness, build_roadmap
from ..services.timezones import to_local


@web_bp.get("/roadmap")
def roadmap():
    return render_template("web/roadmap.html", **roadmap_context())


def roadmap_context():
    slots = build_roadmap()
    avg_effectiveness, effectiveness_count = average_effectiveness()

    days = {}
    for slot in slots:
        # Group by the viewer's local day, not the UTC day.
        day_key = to_local(slot["forecast_for"]).date()
        days.setdefault(day_key, []).append(slot)

    return dict(
        days=days,
        has_forecasts=bool(slots),
        using_model=slots[0]["using_model"] if slots else False,
        min_training_samples=MIN_TRAINING_SAMPLES,
        avg_effectiveness=avg_effectiveness,
        effectiveness_count=effectiveness_count,
    )
