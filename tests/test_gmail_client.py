import base64
from unittest.mock import MagicMock, patch

from app.gmail_client import DEFAULT_SYNC_QUERY, extract_body_text, get_message_summary, list_recent_message_ids


def _b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_list_recent_message_ids_uses_job_related_prefilter_by_default():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"messages": []}
    mock_resp.raise_for_status.return_value = None
    with patch("app.gmail_client.requests.get", return_value=mock_resp) as mock_get:
        list_recent_message_ids("fake-token")

    sent_params = mock_get.call_args.kwargs["params"]
    assert sent_params["q"] == DEFAULT_SYNC_QUERY
    for term in ("interview", "application", "offer", "recruiter"):
        assert term in sent_params["q"]


def test_list_recent_message_ids_can_override_query():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"messages": [{"id": "m1"}]}
    mock_resp.raise_for_status.return_value = None
    with patch("app.gmail_client.requests.get", return_value=mock_resp) as mock_get:
        ids = list_recent_message_ids("fake-token", query="custom query")

    assert ids == ["m1"]
    assert mock_get.call_args.kwargs["params"]["q"] == "custom query"


# ---------- extract_body_text ----------


def test_extract_body_text_prefers_plain_part():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64("Hello plain text")}},
            {"mimeType": "text/html", "body": {"data": _b64("<p>Hello <b>html</b></p>")}},
        ],
    }
    assert extract_body_text(payload) == "Hello plain text"


def test_extract_body_text_falls_back_to_html_stripped():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>Hello <b>html</b> world</p>")}},
        ],
    }
    assert extract_body_text(payload) == "Hello html world"


def test_extract_body_text_skips_attachments():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "text/plain",
                "filename": "resume.txt",
                "body": {"data": _b64("this is an attachment, not the body")},
            },
            {"mimeType": "text/plain", "body": {"data": _b64("the real body text")}},
        ],
    }
    assert extract_body_text(payload) == "the real body text"


def test_extract_body_text_handles_non_multipart():
    payload = {"mimeType": "text/plain", "body": {"data": _b64("just a simple body")}}
    assert extract_body_text(payload) == "just a simple body"


def test_extract_body_text_handles_nested_multipart():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64("nested plain text")}},
                ],
            },
        ],
    }
    assert extract_body_text(payload) == "nested plain text"


def test_extract_body_text_truncates_long_body():
    long_text = "x" * 7000
    payload = {"mimeType": "text/plain", "body": {"data": _b64(long_text)}}
    result = extract_body_text(payload)
    assert len(result) == 6000


def test_extract_body_text_no_content_returns_empty_string():
    payload = {"mimeType": "multipart/mixed", "parts": []}
    assert extract_body_text(payload) == ""


# ---------- get_message_summary ----------


def test_get_message_summary_uses_full_format():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "threadId": "thread-123",
        "snippet": "hi there",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Hello"},
                {"name": "From", "value": "a@b.com"},
            ],
            "mimeType": "text/plain",
            "body": {"data": _b64("the body content")},
        },
    }
    mock_resp.raise_for_status.return_value = None
    with patch("app.gmail_client.requests.get", return_value=mock_resp) as mock_get:
        result = get_message_summary("fake-token", "msg1")

    assert mock_get.call_args.kwargs["params"] == {"format": "full"}
    assert result["id"] == "msg1"
    assert result["thread_id"] == "thread-123"
    assert result["subject"] == "Hello"
    assert result["sender"] == "a@b.com"
    assert result["snippet"] == "hi there"
    assert result["body"] == "the body content"
