from unittest.mock import patch

import pytest

from app import db as _db
from app.crypto import encrypt_token
from app.email_classifier import EmailResult
from app.gmail_client import GmailReauthRequired
from app.models import Application, EmailReviewItem, ProcessedEmail, User


@pytest.fixture
def gmail_env(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())


@pytest.fixture
def gmail_connected_user(app, user, gmail_env):
    with app.app_context():
        u = _db.session.get(User, user)
        u.gmail_connected = True
        u.gmail_refresh_token_enc = encrypt_token("raw-refresh-token")
        _db.session.commit()
    return user


# ---------- /sync ----------


def test_sync_requires_gmail_connected(client, auth_headers):
    resp = client.post("/api/gmail/sync", headers=auth_headers)
    assert resp.status_code == 400


def test_sync_requires_auth(client):
    resp = client.post("/api/gmail/sync")
    assert resp.status_code == 401


def test_sync_reauth_required_disconnects_user(client, app, gmail_connected_user, auth_headers):
    with patch("app.gmail.refresh_access_token", side_effect=GmailReauthRequired()):
        resp = client.post("/api/gmail/sync", headers=auth_headers)
    assert resp.status_code == 400
    with app.app_context():
        u = _db.session.get(User, gmail_connected_user)
        assert u.gmail_connected is False
        assert u.gmail_refresh_token_enc is None


