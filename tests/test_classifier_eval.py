"""Labeled eval harness for the email classifier.

Unlike the rest of the test suite, this hits the real Anthropic API instead of
mocking it - it's a check on classification *accuracy* against real-ish mail,
not a check on the surrounding code logic. Skipped automatically if
ANTHROPIC_API_KEY isn't set, since it costs real money and isn't needed for
"does the code work."

Seeded with 5 anonymized examples covering the main buckets (rejection,
interview invite, platform noise, new-application confirmation, ambiguous
newsletter). Ahmed will add ~45 more pulled from his real inbox - just append
to EVAL_CASES, each one runs as its own pass/fail test case.
"""

import os

import pytest

from app.email_classifier import analyze_email

requires_anthropic_key = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="eval harness calls the real Anthropic API - set ANTHROPIC_API_KEY to run it",
)


class EvalApplication:
    def __init__(self, id, company, role_title, status):
        self.id = id
        self.company = company
        self.role_title = role_title
        self.status = status


EVAL_CASES = [
    {
        "name": "clear_rejection",
        "sender": "careers@lighthouseanalytics.com",
        "subject": "Your application to Lighthouse Analytics",
        "body": (
            "Thank you for taking the time to interview with us. After careful "
            "consideration, we've decided to move forward with other candidates "
            "for this role. We wish you the best in your search."
        ),
        "applications_on_file": [
            {"id": 1, "company": "Lighthouse Analytics", "role_title": "Data Analyst", "status": "interviewing"},
        ],
        "expected_kind": "update",
        "expected_application": 1,
        "expected_status": "rejected",
    },
    {
        "name": "interview_invite",
        "sender": "recruiting@bramblewoodretail.com",
        "subject": "Next steps for your application",
        "body": (
            "Hi, thanks for applying to the Supply Chain Coordinator role at "
            "Bramblewood Retail. We'd like to schedule a 30-minute technical "
            "interview with our team lead sometime next week. Let us know what "
            "times work for you."
        ),
        "applications_on_file": [
            {"id": 1, "company": "Bramblewood Retail", "role_title": "Supply Chain Coordinator", "status": "applied"},
        ],
        "expected_kind": "update",
        "expected_application": 1,
        "expected_status": "interviewing",
    },
    {
        "name": "platform_noise",
        "sender": "alerts@indeed.com",
        "subject": "5 new jobs match your search",
        "body": (
            "Here are some new job postings that match your recent searches on "
            "Indeed. Browse now to see roles hiring in your area."
        ),
        "applications_on_file": [],
        "expected_kind": "skip",
        "expected_application": None,
        "expected_status": None,
    },
    {
        "name": "new_application_confirmation",
        "sender": "no-reply@northfieldrobotics.com",
        "subject": "We've received your application to Northfield Robotics",
        "body": (
            "Thanks for applying to the Embedded Systems Engineer position at "
            "Northfield Robotics. Our team will review your application and "
            "reach out if there's a match."
        ),
        "applications_on_file": [
            {"id": 1, "company": "Some Other Company", "role_title": "Engineer", "status": "applied"},
        ],
        "expected_kind": "new_application",
        "expected_application": None,
        "expected_status": None,
    },
    {
        "name": "ambiguous_newsletter",
        "sender": "newsletter@careercompass.io",
        "subject": "5 tips to ace your next interview",
        "body": (
            "This week's newsletter covers how to prepare for behavioral "
            "interviews, salary negotiation tactics, and resume formatting "
            "tips. Read on for more career advice."
        ),
        "applications_on_file": [
            {"id": 1, "company": "Some Other Company", "role_title": "Engineer", "status": "applied"},
        ],
        "expected_kind": "review",
        "expected_application": None,
        "expected_status": None,
    },
]


def _actual_kind(result):
    if result.confident and result.application_id and result.status:
        return "update"
    if result.confident:
        return "skip"
    if result.suggested_company:
        return "new_application"
    return "review"


@requires_anthropic_key
@pytest.mark.parametrize("case", EVAL_CASES, ids=[c["name"] for c in EVAL_CASES])
def test_classifier_eval(case):
    email = {
        "subject": case["subject"],
        "sender": case["sender"],
        "snippet": case["body"][:200],
        "body": case["body"],
    }
    applications = [
        EvalApplication(a["id"], a["company"], a["role_title"], a["status"]) for a in case["applications_on_file"]
    ]

    result = analyze_email(email, applications)
    actual_kind = _actual_kind(result)

    assert actual_kind == case["expected_kind"], (
        f"expected kind={case['expected_kind']!r}, got {actual_kind!r} (reason: {result.reason!r})"
    )
    if case["expected_application"] is not None:
        assert result.application_id == case["expected_application"]
    if case["expected_status"] is not None:
        assert result.status == case["expected_status"]
