# Job Tracker API

[![Tests](https://github.com/Ahmed-J313/Job-Tracker-Api/actions/workflows/test.yml/badge.svg)](https://github.com/Ahmed-J313/Job-Tracker-Api/actions/workflows/test.yml)

A personal tool for keeping track of job applications — add the jobs you've applied to, update their status as you hear back, and see where things stand. You can use it through a friendly menu or the API directly.

## Get started

- Install Docker Desktop: https://www.docker.com/products/docker-desktop/
- Clone this repo: `git clone https://github.com/Ahmed-J313/Job-Tracker-Api.git`
- `cd Job-Tracker-Api`

The helper script below starts the app for you. If you'd rather start it yourself, run `docker compose up --build`.

## Use it

- Run `python tracker.py`
- It checks whether the app is running, and offers to start it with Docker if not
- The first time, it'll offer to create an account for you
- Then you'll see a menu:
  - **Add a job I applied to** — enter the company and role, plus optional platform, job URL, and notes
  - **See my applications** — list everything, or just one status
  - **Update a job's status** — pick a job from the list and move it to a new status
  - **See my stats** — counts of how many jobs are in each status
  - Press `q` when done

No curl, no tokens, no JSON — just answer the prompts.

## Prefer typing commands?

- Register: `POST /api/auth/register` with `email` and `password`
- Log in: `POST /api/auth/login` with `email` and `password`, returns a token
- Add a job: `POST /api/applications` with `company`, `role_title`, and optional `platform`, `job_url`, `notes`
- See everything: `GET /api/applications`
- Filter by status: `GET /api/applications?status=...`
- Update one: `PUT /api/applications/:id` with a new `status`
- Stats: `GET /api/applications/stats`
- Valid statuses: `applied`, `interviewing`, `offer`, `rejected`

## Without Docker

- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`
- `flask --app app run` (run this from inside the project folder)

## Tests

- `pytest -v`
- Covers auth, CRUD, cross-user isolation, validation, filters, stats, and the `tracker.py` menu script

## What's inside

- Flask · SQLAlchemy · JWT auth · SQLite · pytest · Docker
- `tracker.py` — the friendly menu (start here)
- `app/` — the Flask API
- `tests/` — the pytest suite
