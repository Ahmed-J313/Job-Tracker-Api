from datetime import datetime, date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app import db
from app.models import Application

applications_bp = Blueprint("applications", __name__)

VALID_STATUSES = {"applied", "interviewing", "offer", "rejected"}
MAX_NOTES_LENGTH = 500


def _current_user_id():
    return int(get_jwt_identity())


def _get_owned(app_id):
    return Application.query.filter_by(id=app_id, user_id=_current_user_id()).first()


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


@applications_bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    counts = {status: 0 for status in VALID_STATUSES}
    rows = (
        db.session.query(Application.status, db.func.count(Application.id))
        .filter_by(user_id=_current_user_id())
        .group_by(Application.status)
        .all()
    )
    for status, count in rows:
        counts[status] = count
    return jsonify(counts), 200


@applications_bp.route("", methods=["GET"])
@jwt_required()
def list_applications():
    query = Application.query.filter_by(user_id=_current_user_id())

    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)

    search = request.args.get("search")
    if search:
        query = query.filter(Application.company.ilike(f"%{search}%"))

    apps = query.order_by(Application.created_at.desc()).all()
    return jsonify([a.to_dict() for a in apps]), 200


@applications_bp.route("", methods=["POST"])
@jwt_required()
def create_application():
    data = request.get_json(silent=True) or {}
    company = (data.get("company") or "").strip()
    role_title = (data.get("role_title") or "").strip()

    if not company:
        return jsonify({"error": "company is required"}), 400
    if not role_title:
        return jsonify({"error": "role_title is required"}), 400

    status = data.get("status", "applied")
    if status not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of {sorted(VALID_STATUSES)}"}), 400

    notes = data.get("notes")
    if notes and len(notes) > MAX_NOTES_LENGTH:
        return jsonify({"error": f"notes must be {MAX_NOTES_LENGTH} characters or fewer"}), 400

    date_applied = date.today()
    if data.get("date_applied"):
        try:
            date_applied = _parse_date(data["date_applied"])
        except ValueError:
            return jsonify({"error": "date_applied must be YYYY-MM-DD"}), 400

    application = Application(
        user_id=_current_user_id(),
        company=company,
        role_title=role_title,
        platform=data.get("platform"),
        status=status,
        date_applied=date_applied,
        job_url=data.get("job_url"),
        notes=notes,
    )
    db.session.add(application)
    db.session.commit()

    return jsonify(application.to_dict()), 201


@applications_bp.route("/<int:app_id>", methods=["GET"])
@jwt_required()
def get_application(app_id):
    application = _get_owned(app_id)
    if not application:
        return jsonify({"error": "Application not found"}), 404
    return jsonify(application.to_dict()), 200


@applications_bp.route("/<int:app_id>", methods=["PUT"])
@jwt_required()
def update_application(app_id):
    application = _get_owned(app_id)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    data = request.get_json(silent=True) or {}

    if "status" in data and data["status"] not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of {sorted(VALID_STATUSES)}"}), 400
    if "company" in data and not (data["company"] or "").strip():
        return jsonify({"error": "company cannot be empty"}), 400
    if "role_title" in data and not (data["role_title"] or "").strip():
        return jsonify({"error": "role_title cannot be empty"}), 400
    if "notes" in data and data["notes"] and len(data["notes"]) > MAX_NOTES_LENGTH:
        return jsonify({"error": f"notes must be {MAX_NOTES_LENGTH} characters or fewer"}), 400

    for field in ("company", "role_title", "platform", "status", "job_url", "notes"):
        if field in data:
            setattr(application, field, data[field])

    if "status" in data:
        application.sync_updated_at = None

    if "date_applied" in data and data["date_applied"]:
        try:
            application.date_applied = _parse_date(data["date_applied"])
        except ValueError:
            return jsonify({"error": "date_applied must be YYYY-MM-DD"}), 400

    db.session.commit()
    return jsonify(application.to_dict()), 200


@applications_bp.route("/<int:app_id>", methods=["DELETE"])
@jwt_required()
def delete_application(app_id):
    application = _get_owned(app_id)
    if not application:
        return jsonify({"error": "Application not found"}), 404

    db.session.delete(application)
    db.session.commit()
    return "", 204
