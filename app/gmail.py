import os
from urllib.parse import urlencode

import requests
from flask import Blueprint, current_app, jsonify, redirect, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app import db, limiter
from app.crypto import TokenEncryptionNotConfigured, encrypt_token
from app.models import User

gmail_bp = Blueprint("gmail", __name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
STATE_SALT = "gmail-connect-state"
STATE_MAX_AGE_SECONDS = 600


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
