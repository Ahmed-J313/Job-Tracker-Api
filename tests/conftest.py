import pytest
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from app import create_app
from app import db as _db
from app.models import Application, User


@pytest.fixture
def app():
    flask_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "JWT_SECRET_KEY": "test-secret",
        }
    )
    yield flask_app
    with flask_app.app_context():
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(app):
    with app.app_context():
        u = User(email="alice@example.com", password_hash=generate_password_hash("password123"))
        _db.session.add(u)
        _db.session.commit()
        return u.id


@pytest.fixture
def auth_headers(app, user):
    with app.app_context():
        token = create_access_token(identity=str(user))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_user(app):
    with app.app_context():
        u = User(email="bob@example.com", password_hash=generate_password_hash("password123"))
        _db.session.add(u)
        _db.session.commit()
        return u.id


@pytest.fixture
def other_auth_headers(app, other_user):
    with app.app_context():
        token = create_access_token(identity=str(other_user))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded_applications(app, user):
    with app.app_context():
        apps = [
            Application(user_id=user, company="Acme", role_title="Backend Engineer", status="applied"),
            Application(user_id=user, company="Globex", role_title="SRE", status="interviewing"),
            Application(user_id=user, company="Initech", role_title="Platform Engineer", status="offer"),
        ]
        _db.session.add_all(apps)
        _db.session.commit()
        return [a.id for a in apps]
