import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
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
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token}), 200


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
            "Reset your Job Tracker password",
            f"<p>Click the link below to reset your password. This link expires in 1 hour.</p>"
            f'<p><a href="{reset_link}">{reset_link}</a></p>',
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
