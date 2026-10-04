import os
from datetime import timedelta

from flask import Flask, render_template
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import StaticPool

db = SQLAlchemy()
jwt = JWTManager()


def create_app(config_overrides=None):
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL", "sqlite:///job_tracker.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.environ.get(
        "JWT_SECRET_KEY", "dev-only-change-me"
    )
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(days=1)

    if config_overrides:
        app.config.update(config_overrides)

    # SQLite in-memory DBs (used by tests) live on a single connection,
    # otherwise each new connection gets its own empty database.
    if app.config["SQLALCHEMY_DATABASE_URI"] in ("sqlite://", "sqlite:///:memory:"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }

    db.init_app(app)
    jwt.init_app(app)

    from app.auth import auth_bp
    from app.applications import applications_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(applications_bp, url_prefix="/api/applications")

    @app.route("/")
    def index():
        return render_template("index.html")

    with app.app_context():
        db.create_all()

    return app
