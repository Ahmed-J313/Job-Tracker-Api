# Job Tracker API

A personal REST API for tracking job applications — log them, move them through statuses, and see what's pending at a glance. Built with Flask, JWT auth, SQLAlchemy, pytest, and Docker.

## Tech stack
Flask · Flask-SQLAlchemy · Flask-JWT-Extended · SQLite · pytest · Docker

## Quickstart

**Local:**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
flask --app app run
```

**Docker:**
```bash
docker compose up --build
```
API at `http://localhost:5000`.

## API examples

Register and log in:
```bash
curl -X POST localhost:5000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"secret123"}'

TOKEN=$(curl -s -X POST localhost:5000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","password":"secret123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Log an application:
```bash
curl -X POST localhost:5000/api/applications \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"company":"Meow","role_title":"Software Engineer","platform":"Ashby","job_url":"https://jobs.ashbyhq.com/meow/..."}'
```

List everything in interviewing:
```bash
curl "localhost:5000/api/applications?status=interviewing" \
  -H "Authorization: Bearer $TOKEN"
```

Move one to offer:
```bash
curl -X PUT localhost:5000/api/applications/1 \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"status":"offer"}'
```

Stats:
```bash
curl localhost:5000/api/applications/stats \
  -H "Authorization: Bearer $TOKEN"
```

## Running tests
```bash
pytest -v
```
12–15 tests: auth flows, CRUD, cross-user isolation, validation, filters, stats.

## Project structure
```
job-tracker-api/
├── app/
│   ├── __init__.py        # app factory, blueprint registration
│   ├── models.py          # User, Application
│   ├── auth.py            # /api/auth routes
│   └── applications.py    # /api/applications routes
├── tests/
│   ├── conftest.py        # fixtures: app, client, user, token
│   ├── test_auth.py
│   └── test_applications.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── SCOPE.md
└── DESIGN.md
```

## Status
v1 MVP — API only, no frontend. See `SCOPE.md` for what's in and what's deliberately out.
