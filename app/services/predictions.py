import bisect
import math
from datetime import timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import HeatTransferEvent, Settings, TemperatureReading, WeatherForecast, WeatherObservation, utcnow

MIN_TRAINING_SAMPLES = 15
MATCH_TOLERANCE_MINUTES = 90
ROADMAP_DAYS = 5

# Trained fresh on every roadmap request instead of persisted and retrained
# nightly: with a personal home dataset (dozens to low hundreds of rows),
# fitting a plain LinearRegression takes single-digit milliseconds, so
# caching/persisting a model would add real complexity (storage, staleness,
# invalidation on new readings) for no measurable benefit.


def _feature_row(dt, outdoor_temp, cloud_pct):
    hour_frac = dt.hour + dt.minute / 60
    hour_angle = 2 * math.pi * hour_frac / 24
    day_angle = 2 * math.pi * dt.timetuple().tm_yday / 365.25
    return [
        outdoor_temp,
        cloud_pct if cloud_pct is not None else 50.0,
        math.sin(hour_angle),
        math.cos(hour_angle),
        math.sin(day_angle),
        math.cos(day_angle),
    ]


def _build_training_data(location):
    observations = WeatherObservation.query.order_by(WeatherObservation.fetched_at.asc()).all()
    if not observations:
        return [], []
    obs_times = [o.fetched_at for o in observations]
    tolerance = timedelta(minutes=MATCH_TOLERANCE_MINUTES)

    readings = (
        TemperatureReading.query.filter_by(location=location).order_by(TemperatureReading.recorded_at.asc()).all()
    )

    features, targets = [], []
    for reading in readings:
        idx = bisect.bisect_left(obs_times, reading.recorded_at)
        candidates = []
        if idx < len(observations):
            candidates.append(observations[idx])
        if idx > 0:
            candidates.append(observations[idx - 1])
        if not candidates:
            continue
        nearest = min(candidates, key=lambda o: abs(o.fetched_at - reading.recorded_at))
        if abs(nearest.fetched_at - reading.recorded_at) > tolerance or nearest.temp_c is None:
            continue
        features.append(_feature_row(reading.recorded_at, nearest.temp_c, nearest.cloud_pct))
        targets.append(reading.value_c)
    return features, targets


def _train_model(location):
    features, targets = _build_training_data(location)
    if len(features) < MIN_TRAINING_SAMPLES:
        return None

    from sklearn.linear_model import LinearRegression

    model = LinearRegression()
    model.fit(features, targets)
    return model


def _heuristic_predict(location, dt, outdoor_temp, cloud_pct):
    if location == "conservatory":
        daylight = 8 <= dt.hour <= 17
        sunny = cloud_pct is not None and cloud_pct < 30
        bonus = 8.0 if (daylight and sunny) else (3.0 if daylight else 0.5)
        return outdoor_temp + bonus

    # No model for home yet: assume it stays close to the last known
    # reading, since indoor temperature is dominated by heating/insulation
    # rather than outdoor conditions.
    latest = (
        TemperatureReading.query.filter_by(location="home")
        .order_by(TemperatureReading.recorded_at.desc())
        .first()
    )
    return latest.value_c if latest else outdoor_temp + 5.0


def _latest_forecasts(days=ROADMAP_DAYS):
    """Forecasts get refetched every 3h; keep only the most recently fetched
    row for each forecast_for slot instead of showing stale duplicates."""
    latest_per_slot = (
        db.session.query(
            WeatherForecast.forecast_for,
            func.max(WeatherForecast.fetched_at).label("latest_fetch"),
        )
        .group_by(WeatherForecast.forecast_for)
        .subquery()
    )
    cutoff = utcnow() + timedelta(days=days)
    return (
        WeatherForecast.query.join(
            latest_per_slot,
            db.and_(
                WeatherForecast.forecast_for == latest_per_slot.c.forecast_for,
                WeatherForecast.fetched_at == latest_per_slot.c.latest_fetch,
            ),
        )
        .filter(WeatherForecast.forecast_for >= utcnow(), WeatherForecast.forecast_for <= cutoff)
        .order_by(WeatherForecast.forecast_for.asc())
        .all()
    )


def average_effectiveness():
    values = [
        t.effectiveness for t in HeatTransferEvent.query.filter(HeatTransferEvent.effectiveness.isnot(None)).all()
    ]
    if not values:
        return None, 0
    return sum(values) / len(values), len(values)


def build_roadmap():
    settings = Settings.get()
    threshold = settings.delta_threshold_c if settings else 3.0

    conservatory_model = _train_model("conservatory")
    home_model = _train_model("home")

    slots = []
    for forecast in _latest_forecasts():
        if forecast.temp_c is None:
            continue

        features = _feature_row(forecast.forecast_for, forecast.temp_c, forecast.cloud_pct)

        if conservatory_model is not None:
            predicted_conservatory = float(conservatory_model.predict([features])[0])
        else:
            predicted_conservatory = _heuristic_predict(
                "conservatory", forecast.forecast_for, forecast.temp_c, forecast.cloud_pct
            )

        if home_model is not None:
            predicted_home = float(home_model.predict([features])[0])
        else:
            predicted_home = _heuristic_predict("home", forecast.forecast_for, forecast.temp_c, forecast.cloud_pct)

        delta = predicted_conservatory - predicted_home
        slots.append(
            {
                "forecast_for": forecast.forecast_for,
                "outdoor_temp": forecast.temp_c,
                "cloud_pct": forecast.cloud_pct,
                "condition": forecast.condition,
                "predicted_conservatory": round(predicted_conservatory, 1),
                "predicted_home": round(predicted_home, 1),
                "predicted_delta": round(delta, 1),
                "opportunity": delta >= threshold,
                "using_model": conservatory_model is not None and home_model is not None,
            }
        )

    return slots
