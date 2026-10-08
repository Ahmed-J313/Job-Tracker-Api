import requests

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailReauthRequired(Exception):
    """Raised when Google rejects the refresh token itself (invalid_grant)."""


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


def list_recent_message_ids(access_token, query="in:inbox newer_than:30d", max_results=50):
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
        params={"format": "metadata", "metadataHeaders": ["Subject", "From"]},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    return {
        "id": message_id,
        "subject": headers.get("Subject", ""),
        "sender": headers.get("From", ""),
        "snippet": data.get("snippet", ""),
    }
