# Prospect

[![Tests](https://github.com/Ahmed-J313/Job-Tracker-Api/actions/workflows/test.yml/badge.svg)](https://github.com/Ahmed-J313/Job-Tracker-Api/actions/workflows/test.yml)

**Live site: https://job-tracker-api-5m1v.onrender.com/**

I made this to keep track of my job applications. Log where you applied and it keeps the status of each one (applied, interviewing, offer, rejected).

## How to use it

Go to the link above, make an account, start adding applications. Dashboard gives you the stats at a glance, Applications tab is where you add/edit stuff and move the status by clicking the pill. Forgot your password, there's a link for that on the sign in page.

## Running it yourself

If you'd rather run it locally instead of using the hosted site:

1. Install Docker Desktop
2. `git clone https://github.com/Ahmed-J313/Job-Tracker-Api.git` and `cd` into it
3. `docker compose up --build -d`
4. Open `http://localhost:5000`

`docker compose down` when you're done, your data's still there next time you bring it back up.

There's also `tracker.py`, a CLI menu if you don't feel like using the browser. Run `python tracker.py` while the local server's up and it'll walk you through making an account.

Without Docker: make a venv, `pip install -r requirements.txt`, set `DATABASE_URL` and `JWT_SECRET_KEY` env vars, then `flask --app app run`. Docker sets those two for you automatically, which is why it's the easier path.

## Tests

`pytest -v`

## Built with

Flask, SQLAlchemy, Postgres (Neon), JWT auth, rate limiting, gunicorn, hosted on Render.
