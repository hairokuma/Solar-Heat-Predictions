import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    # A bare relative filename is resolved by Flask-SQLAlchemy against the
    # instance folder (e.g. ./instance/app.db locally). Set an absolute path
    # (e.g. /data/app.db, as docker-compose does) to place the DB elsewhere.
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "app.db")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{DATABASE_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
