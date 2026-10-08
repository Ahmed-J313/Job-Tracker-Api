import base64
from html.parser import HTMLParser

import requests

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
BODY_TRUNCATE_LENGTH = 6000

# Broad on purpose - this just keeps obviously-irrelevant mail (newsletters,
# receipts, personal mail) away from the classifier entirely. Patterns and
# Haiku still do the real filtering on whatever matches here.
JOB_RELATED_TERMS = (
    "interview",
    "interviewing",
    "application",
    "applied",
    "offer",
    "recruiter",
    "recruiting",
    "hiring",
    "candidate",
    "position",
    "onsite",
    '"phone screen"',
    '"next steps"',
)
DEFAULT_SYNC_QUERY = "in:inbox newer_than:30d (" + " OR ".join(JOB_RELATED_TERMS) + ")"


class GmailReauthRequired(Exception):
    """Raised when Google rejects the refresh token itself (invalid_grant)."""


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self):
        return "".join(self._chunks)


def _html_to_text(html):
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def _decode_part_data(data):
    # Gmail returns base64url (RFC 4648 sec 5) and sometimes omits padding.
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def extract_body_text(payload):
    plain = None
    html = None

    def walk(part):
        nonlocal plain, html
        if part.get("filename"):
            return  # attachment, not body content

        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data")

        if data and mime_type == "text/plain" and plain is None:
            plain = _decode_part_data(data)
        elif data and mime_type == "text/html" and html is None:
            html = _decode_part_data(data)

        for sub_part in part.get("parts") or []:
            walk(sub_part)

    walk(payload)

    text = plain if plain is not None else _html_to_text(html) if html is not None else ""
    return text.strip()[:BODY_TRUNCATE_LENGTH]


def refresh_access_token(refresh_token, client_id, client_secret):
    resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    if resp.status_code == 400:
        try:
            error = resp.json().get("error")
        except ValueError:
            error = None
        if error == "invalid_grant":
            raise GmailReauthRequired("Refresh token is no longer valid")
    resp.raise_for_status()
    return resp.json()["access_token"]


def list_recent_message_ids(access_token, query=DEFAULT_SYNC_QUERY, max_results=50):
    resp = requests.get(
        f"{GMAIL_API_BASE}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, "maxResults": max_results},
        timeout=10,
    )
    resp.raise_for_status()
    return [m["id"] for m in resp.json().get("messages", [])]


def get_message_summary(access_token, message_id):
    resp = requests.get(
        f"{GMAIL_API_BASE}/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"format": "full"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    payload = data.get("payload", {})
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
    return {
        "id": message_id,
        "thread_id": data.get("threadId"),
        "subject": headers.get("Subject", ""),
        "sender": headers.get("From", ""),
        "snippet": data.get("snippet", ""),
        "body": extract_body_text(payload),
    }
