from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from itsdangerous import URLSafeTimedSerializer

from app import db as _db
from app.crypto import decrypt_token, encrypt_token
from app.gmail import STATE_SALT
from app.models import User

EXCHANGE_PATCH_TARGET = "app.gmail.exchange_code_for_tokens"


@pytest.fixture(autouse=True)
def gmail_env(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _make_state(user_id):
    return URLSafeTimedSerializer("test-secret", salt=STATE_SALT).dumps({"user_id": user_id})


def _location_query(resp):
    return parse_qs(urlparse(resp.headers["Location"]).query)


# ---------- encryption ----------


def test_encrypt_decrypt_round_trip(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    enc = encrypt_token("my-refresh-token")
    assert enc != "my-refresh-token"
    assert decrypt_token(enc) == "my-refresh-token"


# ---------- /connect ----------


def test_connect_requires_auth(client):
    resp = client.get("/api/gmail/connect")
    assert resp.status_code == 401


def test_connect_returns_google_auth_url(client, auth_headers):
    resp = client.get("/api/gmail/connect", headers=auth_headers)
    assert resp.status_code == 200
    auth_url = resp.get_json()["auth_url"]
    parsed = urlparse(auth_url)
    assert parsed.netloc == "accounts.google.com"
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["test-client-id.apps.googleusercontent.com"]
    assert qs["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
    assert qs["access_type"] == ["offline"]
    assert qs["prompt"] == ["consent"]
    assert "state" in qs


def test_connect_not_configured_returns_500(client, auth_headers, monkeypatch):
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    resp = client.get("/api/gmail/connect", headers=auth_headers)
    assert resp.status_code == 500


# ---------- /callback ----------


def test_callback_success_stores_encrypted_token(client, app, user):
    state = _make_state(user)
    with patch(EXCHANGE_PATCH_TARGET, return_value={"refresh_token": "raw-refresh-token-123"}):
        resp = client.get(f"/api/gmail/callback?code=abc123&state={state}")

    assert resp.status_code == 302
    assert _location_query(resp).get("gmail_connected") == ["1"]

    with app.app_context():
        u = _db.session.get(User, user)
        assert u.gmail_connected is True
        assert u.gmail_refresh_token_enc is not None
        assert u.gmail_refresh_token_enc != "raw-refresh-token-123"
        assert decrypt_token(u.gmail_refresh_token_enc) == "raw-refresh-token-123"


def test_callback_google_error_redirects_with_error(client):
    resp = client.get("/api/gmail/callback?error=access_denied")
    assert resp.status_code == 302
    assert _location_query(resp).get("gmail_connect_error") == ["1"]


def test_callback_missing_code_redirects_with_error(client, user):
    state = _make_state(user)
    resp = client.get(f"/api/gmail/callback?state={state}")
    assert resp.status_code == 302
    assert _location_query(resp).get("gmail_connect_error") == ["1"]


def test_callback_invalid_state_redirects_with_error(client):
    resp = client.get("/api/gmail/callback?code=abc123&state=garbage")
    assert resp.status_code == 302
    assert _location_query(resp).get("gmail_connect_error") == ["1"]


def test_callback_expired_state_redirects_with_error(client, user):
    state = _make_state(user)
    with patch("app.gmail.STATE_MAX_AGE_SECONDS", -1):
        resp = client.get(f"/api/gmail/callback?code=abc123&state={state}")
    assert resp.status_code == 302
    assert _location_query(resp).get("gmail_connect_error") == ["1"]


def test_callback_token_exchange_failure_redirects_with_error(client, user):
    state = _make_state(user)
    with patch(EXCHANGE_PATCH_TARGET, side_effect=requests.RequestException("boom")):
        resp = client.get(f"/api/gmail/callback?code=abc123&state={state}")
    assert resp.status_code == 302
    assert _location_query(resp).get("gmail_connect_error") == ["1"]


def test_callback_no_refresh_token_redirects_with_error(client, app, user):
    state = _make_state(user)
    with patch(EXCHANGE_PATCH_TARGET, return_value={"access_token": "no-refresh-here"}):
        resp = client.get(f"/api/gmail/callback?code=abc123&state={state}")
    assert resp.status_code == 302
    assert _location_query(resp).get("gmail_connect_error") == ["1"]

    with app.app_context():
        u = _db.session.get(User, user)
        assert u.gmail_connected is False


# ---------- /status ----------


def test_status_not_connected_by_default(client, auth_headers):
    resp = client.get("/api/gmail/status", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json() == {"connected": False}


def test_status_connected_after_callback(client, app, user, auth_headers):
    state = _make_state(user)
    with patch(EXCHANGE_PATCH_TARGET, return_value={"refresh_token": "raw-token"}):
        client.get(f"/api/gmail/callback?code=abc123&state={state}")

    resp = client.get("/api/gmail/status", headers=auth_headers)
    assert resp.get_json() == {"connected": True}


# ---------- /disconnect ----------


def test_disconnect_clears_token(client, app, user, auth_headers):
    state = _make_state(user)
    with patch(EXCHANGE_PATCH_TARGET, return_value={"refresh_token": "raw-token"}):
        client.get(f"/api/gmail/callback?code=abc123&state={state}")

    resp = client.post("/api/gmail/disconnect", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json() == {"connected": False}

    with app.app_context():
        u = _db.session.get(User, user)
        assert u.gmail_connected is False
        assert u.gmail_refresh_token_enc is None


def test_disconnect_requires_auth(client):
    resp = client.post("/api/gmail/disconnect")
    assert resp.status_code == 401


# ---------- gmail never connected doesn't break anything else ----------


def test_normal_flow_unaffected_when_gmail_never_connected(client, user, auth_headers):
    login_resp = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "password123"}
    )
    assert login_resp.status_code == 200

    create_resp = client.post(
        "/api/applications",
        headers=auth_headers,
        json={"company": "Acme", "role_title": "Engineer"},
    )
    assert create_resp.status_code == 201

    stats_resp = client.get("/api/applications/stats", headers=auth_headers)
    assert stats_resp.status_code == 200
    assert stats_resp.get_json()["applied"] == 1
