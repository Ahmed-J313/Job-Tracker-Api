def test_create_application(client, auth_headers):
    resp = client.post(
        "/api/applications",
        headers=auth_headers,
        json={"company": "Acme", "role_title": "Engineer"},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["company"] == "Acme"
    assert body["status"] == "applied"


def test_create_application_missing_company(client, auth_headers):
    resp = client.post(
        "/api/applications",
        headers=auth_headers,
        json={"role_title": "Engineer"},
    )
    assert resp.status_code == 400


def test_create_application_notes_too_long(client, auth_headers):
    resp = client.post(
        "/api/applications",
        headers=auth_headers,
        json={"company": "Acme", "role_title": "Engineer", "notes": "x" * 501},
    )
    assert resp.status_code == 400


def test_create_application_notes_at_limit(client, auth_headers):
    resp = client.post(
        "/api/applications",
        headers=auth_headers,
        json={"company": "Acme", "role_title": "Engineer", "notes": "x" * 500},
    )
    assert resp.status_code == 201


def test_create_application_requires_auth(client):
    resp = client.post(
        "/api/applications",
        json={"company": "Acme", "role_title": "Engineer"},
    )
    assert resp.status_code == 401


def test_list_applications_returns_only_own(client, auth_headers, seeded_applications):
    resp = client.get("/api/applications", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 3


def test_get_application(client, auth_headers, seeded_applications):
    resp = client.get(f"/api/applications/{seeded_applications[0]}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["company"] == "Acme"


def test_update_application_status(client, auth_headers, seeded_applications):
    app_id = seeded_applications[0]
    resp = client.put(
        f"/api/applications/{app_id}",
        headers=auth_headers,
        json={"status": "interviewing"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "interviewing"


def test_update_application_invalid_status(client, auth_headers, seeded_applications):
    resp = client.put(
        f"/api/applications/{seeded_applications[0]}",
        headers=auth_headers,
        json={"status": "ghosted"},
    )
    assert resp.status_code == 400


def test_update_application_notes_too_long(client, auth_headers, seeded_applications):
    resp = client.put(
        f"/api/applications/{seeded_applications[0]}",
        headers=auth_headers,
        json={"notes": "x" * 501},
    )
    assert resp.status_code == 400


def test_delete_application(client, auth_headers, seeded_applications):
    app_id = seeded_applications[0]
    resp = client.delete(f"/api/applications/{app_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = client.get(f"/api/applications/{app_id}", headers=auth_headers)
    assert resp.status_code == 404


def test_filter_by_status(client, auth_headers, seeded_applications):
    resp = client.get("/api/applications?status=interviewing", headers=auth_headers)
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["status"] == "interviewing"


def test_search_by_company(client, auth_headers, seeded_applications):
    resp = client.get("/api/applications?search=glob", headers=auth_headers)
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["company"] == "Globex"


def test_stats(client, auth_headers, seeded_applications):
    resp = client.get("/api/applications/stats", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["applied"] == 1
    assert data["interviewing"] == 1
    assert data["offer"] == 1
    assert data["rejected"] == 0


def test_isolation_get_other_users_application(client, other_auth_headers, seeded_applications):
    resp = client.get(f"/api/applications/{seeded_applications[0]}", headers=other_auth_headers)
    assert resp.status_code == 404


def test_isolation_update_other_users_application(client, other_auth_headers, seeded_applications):
    resp = client.put(
        f"/api/applications/{seeded_applications[0]}",
        headers=other_auth_headers,
        json={"status": "offer"},
    )
    assert resp.status_code == 404


def test_isolation_delete_other_users_application(client, other_auth_headers, seeded_applications):
    resp = client.delete(f"/api/applications/{seeded_applications[0]}", headers=other_auth_headers)
    assert resp.status_code == 404
