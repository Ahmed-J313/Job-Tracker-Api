from unittest.mock import MagicMock, patch

from app.gmail_client import DEFAULT_SYNC_QUERY, list_recent_message_ids


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
