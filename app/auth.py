import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request
from flask_jwt_extended import create_access_token
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_auth_request
from google.oauth2 import id_token as google_id_token
from jwt.exceptions import PyJWTError
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, limiter
from app.email import send_email
from app.models import PasswordResetToken, User

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8
RESET_TOKEN_TTL = timedelta(hours=1)
RESET_REQUESTED_MESSAGE = "If an account exists with that email, we sent a reset link."


@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per minute")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    confirm_password = data.get("confirm_password") or ""

    if not email or not EMAIL_RE.match(email):
        return jsonify({"error": "A valid email is required"}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify(
            {"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}
        ), 400
    if password != confirm_password:
        return jsonify({"error": "Passwords do not match"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 400

    user = User(email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()

    return jsonify({"id": user.id, "email": user.email}), 201


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token}), 200


@auth_bp.route("/google", methods=["POST"])
@limiter.limit("5 per minute")
def google_signin():
    data = request.get_json(silent=True) or {}
    credential = data.get("credential") or ""

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    if not client_id:
        return jsonify({"error": "Google sign-in is not configured"}), 500

    try:
        idinfo = google_id_token.verify_oauth2_token(
            credential, google_auth_request.Request(), client_id
        )
    except (PyJWTError, google_auth_exceptions.GoogleAuthError, ValueError):
        return jsonify({"error": "Invalid Google credential"}), 401

    google_sub = idinfo["sub"]
    email = (idinfo.get("email") or "").strip().lower()
    email_verified = idinfo.get("email_verified", False)

    user = User.query.filter_by(google_sub=google_sub).first()
    is_new_user = False
    if not user:
        existing = User.query.filter_by(email=email).first() if email else None
        if existing:
            if not email_verified:
                return jsonify(
                    {"error": "This email is already registered. Sign in with your password instead."}
                ), 401
            existing.google_sub = google_sub
            user = existing
        else:
            user = User(email=email, google_sub=google_sub, password_hash=None)
            db.session.add(user)
            is_new_user = True
        db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "email": user.email, "is_new_user": is_new_user}), 200


@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    user = User.query.filter_by(email=email).first() if email else None
    if user:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        db.session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.utcnow() + RESET_TOKEN_TTL,
            )
        )
        db.session.commit()

        base_url = (os.environ.get("APP_BASE_URL") or request.host_url).rstrip("/")
        reset_link = f"{base_url}/reset-password?token={raw_token}"
        send_email(
            user.email,
            "Reset your password",
            render_template("emails/password_reset.html", reset_url=reset_link),
        )

    # Same response whether or not the email is registered - don't leak that.
    return jsonify({"message": RESET_REQUESTED_MESSAGE}), 200


@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("5 per minute")
def reset_password():
    data = request.get_json(silent=True) or {}
    raw_token = data.get("token") or ""
    new_password = data.get("new_password") or ""

    if len(new_password) < MIN_PASSWORD_LENGTH:
        return jsonify(
            {"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"}
        ), 400

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    reset = PasswordResetToken.query.filter_by(token_hash=token_hash).first()

    if not reset or reset.used_at is not None or reset.expires_at < datetime.utcnow():
        return jsonify({"error": "This reset link is invalid or has expired"}), 400

    user = db.session.get(User, reset.user_id)
    user.password_hash = generate_password_hash(new_password)
    reset.used_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Password updated. You can sign in now."}), 200
