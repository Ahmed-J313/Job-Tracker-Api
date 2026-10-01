# Job Tracker API

[![Tests](https://github.com/Ahmed-J313/Job-Tracker-Api/actions/workflows/test.yml/badge.svg)](https://github.com/Ahmed-J313/Job-Tracker-Api/actions/workflows/test.yml)

I made this to keep track of my job applications. You log where you applied and it keeps the status of each one (applied, interviewing, offer, rejected) .

## Setup

You need Docker Desktop: https://www.docker.com/products/docker-desktop/

- `git clone https://github.com/Ahmed-J313/Job-Tracker-Api.git`
- `cd Job-Tracker-Api`

## How to use

Just run `python tracker.py` and follow the prompts. It starts the app for you if it's not already running, and the first time it'll walk you through making an account.

Then you get a menu:

- **Add a job I applied to**
- **See my applications**
- **Update a job's status**
- **See my stats**

Press `q` when you're done. That's really it, no curl or anything.

## Why is there a login if it's all on my computer?

Right now you don't need it. It's there so I can host this on a server later and have multiple people use it without seeing each other's stuff. The script handles the login for you so you only deal with it once.

## If you'd rather use curl

Create an account:

- `curl -X POST localhost:5000/api/auth/register -H 'Content-Type: application/json' -d '{"email":"you@example.com","password":"secret123"}'`

Log in and save the token:

- `TOKEN=$(curl -s -X POST localhost:5000/api/auth/login -H 'Content-Type: application/json' -d '{"email":"you@example.com","password":"secret123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")`

Add a job:

- `curl -X POST localhost:5000/api/applications -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"company":"Meow","role_title":"Software Engineer","platform":"Ashby"}'`

See everything:

- `curl localhost:5000/api/applications -H "Authorization: Bearer $TOKEN"`

Only show interviews:

- `curl "localhost:5000/api/applications?status=interviewing" -H "Authorization: Bearer $TOKEN"`

Update one (this moves app #1 to offer):

- `curl -X PUT localhost:5000/api/applications/1 -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"status":"offer"}'`

Stats:

- `curl localhost:5000/api/applications/stats -H "Authorization: Bearer $TOKEN"`

## Without Docker

Do this inside the project folder:

- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`
- `flask --app app run`

## Tests

- `pytest -v`

Tests cover login/register, adding and updating applications, making sure users can't see each other's stuff, bad input, filters, and stats.

## What's in here

Built with Flask, SQLAlchemy, JWT, SQLite, pytest, Docker.

- `tracker.py` - the menu script, easiest way to use this
- `app/` - the api code
- `tests/` - tests