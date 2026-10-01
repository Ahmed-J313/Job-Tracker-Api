# Job Tracker API — Feature Scope

## Goal
A personal REST API to track job applications: log them, move them through statuses, and see what's pending. A ~3-hour resume project demonstrating backend fundamentals — auth, CRUD, testing, Docker.

## MVP features (v1 — the 3-hour build)
1. **User registration** — email + password, hashed storage. Duplicate emails rejected.
2. **Login** — returns a JWT access token.
3. **Create application** — company, role title, platform, date applied, job URL, notes. Status defaults to `applied`.
4. **List applications** — the authed user's own, newest first.
5. **Filter / search** — by `status`, by company substring.
6. **Update application** — edit any field, including status transitions (applied → interviewing → offer / rejected).
7. **Delete application.**
8. **Stats endpoint** — counts grouped by status.
9. **Auth isolation** — users can only see and touch their own applications (covered by tests).
10. **Input validation** — bad payloads return 400 with a clear message, never a 500.

## Non-goals (explicitly out of v1)
- No frontend / UI — API only, exercised via curl and tests.
- No email reminders or notifications.
- No resume parsing or autofill.
- No OAuth / social login — email + password only.
- SQLite only — no Postgres, no migrations.
- No pagination (fine at personal scale; add later if needed).

## 3-hour budget (rough)
- 45 min — project setup, models, auth routes
- 60 min — application CRUD + filters + stats
- 45 min — pytest suite (12–15 tests)
- 30 min — Dockerfile, README, final commits

## Done means
- `pytest` green, 12+ tests passing
- `docker compose up --build` works; README quickstart reproducible from scratch
- Commits in logical stages, not one dump
- README documents every endpoint with a curl example
