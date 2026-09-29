from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter


def _rate_limit_key():
    from flask import request

    return request.headers.get("X-API-Key") or (request.remote_addr or "unknown")


db = SQLAlchemy()
migrate = Migrate()
# In-memory storage: fine for the single-process deployment this app assumes
# (see entrypoint.sh) - limits reset on restart, which is an acceptable
# trade-off for a personal home app rather than adding Redis.
limiter = Limiter(key_func=_rate_limit_key, storage_uri="memory://")
