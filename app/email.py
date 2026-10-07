import json
import os
import urllib.error
import urllib.request

RESEND_URL = "https://api.resend.com/emails"


def send_email(to_email, subject, html_body):
    api_key = os.environ.get("RESEND_API_KEY")

    if not api_key:
        # Gunicorn workers have no tty, so stdout is block-buffered by default -
        # without flush=True this can sit invisible in the log for a long time.
        print(f"[dev email] To: {to_email} | Subject: {subject}\n{html_body}", flush=True)
        return

    payload = json.dumps(
        {
            "from": "Prospect <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        RESEND_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Cloudflare (in front of api.resend.com) blocks urllib's default
            # "Python-urllib/x.y" user agent as bot traffic (error code 1010).
            "User-Agent": "job-tracker-api/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        # Resend puts the actual reason (bad key, unverified recipient, etc.)
        # in the response body - the bare exception alone doesn't show it.
        body = e.read().decode("utf-8", errors="replace")
        print(f"[email send failed] {to_email}: HTTP {e.code}: {body}", flush=True)
    except urllib.error.URLError as e:
        # An email provider outage shouldn't break the password reset flow itself.
        print(f"[email send failed] {to_email}: {e}", flush=True)
