from unittest.mock import MagicMock, patch

from app.email_classifier import (
    EmailAnalysis,
    analyze_email,
    llm_classify_and_match,
    pattern_classify_status,
    pattern_match_application,
)


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


# ---------- analyze_email ----------


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
        reason="mentions interview",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.confident is True
    assert result.application_id == 1
    assert result.status == "interviewing"


def test_analyze_email_llm_unconfident_goes_to_review():
    email = {"subject": "re: update", "sender": "x@y.com", "snippet": "hmm"}
    apps = [FakeApplication(1, "Acme Corp", status="applied")]
    fake_analysis = EmailAnalysis(
        is_job_related=True,
        application_id=1,
        application_match_confidence="low",
        status=None,
        status_confidence="low",
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
        reason="unrelated receipt",
    )
    with patch("app.email_classifier.llm_classify_and_match", return_value=fake_analysis):
        result = analyze_email(email, apps)
    assert result.confident is True
    assert result.application_id is None
    assert result.status is None


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