def test_sync_updates_application_on_confident_pattern_match(client, app, gmail_connected_user, auth_headers):
    with app.app_context():
        appn = Application(user_id=gmail_connected_user, company="Acme Corp", role_title="Engineer", status="applied")
        _db.session.add(appn)
        _db.session.commit()
        app_id = appn.id

    with patch("app.gmail.refresh_access_token", return_value="fake-access-token"), patch(
        "app.gmail.list_recent_message_ids", return_value=["msg1"]
    ), patch(
        "app.gmail.get_message_summary",
        return_value={
            "id": "msg1",
            "subject": "Acme Corp interview",
            "sender": "hr@acme.com",
            "snippet": "We'd like to schedule an interview with you for the role.",
        },
    ):
        resp = client.post("/api/gmail/sync", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["scanned"] == 1
    assert len(data["updated"]) == 1
    assert data["updated"][0]["status"] == "interviewing"

    with app.app_context():
        appn = _db.session.get(Application, app_id)
        assert appn.status == "interviewing"
        assert ProcessedEmail.query.filter_by(gmail_message_id="msg1").count() == 1


def test_sync_blocks_backward_status_even_if_result_suggests_it(client, app, gmail_connected_user, auth_headers):
    with app.app_context():
        appn = Application(
            user_id=gmail_connected_user, company="Acme Corp", role_title="Engineer", status="interviewing"
        )
        _db.session.add(appn)
        _db.session.commit()
        app_id = appn.id

    with patch("app.gmail.refresh_access_token", return_value="fake-access-token"), patch(
        "app.gmail.list_recent_message_ids", return_value=["msg1"]
    ), patch(
        "app.gmail.get_message_summary",
        return_value={"id": "msg1", "subject": "Acme Corp", "sender": "hr@acme.com", "snippet": "thanks for applying"},
    ), patch(
        "app.gmail.analyze_email",
        return_value=EmailResult(application_id=app_id, status="applied", confident=True, reason="forced for test"),
    ):
        resp = client.post("/api/gmail/sync", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.get_json()["updated"] == []
    with app.app_context():
        appn = _db.session.get(Application, app_id)
        assert appn.status == "interviewing"


def test_sync_never_touches_terminal_status(client, app, gmail_connected_user, auth_headers):
    with app.app_context():
        appn = Application(user_id=gmail_connected_user, company="Acme Corp", role_title="Engineer", status="rejected")
        _db.session.add(appn)
        _db.session.commit()
        app_id = appn.id

    with patch("app.gmail.refresh_access_token", return_value="fake-access-token"), patch(
        "app.gmail.list_recent_message_ids", return_value=["msg1"]
    ), patch(
        "app.gmail.get_message_summary",
        return_value={"id": "msg1", "subject": "Acme Corp", "sender": "hr@acme.com", "snippet": "whatever"},
    ), patch(
        "app.gmail.analyze_email",
        return_value=EmailResult(application_id=app_id, status="offer", confident=True, reason="forced for test"),
    ):
        resp = client.post("/api/gmail/sync", headers=auth_headers)

    assert resp.status_code == 200
    with app.app_context():
        appn = _db.session.get(Application, app_id)
        assert appn.status == "rejected"


def test_sync_creates_review_item_when_not_confident(client, app, gmail_connected_user, auth_headers):
    with patch("app.gmail.refresh_access_token", return_value="fake-access-token"), patch(
        "app.gmail.list_recent_message_ids", return_value=["msg1"]
    ), patch(
        "app.gmail.get_message_summary",
        return_value={"id": "msg1", "subject": "Random", "sender": "x@y.com", "snippet": "ambiguous content"},
    ), patch(
        "app.gmail.analyze_email",
        return_value=EmailResult(application_id=None, status=None, confident=False, reason="genuinely unsure"),
    ):
        resp = client.post("/api/gmail/sync", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.get_json()["needs_review"] == 1
    with app.app_context():
        items = EmailReviewItem.query.filter_by(gmail_message_id="msg1").all()
        assert len(items) == 1
        assert items[0].reason == "genuinely unsure"


def test_sync_skips_silently_when_confidently_unrelated(client, app, gmail_connected_user, auth_headers):
    with patch("app.gmail.refresh_access_token", return_value="fake-access-token"), patch(
        "app.gmail.list_recent_message_ids", return_value=["msg1"]
    ), patch(
        "app.gmail.get_message_summary",
        return_value={"id": "msg1", "subject": "Your receipt", "sender": "no-reply@store.com", "snippet": "shipped"},
    ), patch(
        "app.gmail.analyze_email",
        return_value=EmailResult(application_id=None, status=None, confident=True, reason="not job related"),
    ):
        resp = client.post("/api/gmail/sync", headers=auth_headers)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["needs_review"] == 0
    assert data["skipped"] == 1
    with app.app_context():
        assert EmailReviewItem.query.count() == 0
        assert ProcessedEmail.query.filter_by(gmail_message_id="msg1").count() == 1


def test_sync_dedups_already_processed_messages(client, app, gmail_connected_user, auth_headers):
    with app.app_context():
        _db.session.add(ProcessedEmail(user_id=gmail_connected_user, gmail_message_id="msg1"))
        _db.session.commit()

    with patch("app.gmail.refresh_access_token", return_value="fake-access-token"), patch(
        "app.gmail.list_recent_message_ids", return_value=["msg1"]
    ), patch("app.gmail.get_message_summary") as mock_get:
        resp = client.post("/api/gmail/sync", headers=auth_headers)

    assert resp.status_code == 200
    assert resp.get_json()["scanned"] == 0
    mock_get.assert_not_called()


# ---------- /review-items ----------


def test_list_review_items(client, app, user, auth_headers):
    with app.app_context():
        _db.session.add(
            EmailReviewItem(
                user_id=user, gmail_message_id="m1", subject="Subj", snippet="Snip", sender="a@b.com", reason="unsure"
            )
        )
        _db.session.commit()

    resp = client.get("/api/gmail/review-items", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.get_json()
    assert len(items) == 1
    assert items[0]["reason"] == "unsure"


def test_dismiss_review_item(client, app, user, auth_headers):
    with app.app_context():
        item = EmailReviewItem(user_id=user, gmail_message_id="m1", reason="unsure")
        _db.session.add(item)
        _db.session.commit()
        item_id = item.id

    resp = client.post(f"/api/gmail/review-items/{item_id}/dismiss", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["resolution"] == "dismissed"

    resp2 = client.get("/api/gmail/review-items", headers=auth_headers)
    assert resp2.get_json() == []


def test_resolve_review_item(client, app, user, auth_headers):
    with app.app_context():
        item = EmailReviewItem(user_id=user, gmail_message_id="m1", reason="unsure")
        _db.session.add(item)
        _db.session.commit()
        item_id = item.id

    resp = client.post(f"/api/gmail/review-items/{item_id}/resolve", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["resolution"] == "resolved"


def test_cannot_dismiss_other_users_review_item(client, app, user, other_auth_headers):
    with app.app_context():
        item = EmailReviewItem(user_id=user, gmail_message_id="m1", reason="unsure")
        _db.session.add(item)
        _db.session.commit()
        item_id = item.id

    resp = client.post(f"/api/gmail/review-items/{item_id}/dismiss", headers=other_auth_headers)
    assert resp.status_code == 404


def test_review_items_require_auth(client):
    resp = client.get("/api/gmail/review-items")
    assert resp.status_code == 401
