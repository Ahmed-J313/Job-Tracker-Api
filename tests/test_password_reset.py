import hashlib
from datetime import datetime, timedelta

import pytest

from app import create_app
from app import db as _db
from app.models import PasswordResetToken

GENERIC_MESSAGE = "If an account exists with that email, we sent a reset link."


def _make_token(app, user_id, raw_token, expires_delta=timedelta(hours=1), used=False):
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    with app.app_context():
        _db.session.add(
            PasswordResetToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=datetime.utcnow() + expires_delta,
                used_at=datetime.utcnow() if used else None,
            )
        )
        _db.session.commit()


def test_forgot_password_unknown_email_returns_generic_message(client):
    resp = client.post("/api/auth/forgot-password", json={"email": "nope@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["message"] == GENERIC_MESSAGE


def test_forgot_password_known_email_returns_same_message(client, user):
    resp = client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["message"] == GENERIC_MESSAGE


def test_forgot_password_creates_token_for_known_user(app, client, user):
    client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    with app.app_context():
        count = PasswordResetToken.query.filter_by(user_id=user).count()
    assert count == 1


def test_forgot_password_creates_no_token_for_unknown_user(app, client):
    client.post("/api/auth/forgot-password", json={"email": "nope@example.com"})
    with app.app_context():
        count = PasswordResetToken.query.count()
    assert count == 0


def test_reset_password_with_valid_token(app, client, user):
    _make_token(app, user, "goodtoken")
    resp = client.post(
        "/api/auth/reset-password",
        json={"token": "goodtoken", "new_password": "newpassword123"},
    )
    assert resp.status_code == 200

    login_resp = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "newpassword123"},
    )
    assert login_resp.status_code == 200


def test_reset_password_expired_token_rejected(app, client, user):
    _make_token(app, user, "expiredtoken", expires_delta=timedelta(hours=-1))
    resp = client.post(
        "/api/auth/reset-password",
        json={"token": "expiredtoken", "new_password": "newpassword123"},
    )
    assert resp.status_code == 400


def test_reset_password_used_token_rejected(app, client, user):
    _make_token(app, user, "usedtoken", used=True)
    resp = client.post(
        "/api/auth/reset-password",
        json={"token": "usedtoken", "new_password": "newpassword123"},
    )
    assert resp.status_code == 400


def test_reset_password_unknown_token_rejected(client):
    resp = client.post(
        "/api/auth/reset-password",
        json={"token": "nonexistent", "new_password": "newpassword123"},
    )
    assert resp.status_code == 400


def test_reset_password_token_is_single_use(app, client, user):
    _make_token(app, user, "onceonly")
    first = client.post(
        "/api/auth/reset-password",
        json={"token": "onceonly", "new_password": "firstpassword123"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/auth/reset-password",
        json={"token": "onceonly", "new_password": "secondpassword123"},
    )
    assert second.status_code == 400


def test_reset_password_short_password_rejected(app, client, user):
    _make_token(app, user, "shortpwtoken")
    resp = client.post(
        "/api/auth/reset-password",
        json={"token": "shortpwtoken", "new_password": "short"},
    )
    assert resp.status_code == 400


@pytest.fixture
def rate_limited_client():
    flask_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "JWT_SECRET_KEY": "test-secret",
            "RATELIMIT_ENABLED": True,
        }
    )
    test_client = flask_app.test_client()
    yield test_client
    with flask_app.app_context():
        _db.drop_all()


def test_forgot_password_rate_limited(rate_limited_client):
    for _ in range(5):
        resp = rate_limited_client.post(
            "/api/auth/forgot-password", json={"email": "someone@example.com"}
        )
        assert resp.status_code == 200

    resp = rate_limited_client.post(
        "/api/auth/forgot-password", json={"email": "someone@example.com"}
    )
    assert resp.status_code == 429


def test_reset_password_rate_limited(rate_limited_client):
    for _ in range(5):
        resp = rate_limited_client.post(
            "/api/auth/reset-password",
            json={"token": "x", "new_password": "newpassword123"},
        )
        assert resp.status_code == 400

    resp = rate_limited_client.post(
        "/api/auth/reset-password",
        json={"token": "x", "new_password": "newpassword123"},
    )
    assert resp.status_code == 429
