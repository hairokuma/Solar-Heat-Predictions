from datetime import datetime, timezone

from .extensions import db


def utcnow():
    # Naive on purpose: SQLite (via SQLAlchemy's DateTime type) drops tzinfo
    # on round-trip, so a value read back from the DB is always naive. Using
    # a tz-aware value here would only match freshly-created, not-yet-reloaded
    # rows, and blow up (TypeError: naive vs aware) as soon as it's compared
    # against anything that came back from a query.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Settings(db.Model):
    """Singleton row (id=1) holding all operational configuration.

    Populated by the first-run setup wizard and editable afterwards from
    /settings. Deliberately kept out of .env so it can be changed at
    runtime without a container restart.
    """

    __tablename__ = "settings"

    SINGLETON_ID = 1

    id = db.Column(db.Integer, primary_key=True)

    location_name = db.Column(db.String(120))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    weather_api_key = db.Column(db.String(120))

    delta_threshold_c = db.Column(db.Float, nullable=False, default=3.0)
    desired_home_temp_c = db.Column(db.Float, nullable=False, default=21.0)
    renotify_cooldown_min = db.Column(db.Integer, nullable=False, default=60)

    notify_email = db.Column(db.String(255))
    smtp_host = db.Column(db.String(255))
    smtp_port = db.Column(db.Integer, default=587)
    smtp_username = db.Column(db.String(255))
    smtp_password = db.Column(db.String(255))
    smtp_use_tls = db.Column(db.Boolean, nullable=False, default=True)

    setup_complete = db.Column(db.Boolean, nullable=False, default=False)

    @classmethod
    def get(cls):
        return db.session.get(cls, cls.SINGLETON_ID)

    @classmethod
    def is_configured(cls):
        row = cls.get()
        return bool(row and row.setup_complete)


class Sensor(db.Model):
    """A registered physical sensor, one API key per device.

    Each sensor is bound to a single location: the key identifies both who
    is posting and where their readings belong, so a compromised or
    misconfigured device can only ever write to its own location, and can be
    revoked individually without affecting other sensors.
    """

    __tablename__ = "sensors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    location = db.Column(db.String(20), nullable=False)
    api_key = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime)


class CustomLocation(db.Model):
    """A user-added location, on top of the built-in DEFAULT_LOCATIONS.

    Custom locations are for logging only: readings are stored, shown on the
    dashboard and accepted from sensors, but they take no part in
    predictions, the roadmap or notifications, which only look at Home and
    Conservatory.
    """

    __tablename__ = "custom_locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class TemperatureReading(db.Model):
    __tablename__ = "temperature_readings"

    DEFAULT_LOCATIONS = ("home", "conservatory")
    SOURCES = ("manual", "sensor")

    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(20), nullable=False)
    value_c = db.Column(db.Float, nullable=False)
    humidity_pct = db.Column(db.Float)
    source = db.Column(db.String(10), nullable=False, default="manual")
    sensor_id = db.Column(db.String(50))
    recorded_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    @classmethod
    def locations(cls):
        """The defaults followed by custom locations, in the order they were added."""
        custom = CustomLocation.query.order_by(CustomLocation.created_at.asc(), CustomLocation.id.asc())
        return list(cls.DEFAULT_LOCATIONS) + [loc.name for loc in custom]


class WeatherObservation(db.Model):
    __tablename__ = "weather_observations"

    id = db.Column(db.Integer, primary_key=True)
    fetched_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    temp_c = db.Column(db.Float)
    cloud_pct = db.Column(db.Float)
    humidity = db.Column(db.Float)
    wind_speed = db.Column(db.Float)
    condition = db.Column(db.String(120))
    raw_json = db.Column(db.Text)


class WeatherForecast(db.Model):
    __tablename__ = "weather_forecasts"

    id = db.Column(db.Integer, primary_key=True)
    fetched_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    forecast_for = db.Column(db.DateTime, nullable=False)
    temp_c = db.Column(db.Float)
    cloud_pct = db.Column(db.Float)
    condition = db.Column(db.String(120))
    raw_json = db.Column(db.Text)


class HeatTransferEvent(db.Model):
    __tablename__ = "heat_transfer_events"

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    ended_at = db.Column(db.DateTime)
    home_temp_start = db.Column(db.Float)
    home_temp_end = db.Column(db.Float)
    conservatory_temp_start = db.Column(db.Float)
    conservatory_temp_end = db.Column(db.Float)
    effectiveness = db.Column(db.Float)
    notes = db.Column(db.Text)

    @property
    def is_active(self):
        return self.ended_at is None


class NotificationLog(db.Model):
    __tablename__ = "notification_logs"

    KINDS = ("start", "stop")

    id = db.Column(db.Integer, primary_key=True)
    sent_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    kind = db.Column(db.String(10), nullable=False)
    delta_c = db.Column(db.Float)
    home_temp = db.Column(db.Float)
    success = db.Column(db.Boolean, nullable=False, default=True)
