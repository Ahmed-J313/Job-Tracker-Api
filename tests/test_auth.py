def test_register_happy_path(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "new@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert resp.status_code == 201
    assert resp.get_json()["email"] == "new@example.com"


def test_register_password_mismatch(client):
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "new@example.com",
            "password": "password123",
            "confirm_password": "password456",
        },
    )
    assert resp.status_code == 400


def test_register_duplicate_email(client, user):
    resp = client.post(
        "/api/auth/register",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert resp.status_code == 400


def test_register_short_password(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )
    assert resp.status_code == 400


def test_register_invalid_email(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "password123"},
    )
    assert resp.status_code == 400


def test_login_happy_path(client, user):
    resp = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "password123"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.get_json()


def test_login_wrong_password(client, user):
    resp = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "nope@example.com", "password": "password123"},
    )
    assert resp.status_code == 401
