from unittest.mock import patch

import pytest
from jwt.exceptions import ExpiredSignatureError, InvalidAudienceError, InvalidSignatureError

from app import db as _db
from app.models import User

GOOGLE_PATCH_TARGET = "app.auth.google_id_token.verify_oauth2_token"


def _fake_idinfo(sub="google-sub-123", email="newgoogleuser@example.com", email_verified=True):
    return {
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "iss": "https://accounts.google.com",
    }


@pytest.fixture(autouse=True)
def google_client_id(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")


def test_google_signin_valid_token_creates_new_user(client, app):
    with patch(GOOGLE_PATCH_TARGET, return_value=_fake_idinfo()):
        resp = client.post("/api/auth/google", json={"credential": "fake-token"})

    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data
    assert data["email"] == "newgoogleuser@example.com"

    with app.app_context():
        user = User.query.filter_by(google_sub="google-sub-123").first()
        assert user is not None
        assert user.password_hash is None


def test_google_signin_wrong_audience_rejected(client):
    with patch(GOOGLE_PATCH_TARGET, side_effect=InvalidAudienceError("Audience doesn't match")):
        resp = client.post("/api/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 401


def test_google_signin_expired_token_rejected(client):
    with patch(GOOGLE_PATCH_TARGET, side_effect=ExpiredSignatureError("Signature has expired")):
        resp = client.post("/api/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 401


def test_google_signin_forged_signature_rejected(client):
    with patch(GOOGLE_PATCH_TARGET, side_effect=InvalidSignatureError("Signature verification failed")):
        resp = client.post("/api/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 401


def test_google_signin_links_existing_verified_email(client, app, user):
    with patch(
        GOOGLE_PATCH_TARGET,
        return_value=_fake_idinfo(sub="google-sub-456", email="alice@example.com", email_verified=True),
    ):
        resp = client.post("/api/auth/google", json={"credential": "fake-token"})

    assert resp.status_code == 200
    with app.app_context():
        linked = User.query.filter_by(google_sub="google-sub-456").first()
        assert linked is not None
        assert linked.id == user
        assert User.query.count() == 1


def test_google_signin_unverified_email_does_not_link_or_duplicate(client, app, user):
    with patch(
        GOOGLE_PATCH_TARGET,
        return_value=_fake_idinfo(sub="google-sub-789", email="alice@example.com", email_verified=False),
    ):
        resp = client.post("/api/auth/google", json={"credential": "fake-token"})

    assert resp.status_code == 401
    with app.app_context():
        assert User.query.count() == 1
        assert User.query.filter_by(google_sub="google-sub-789").first() is None


def test_google_signin_not_configured_returns_500(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    resp = client.post("/api/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 500


def test_password_login_still_works(client, user):
    resp = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.get_json()


def test_google_only_user_cannot_password_login(client, app):
    with app.app_context():
        u = User(email="googleonly@example.com", google_sub="google-sub-999", password_hash=None)
        _db.session.add(u)
        _db.session.commit()

    resp = client.post(
        "/api/auth/login",
        json={"email": "googleonly@example.com", "password": "whatever"},
    )
    assert resp.status_code == 401
