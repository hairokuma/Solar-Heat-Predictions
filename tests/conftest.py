import pytest

from app import create_app
from app.extensions import db as _db
from app.extensions import limiter as _limiter


@pytest.fixture
def app():
    flask_app = create_app("config.TestConfig")
    # The Limiter's in-memory storage is a module-level singleton shared
    # across every create_app() call in the test session, so counters from
    # an earlier test's requests would otherwise leak into this one.
    _limiter.reset()
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
