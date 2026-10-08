import os
import resource
from datetime import datetime
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import db, limiter
from app.crypto import TokenEncryptionNotConfigured, decrypt_token, encrypt_token
from app.email_classifier import analyze_email
from app.gmail_client import (
    GmailReauthRequired,
    get_message_summary,
    list_recent_message_ids,
    refresh_access_token,
)
from app.models import Application, EmailReviewItem, ProcessedEmail, User

gmail_bp = Blueprint("gmail", __name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
STATE_SALT = "gmail-connect-state"
STATE_MAX_AGE_SECONDS = 600
SYNC_BATCH_LIMIT = 20
STATUS_RANK = {"applied": 0, "interviewing": 1, "offer": 2, "rejected": 2}


def _log_mem(label):
    # Render's free tier doesn't expose memory metrics, so this is the only
    # way to see what /sync is actually doing on the box that's OOMing -
    # temporary, pull it once we know what's going on.
    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"[gmail sync][mem] {label}: {rss_mb:.1f} MB", flush=True)


def _current_user_id():
    return int(get_jwt_identity())


def _state_serializer():
    return URLSafeTimedSerializer(current_app.config["JWT_SECRET_KEY"], salt=STATE_SALT)


def _base_url():
    return (os.environ.get("APP_BASE_URL") or request.host_url).rstrip("/")


def _redirect_uri():
    return f"{_base_url()}/api/gmail/callback"


def _app_redirect(query):
    return redirect(f"{_base_url()}/?{query}")


def exchange_code_for_tokens(code, client_id, client_secret, redirect_uri):
    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


@gmail_bp.route("/connect", methods=["GET"])
@jwt_required()
@limiter.limit("5 per minute")
def connect():
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id or not os.environ.get("TOKEN_ENCRYPTION_KEY"):
        return jsonify({"error": "Gmail connect is not configured"}), 500

    state = _state_serializer().dumps({"user_id": _current_user_id()})
    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": GMAIL_READONLY_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return jsonify({"auth_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}), 200


