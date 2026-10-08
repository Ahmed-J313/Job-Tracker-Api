import os
import re
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel

CLAUDE_MODEL = "claude-haiku-4-5"

STATUS_KEYWORDS = {
    "rejected": [
        "unfortunately",
        "regret to inform",
        "will not be moving forward",
        "decided to move forward with other candidates",
        "not been selected",
        "pursuing other candidates",
    ],
    "offer": [
        "pleased to offer",
        "job offer",
        "offer letter",
        "excited to extend an offer",
        "extend an offer",
    ],
    "interviewing": [
        "schedule an interview",
        "interview invitation",
        "phone screen",
        "set up a call",
        "next steps in our process",
        "move forward to the interview",
        "technical interview",
    ],
}


@dataclass
class EmailResult:
    application_id: Optional[int]
    status: Optional[str]
    confident: bool
    reason: str


def _normalize(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def pattern_classify_status(text):
    text_lower = text.lower()
    matched = [status for status, keywords in STATUS_KEYWORDS.items() if any(kw in text_lower for kw in keywords)]
    if len(matched) == 1:
        return matched[0], True
    return None, False


def pattern_match_application(text, applications):
    text_norm = _normalize(text)
    matched = [a for a in applications if _normalize(a.company) and _normalize(a.company) in text_norm]
    if len(matched) == 1:
        return matched[0], True
    return None, False


class EmailAnalysis(BaseModel):
    is_job_related: bool
    application_id: Optional[int]
    application_match_confidence: Literal["high", "medium", "low"]
    status: Optional[Literal["applied", "interviewing", "offer", "rejected"]]
    status_confidence: Literal["high", "medium", "low"]
    reason: str


_client = None


def _get_client():
    # Built once and reused for the life of the worker process, not once
    # per email - a sync run can hit this dozens of times, and a fresh
    # Anthropic() (own connection pool) per call adds up fast on a 512MB
    # Render instance.
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    from anthropic import Anthropic

    _client = Anthropic(api_key=api_key)
    return _client


def llm_classify_and_match(subject, sender, snippet, applications):
    client = _get_client()
    if client is None:
        return None

    application_list = "\n".join(
        f"{a.id}: {a.company} - {a.role_title} - currently {a.status}" for a in applications
    ) or "(no applications on file)"

    prompt = f"""An email landed in a job seeker's inbox. Decide whether it relates to one of their in-progress job applications and, if so, what it signals about status.

Email:
From: {sender}
Subject: {subject}
Preview: {snippet}

Applications on file (id: company - role - current status):
{application_list}

Status changes only ever move forward: applied -> interviewing -> offer OR rejected. Never suggest moving an application backward, and never suggest a status change for an application that's already offer or rejected.

Respond with:
- is_job_related: true only if this is clearly about one of these applications or the person's job search
- application_id: the id of the matching application, or null if unclear or unrelated
- application_match_confidence: how confident you are in that match
- status: what this email signals about status, or null if it doesn't indicate one
- status_confidence: how confident you are in that status signal
- reason: one sentence explaining your reasoning"""

    try:
        response = client.messages.parse(
            model=CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
            output_format=EmailAnalysis,
        )
        return response.parsed_output
    except Exception as e:
        print(f"[email classifier] LLM call failed: {e}", flush=True)
        return None


def analyze_email(email, applications):
    text = f"{email['subject']} {email['snippet']}"

    status, status_confident = pattern_classify_status(text)
    application, match_confident = pattern_match_application(text, applications)

    if status_confident and match_confident:
        return EmailResult(application.id, status, True, "Matched by company name and status keywords.")

    analysis = llm_classify_and_match(email["subject"], email["sender"], email["snippet"], applications)
    if analysis is None:
        return EmailResult(None, None, False, "Pattern match was ambiguous and LLM classification is not configured.")

    if not match_confident:
        if analysis.is_job_related and analysis.application_match_confidence != "low" and analysis.application_id is not None:
            valid_ids = {a.id for a in applications}
            application = next((a for a in applications if a.id == analysis.application_id), None) if analysis.application_id in valid_ids else None
        else:
            application = None

    if not status_confident:
        status = analysis.status if analysis.status_confidence != "low" else None

    if application is None:
        if not analysis.is_job_related and analysis.application_match_confidence == "low":
            return EmailResult(None, None, True, "Not related to any application on file.")
        return EmailResult(None, None, False, analysis.reason)

    if status is None:
        return EmailResult(application.id, None, True, "Matched to an application, but no status change was signaled.")

    return EmailResult(application.id, status, True, analysis.reason)
