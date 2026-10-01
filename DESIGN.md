# Job Tracker API — Design

## Stack
| Layer | Choice | Why |
|---|---|---|
| Framework | Flask | You know it from Secret Santa; minimal boilerplate |
| ORM | Flask-SQLAlchemy | Simple models, no raw SQL |
| Auth | Flask-JWT-Extended | Standard JWT handling for Flask; Bearer tokens |
| Password hashing | Werkzeug (bundled with Flask) | No extra dependency |
| Database | SQLite | Zero setup; personal-scale data |
| Tests | pytest | Flask test client, fresh in-memory DB per test |
| Packaging | Docker + Compose | Matches the Docker story on your resume |

## Architecture
Single Flask app, app-factory pattern, two blueprints:

```
client (curl / pytest)
   │  JSON + Bearer JWT
   ▼
┌──────────────────┐
│    Flask app     │
│  ┌────────────┐  │
│  │ /api/auth  │──│─ register, login
│  ├────────────┤  │
│  │ /api/apps  │──│─ CRUD + filters + stats
│  └────────────┘  │
│   SQLAlchemy     │
└────────┬─────────┘
         ▼
       SQLite
```

## Data model

**User**
- `id` (PK), `email` (unique, indexed), `password_hash`, `created_at`

**Application**
- `id` (PK), `user_id` (FK → user.id, indexed)
- `company` (required), `role_title` (required)
- `platform` (e.g. "Ashby", "Dice", "Company site")
- `status`: `applied` | `interviewing` | `offer` | `rejected` (default `applied`)
- `date_applied` (default today), `job_url` (optional), `notes` (optional)
- `created_at`, `updated_at`

One user → many applications. Every application query is scoped by `user_id`.

## API contract

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | no | Create user → 201 |
| POST | `/api/auth/login` | no | Email + password → JWT |
| GET | `/api/applications` | yes | List mine, newest first; `?status=` `?search=` |
| POST | `/api/applications` | yes | Create → 201 |
| GET | `/api/applications/:id` | yes | Single application |
| PUT | `/api/applications/:id` | yes | Update any field |
| DELETE | `/api/applications/:id` | yes | Delete → 204 |
| GET | `/api/applications/stats` | yes | Counts grouped by status |

Error shape: `{ "error": "message" }` with proper codes — 400 validation, 401 auth, 404 not found.

Security note: accessing another user's application id returns **404, not 403** — don't leak which ids exist.

## Auth design
- **Register:** validate email format, minimum password length 8, hash with Werkzeug, reject duplicate email with 400.
- **Login:** verify hash, return a short-lived JWT access token (e.g. 1 day).
- **Protected routes:** `@jwt_required()`, current user taken from the token identity.
- **Isolation:** every application query filters by the current user's id — no exceptions.

## Testing strategy
- pytest with the Flask test client; fresh in-memory SQLite per test via fixtures.
- Fixtures: `app`, `client`, a registered user + token, a few seeded applications.
- 12–15 tests covering:
  - register / login happy path, duplicate registration, bad credentials
  - application CRUD happy paths
  - cross-user isolation (user B reads/updates/deletes user A's data → 404)
  - validation (missing company → 400)
  - filters (`status`, `search`) and stats counts

## Key decisions
1. **SQLite, no migrations** — personal tool, single developer; `db.create_all()` is enough. Tradeoff is documented, not hidden.
2. **Manual JSON validation, no Marshmallow** — one fewer dependency; small validation helpers instead.
3. **404 instead of 403 for other users' data** — avoids leaking which record ids exist.
4. **App factory + blueprints** — keeps `app/` and `tests/` organized and testable.
5. **No pagination in v1** — personal scale; listed as a follow-up, not forgotten.
