from unittest.mock import MagicMock, patch

import pytest

import app.email_classifier as email_classifier
from app.email_classifier import (
    EmailAnalysis,
    analyze_email,
    is_platform_sender,
    llm_classify_and_match,
    pattern_classify_status,
    pattern_match_application,
)


@pytest.fixture(autouse=True)
def reset_cached_client():
    # llm_classify_and_match now caches the Anthropic client at module level
    # (reused across calls in production) - reset it so each test's patch
    # of anthropic.Anthropic actually takes effect instead of reusing
    # whatever a previous test cached.
    email_classifier._client = None
    yield
    email_classifier._client = None


class FakeApplication:
    def __init__(self, id, company, role_title="Engineer", status="applied"):
        self.id = id
        self.company = company
        self.role_title = role_title
        self.status = status


# ---------- pattern_classify_status ----------


def test_pattern_classify_status_single_match():
    status, confident = pattern_classify_status(
        "We regret to inform you that unfortunately we will not be moving forward."
    )
    assert status == "rejected"
    assert confident is True


def test_pattern_classify_status_no_match():
    status, confident = pattern_classify_status("Just checking in, nothing special here.")
    assert status is None
    assert confident is False


def test_pattern_classify_status_conflicting_signals():
    text = "Unfortunately we'd like to schedule an interview with you."
    status, confident = pattern_classify_status(text)
    assert confident is False


# ---------- pattern_match_application ----------


def test_pattern_match_application_single():
    apps = [FakeApplication(1, "Acme Corp"), FakeApplication(2, "Globex")]
    app, confident = pattern_match_application("Update on your Acme Corp application", apps)
    assert confident is True
    assert app.id == 1


def test_pattern_match_application_none():
    apps = [FakeApplication(1, "Acme Corp")]
    app, confident = pattern_match_application("Your weekly newsletter digest", apps)
    assert app is None
    assert confident is False


def test_pattern_match_application_multiple():
    apps = [FakeApplication(1, "Acme"), FakeApplication(2, "Globex")]
    app, confident = pattern_match_application("Update from Acme regarding your Globex interview", apps)
    assert app is None
    assert confident is False


# ---------- is_platform_sender ----------


def test_is_platform_sender_bare_address():
    assert is_platform_sender("no-reply@dice.com") is True


def test_is_platform_sender_name_and_address():
    assert is_platform_sender("Dice <no-reply@dice.com>") is True


def test_is_platform_sender_subdomain():
    assert is_platform_sender("alerts@connect.dice.com") is True


def test_is_platform_sender_ats_domain_not_platform():
    assert is_platform_sender("Acme Corp <no-reply@greenhouse.io>") is False


def test_is_platform_sender_direct_employer():
    assert is_platform_sender("hr@acme.com") is False


def test_is_platform_sender_missing_address():
    assert is_platform_sender("not an email address") is False


# ---------- analyze_email ----------


def test_analyze_email_platform_sender_skips_without_llm_call():
    email = {
        "subject": "Verify your Dice account",
        "sender": "Dice <no-reply@dice.com>",
        "snippet": "Please verify your candidate email.",
    }
    with patch("app.email_classifier.llm_classify_and_match") as mock_llm:
        result = analyze_email(email, [])
    mock_llm.assert_not_called()
    assert result.confident is True
    assert result.application_id is None
    assert result.status is None


