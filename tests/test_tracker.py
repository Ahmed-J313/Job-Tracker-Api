import io
import urllib.error
from unittest.mock import MagicMock, call, patch

import tracker


# --- api() ---

def test_api_success_returns_status_and_dict():
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"key": "value"}'

    with patch("tracker.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        status, data = tracker.api("GET", "/api/applications")

    assert status == 200
    assert data == {"key": "value"}


def test_api_http_error_with_json_body_returns_parsed_dict():
    error = urllib.error.HTTPError(
        url="http://localhost:5000/api/applications",
        code=400,
        msg="Bad Request",
        hdrs=None,
        fp=io.BytesIO(b'{"error": "company is required"}'),
    )

    with patch("tracker.urllib.request.urlopen", side_effect=error):
        status, data = tracker.api("POST", "/api/applications", json_body={})

    assert status == 400
    assert data == {"error": "company is required"}


def test_api_http_error_with_non_json_body_does_not_crash():
    error = urllib.error.HTTPError(
        url="http://localhost:5000/api/applications",
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=io.BytesIO(b"not json"),
    )

    with patch("tracker.urllib.request.urlopen", side_effect=error):
        status, data = tracker.api("GET", "/api/applications")

    assert status == 500
    assert "error" in data


# --- api_is_up() ---

def test_api_is_up_true_on_normal_response():
    with patch("tracker.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = MagicMock(status=200)
        assert tracker.api_is_up() is True


def test_api_is_up_true_on_http_error():
    error = urllib.error.HTTPError(url="http://localhost:5000", code=404, msg="Not Found", hdrs=None, fp=io.BytesIO(b""))
    with patch("tracker.urllib.request.urlopen", side_effect=error):
        assert tracker.api_is_up() is True


def test_api_is_up_false_on_connection_refused():
    with patch("tracker.urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        assert tracker.api_is_up() is False


# --- ask() ---

def test_ask_required_field_reprompts_until_entered():
    with patch("builtins.input", side_effect=["", "  ", "Acme"]):
        assert tracker.ask("Company: ") == "Acme"


def test_ask_optional_field_returns_empty_immediately():
    with patch("builtins.input", side_effect=[""]) as mock_input:
        assert tracker.ask("Platform (optional): ", required=False) == ""
    assert mock_input.call_count == 1


# --- log_application() ---

def test_log_application_drops_empty_optional_fields():
    with patch("builtins.input", side_effect=["Acme", "Engineer", "", "", ""]), \
         patch("tracker.api", return_value=(201, {"company": "Acme", "role_title": "Engineer"})) as mock_api:
        tracker.log_application("tok")

    mock_api.assert_called_once_with(
        "POST", "/api/applications", token="tok",
        json_body={"company": "Acme", "role_title": "Engineer"},
    )


def test_log_application_sends_optional_fields_when_provided():
    with patch("builtins.input", side_effect=["Acme", "Engineer", "Ashby", "http://x", "note"]), \
         patch("tracker.api", return_value=(201, {"company": "Acme", "role_title": "Engineer"})) as mock_api:
        tracker.log_application("tok")

    _, kwargs = mock_api.call_args
    assert kwargs["json_body"] == {
        "company": "Acme",
        "role_title": "Engineer",
        "platform": "Ashby",
        "job_url": "http://x",
        "notes": "note",
    }


def test_log_application_prints_confirmation_with_company_name(capsys):
    with patch("builtins.input", side_effect=["Acme", "Engineer", "", "", ""]), \
         patch("tracker.api", return_value=(201, {"company": "Acme", "role_title": "Engineer"})):
        tracker.log_application("tok")

    assert "Acme" in capsys.readouterr().out


# --- update_status() ---

APPS = [
    {"id": 1, "company": "Acme", "role_title": "Engineer", "status": "applied"},
    {"id": 2, "company": "Globex", "role_title": "SRE", "status": "interviewing"},
]


def test_update_status_out_of_range_number_makes_no_put():
    with patch("builtins.input", side_effect=["5"]), \
         patch("tracker.api", return_value=(200, APPS)) as mock_api:
        tracker.update_status("tok")

    assert mock_api.call_count == 1


def test_update_status_invalid_status_makes_no_put():
    with patch("builtins.input", side_effect=["1", "ghosted"]), \
         patch("tracker.api", return_value=(200, APPS)) as mock_api:
        tracker.update_status("tok")

    assert mock_api.call_count == 1


def test_update_status_valid_choice_sends_one_put():
    with patch("builtins.input", side_effect=["2", "offer"]), \
         patch("tracker.api", side_effect=[(200, APPS), (200, {"status": "offer"})]) as mock_api:
        tracker.update_status("tok")

    assert mock_api.call_count == 2
    assert mock_api.call_args_list[1] == call(
        "PUT", "/api/applications/2", token="tok", json_body={"status": "offer"}
    )


# --- login() ---

def test_login_success_does_not_register():
    with patch("builtins.input", return_value="alice@example.com"), \
         patch("tracker.getpass.getpass", return_value="password123"), \
         patch("tracker.api", return_value=(200, {"access_token": "tok123"})) as mock_api:
        token = tracker.login()

    assert token == "tok123"
    mock_api.assert_called_once_with(
        "POST", "/api/auth/login",
        json_body={"email": "alice@example.com", "password": "password123"},
    )


def test_login_401_then_yes_registers_then_logs_in():
    with patch("builtins.input", side_effect=["alice@example.com", "y"]), \
         patch("tracker.getpass.getpass", return_value="password123"), \
         patch("tracker.api", side_effect=[
             (401, {"error": "invalid"}),
             (201, {"id": 1, "email": "alice@example.com"}),
             (200, {"access_token": "tok456"}),
         ]) as mock_api:
        token = tracker.login()

    assert token == "tok456"
    assert mock_api.call_count == 3


def test_login_401_then_no_exits_cleanly():
    with patch("builtins.input", side_effect=["alice@example.com", "n"]), \
         patch("tracker.getpass.getpass", return_value="password123"), \
         patch("tracker.api", return_value=(401, {"error": "invalid"})) as mock_api:
        token = tracker.login()

    assert token is None
    assert mock_api.call_count == 1