@gmail_bp.route("/callback", methods=["GET"])
def callback():
    code = request.args.get("code")
    state = request.args.get("state")

    if request.args.get("error") or not code or not state:
        return _app_redirect("gmail_connect_error=1")

    try:
        payload = _state_serializer().loads(state, max_age=STATE_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return _app_redirect("gmail_connect_error=1")

    user = db.session.get(User, payload.get("user_id"))
    if not user:
        return _app_redirect("gmail_connect_error=1")

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return _app_redirect("gmail_connect_error=1")

    try:
        tokens = exchange_code_for_tokens(code, client_id, client_secret, _redirect_uri())
    except requests.RequestException:
        return _app_redirect("gmail_connect_error=1")

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return _app_redirect("gmail_connect_error=1")

    try:
        user.gmail_refresh_token_enc = encrypt_token(refresh_token)
    except TokenEncryptionNotConfigured:
        return _app_redirect("gmail_connect_error=1")
    user.gmail_connected = True
    db.session.commit()

    return _app_redirect("gmail_connected=1")


@gmail_bp.route("/status", methods=["GET"])
@jwt_required()
def status():
    user = db.session.get(User, _current_user_id())
    return jsonify({"connected": bool(user.gmail_connected)}), 200


@gmail_bp.route("/disconnect", methods=["POST"])
@jwt_required()
@limiter.limit("5 per minute")
def disconnect():
    user = db.session.get(User, _current_user_id())
    user.gmail_refresh_token_enc = None
    user.gmail_connected = False
    db.session.commit()
    return jsonify({"connected": False}), 200


@gmail_bp.route("/sync", methods=["POST"])
@jwt_required()
@limiter.limit("2 per minute")
def sync():
    _log_mem("start")
    user = db.session.get(User, _current_user_id())
    if not user.gmail_connected or not user.gmail_refresh_token_enc:
        return jsonify({"error": "Gmail is not connected"}), 400

    refresh_token = decrypt_token(user.gmail_refresh_token_enc)
    if refresh_token is None:
        return jsonify({"error": "Stored Gmail credentials are invalid, please reconnect"}), 400

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return jsonify({"error": "Gmail sync is not configured"}), 500

    try:
        access_token = refresh_access_token(refresh_token, client_id, client_secret)
        _log_mem("after token refresh")
    except GmailReauthRequired:
        user.gmail_connected = False
        user.gmail_refresh_token_enc = None
        db.session.commit()
        return jsonify({"error": "Gmail connection expired, please reconnect"}), 400
    except requests.RequestException:
        return jsonify({"error": "Could not reach Google to refresh the Gmail connection"}), 502

    try:
        message_ids = list_recent_message_ids(access_token)
        _log_mem(f"after listing {len(message_ids)} message ids")
    except requests.RequestException:
        return jsonify({"error": "Could not reach Gmail"}), 502

    already_processed = {
        pe.gmail_message_id
        for pe in ProcessedEmail.query.filter_by(user_id=user.id)
        .filter(ProcessedEmail.gmail_message_id.in_(message_ids))
        .all()
    }
    new_ids = [m for m in message_ids if m not in already_processed][:SYNC_BATCH_LIMIT]
    _log_mem(f"after dedup, {len(new_ids)} new to process")

    applications = Application.query.filter_by(user_id=user.id).all()

    updated = []
    needs_review = 0
    skipped = 0

    for i, message_id in enumerate(new_ids):
        try:
            email = get_message_summary(access_token, message_id)
        except requests.RequestException:
            continue  # leave unprocessed, pick it up on the next sync

        result = analyze_email(email, applications)
        _log_mem(f"after email {i + 1}/{len(new_ids)}")
        db.session.add(ProcessedEmail(user_id=user.id, gmail_message_id=message_id))

        if result.confident and result.application_id and result.status:
            application = next((a for a in applications if a.id == result.application_id), None)
            if (
                application
                and application.status not in ("offer", "rejected")
                and STATUS_RANK[result.status] >= STATUS_RANK[application.status]
            ):
                application.status = result.status
                updated.append(
                    {"application_id": application.id, "company": application.company, "status": result.status}
                )
        elif result.confident:
            skipped += 1
        else:
            db.session.add(
                EmailReviewItem(
                    user_id=user.id,
                    gmail_message_id=message_id,
                    subject=email["subject"],
                    snippet=email["snippet"],
                    sender=email["sender"],
                    reason=result.reason,
                )
            )
            needs_review += 1

    db.session.commit()
    _log_mem("after commit, before response")

    return (
        jsonify(
            {
                "scanned": len(new_ids),
                "updated": updated,
                "needs_review": needs_review,
                "skipped": skipped,
            }
        ),
        200,
    )


@gmail_bp.route("/review-items", methods=["GET"])
@jwt_required()
def list_review_items():
    items = (
        EmailReviewItem.query.filter_by(user_id=_current_user_id(), resolution=None)
        .order_by(EmailReviewItem.created_at.desc())
        .all()
    )
    return jsonify([item.to_dict() for item in items]), 200


def _get_owned_review_item(item_id):
    return EmailReviewItem.query.filter_by(id=item_id, user_id=_current_user_id()).first()


@gmail_bp.route("/review-items/<int:item_id>/dismiss", methods=["POST"])
@jwt_required()
def dismiss_review_item(item_id):
    item = _get_owned_review_item(item_id)
    if not item:
        return jsonify({"error": "Review item not found"}), 404
    item.resolution = "dismissed"
    item.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify(item.to_dict()), 200


@gmail_bp.route("/review-items/<int:item_id>/resolve", methods=["POST"])
@jwt_required()
def resolve_review_item(item_id):
    item = _get_owned_review_item(item_id)
    if not item:
        return jsonify({"error": "Review item not found"}), 404
    item.resolution = "resolved"
    item.resolved_at = datetime.utcnow()
    db.session.commit()
    return jsonify(item.to_dict()), 200