def test_analyze_email_interview_invite_from_untracked_employer_suggests_creation():
    email = {
        "subject": "Elevate New York - Info Session Confirmation",
        "sender": "events@elevateny.org",
        "snippet": "You're registered for our upcoming info session.",
    }
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    fake_analysis = EmailAnalysis(
        is_job_related=True,
        application_id=None,
        application_match_confidence="low",
        status=None,
        status_confidence="low",
        suggest_new_application=True,
        suggested_company="Elevate New York",
        suggested_role=None,
        reason="employer-hosted info session the person registered for, not on file",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.confident is False
    assert result.application_id is None
    assert result.suggested_company == "Elevate New York"
    assert result.suggested_role == "Unknown"


def test_analyze_email_confident_pattern_match_skips_llm():
    email = {
        "subject": "Acme Corp - Interview",
        "sender": "hr@acme.com",
        "snippet": "We'd like to schedule an interview with you.",
    }
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    with patch("app.email_classifier.llm_classify_and_match") as mock_llm:
        result = analyze_email(email, apps)
    mock_llm.assert_not_called()
    assert result.confident is True
    assert result.application_id == 1
    assert result.status == "interviewing"


def test_analyze_email_escalates_to_llm_when_ambiguous():
    email = {"subject": "Following up", "sender": "someone@example.com", "snippet": "just checking in"}
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    fake_analysis = EmailAnalysis(
        is_job_related=True,
        application_id=1,
        application_match_confidence="high",
        status="interviewing",
        status_confidence="high",
        suggest_new_application=False,
        suggested_company=None,
        suggested_role=None,
        reason="mentions interview",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.confident is True
    assert result.application_id == 1
    assert result.status == "interviewing"


def test_analyze_email_confident_match_no_status_change_is_skipped_not_reviewed():
    email = {"subject": "Re: your application", "sender": "hr@acme.com", "snippet": "We received your application."}
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    fake_analysis = EmailAnalysis(
        is_job_related=True,
        application_id=1,
        application_match_confidence="high",
        status=None,
        status_confidence="low",
        suggest_new_application=False,
        suggested_company=None,
        suggested_role=None,
        reason="confirms receipt, no status signal",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.confident is True
    assert result.application_id == 1
    assert result.status is None


def test_analyze_email_llm_unconfident_goes_to_review():
    email = {"subject": "re: update", "sender": "x@y.com", "snippet": "hmm"}
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    fake_analysis = EmailAnalysis(
        is_job_related=True,
        application_id=1,
        application_match_confidence="low",
        status=None,
        status_confidence="low",
        suggest_new_application=False,
        suggested_company=None,
        suggested_role=None,
        reason="not sure",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.confident is False


def test_analyze_email_llm_confidently_unrelated_skips_silently():
    email = {"subject": "Your Amazon order", "sender": "no-reply@amazon.com", "snippet": "shipped"}
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    fake_analysis = EmailAnalysis(
        is_job_related=False,
        application_id=None,
        application_match_confidence="low",
        status=None,
        status_confidence="low",
        suggest_new_application=False,
        suggested_company=None,
        suggested_role=None,
        reason="unrelated receipt",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.confident is True
    assert result.application_id is None
    assert result.status is None


def test_analyze_email_new_application_confirmation_suggests_creation():
    email = {"subject": "Thanks for applying to Stripe!", "sender": "no-reply@stripe.com", "snippet": "received"}
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    fake_analysis = EmailAnalysis(
        is_job_related=True,
        application_id=None,
        application_match_confidence="low",
        status="applied",
        status_confidence="high",
        suggest_new_application=True,
        suggested_company="Stripe",
        suggested_role="Software Engineer, New Grad",
        reason="confirms a new application to Stripe, not on file",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.confident is False
    assert result.application_id is None
    assert result.suggested_company == "Stripe"
    assert result.suggested_role == "Software Engineer, New Grad"


def test_analyze_email_new_application_confirmation_defaults_unknown_role():
    email = {"subject": "We received your application", "sender": "no-reply@noom.com", "snippet": "received"}
    apps = []
    fake_analysis = EmailAnalysis(
        is_job_related=True,
        application_id=None,
        application_match_confidence="low",
        status="applied",
        status_confidence="high",
        suggest_new_application=True,
        suggested_company="Noom",
        suggested_role=None,
        reason="confirms a new application to Noom, role not stated",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.suggested_company == "Noom"
    assert result.suggested_role == "Unknown"


def test_analyze_email_no_llm_configured_goes_to_review():
    email = {"subject": "re: update", "sender": "x@y.com", "snippet": "hmm"}
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    with patch("app.email_classifier.llm_classify_and_match", return_value=None):
        result = analyze_email(email, apps)
    assert result.confident is False


def test_analyze_email_rejects_hallucinated_application_id():
    email = {"subject": "re: update", "sender": "x@y.com", "snippet": "hmm"}
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    fake_analysis = EmailAnalysis(
        is_job_related=True,
        application_id=999,  # not in the applications list
        application_match_confidence="high",
        status="interviewing",
        status_confidence="high",
        suggest_new_application=False,
        suggested_company=None,
        suggested_role=None,
        reason="hallucinated",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.confident is False


# ---------- llm_classify_and_match ----------


def test_llm_classify_and_match_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = llm_classify_and_match("subj", "sender", "snippet", [])
    assert result is None


def test_llm_classify_and_match_calls_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake_parsed = EmailAnalysis(
        is_job_related=True,
        application_id=None,
        application_match_confidence="low",
        status=None,
        status_confidence="low",
        suggest_new_application=False,
        suggested_company=None,
        suggested_role=None,
        reason="x",
    )
    mock_response = MagicMock(parsed_output=fake_parsed)
    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.parse.return_value = mock_response
        result = llm_classify_and_match("subj", "sender", "snippet", [])
    assert result == fake_parsed


def test_llm_classify_and_match_returns_none_on_api_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.parse.side_effect = Exception("boom")
        result = llm_classify_and_match("subj", "sender", "snippet", [])
    assert result is None
