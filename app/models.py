from datetime import date, datetime

from app import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    google_sub = db.Column(db.String(255), unique=True, nullable=True, index=True)
    gmail_refresh_token_enc = db.Column(db.Text, nullable=True)
    gmail_connected = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    applications = db.relationship(
        "Application", backref="user", lazy=True, cascade="all, delete-orphan"
    )


class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ProcessedEmail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    gmail_message_id = db.Column(db.String(64), nullable=False)
    processed_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "gmail_message_id", name="uq_processed_email_user_message"),
    )


class EmailReviewItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    gmail_message_id = db.Column(db.String(64), nullable=False)
    subject = db.Column(db.String(998))
    snippet = db.Column(db.Text)
    sender = db.Column(db.String(255))
    reason = db.Column(db.Text, nullable=False)
    resolution = db.Column(db.String(16))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "gmail_message_id": self.gmail_message_id,
            "subject": self.subject,
            "snippet": self.snippet,
            "sender": self.sender,
            "reason": self.reason,
            "resolution": self.resolution,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False, index=True
    )
    company = db.Column(db.String(255), nullable=False)
    role_title = db.Column(db.String(255), nullable=False)
    platform = db.Column(db.String(255))
    status = db.Column(db.String(32), nullable=False, default="applied")
    date_applied = db.Column(db.Date, default=date.today)
    job_url = db.Column(db.String(1024))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "company": self.company,
            "role_title": self.role_title,
            "platform": self.platform,
            "status": self.status,
            "date_applied": self.date_applied.isoformat() if self.date_applied else None,
            "job_url": self.job_url,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
