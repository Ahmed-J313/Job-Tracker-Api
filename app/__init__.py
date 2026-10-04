import os
from datetime import timedelta

from flask import Flask, render_template
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import StaticPool

db = SQLAlchemy()
jwt = JWTManager()
limiter = Limiter(key_func=get_remote_address, default_limits=["100 per minute"])


def create_app(config_overrides=None):
    app = Flask(__name__)

    database_url = os.environ.get("DATABASE_URL")
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY")
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)
    app.config["JWT_ALGORITHM"] = "HS256"

    if config_overrides:
        app.config.update(config_overrides)

    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError("DATABASE_URL environment variable is required")
    if not app.config["JWT_SECRET_KEY"]:
        raise RuntimeError("JWT_SECRET_KEY environment variable is required")

    # Rate limiting would make login/register attempts across many tests
    # flaky and order-dependent, so it's off when TESTING is set.
    if app.config.get("TESTING"):
        app.config["RATELIMIT_ENABLED"] = False

    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql://"):
        print("Using Postgres")
    else:
        print("Using local SQLite")

    # SQLite in-memory DBs (used by tests) live on a single connection,
    # otherwise each new connection gets its own empty database.
    if app.config["SQLALCHEMY_DATABASE_URI"] in ("sqlite://", "sqlite:///:memory:"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }

    db.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)

    from app.auth import auth_bp
    from app.applications import applications_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(applications_bp, url_prefix="/api/applications")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    with app.app_context():
        db.create_all()

    return app
