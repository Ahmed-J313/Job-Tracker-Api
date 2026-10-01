import getpass
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

BASE_URL = "http://localhost:5000"
VALID_STATUSES = ["applied", "interviewing", "offer", "rejected"]


def api(method, path, token=None, json_body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(json_body).encode("utf-8") if json_body is not None else None
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, {"error": body or str(e)}
    except urllib.error.URLError as e:
        return 0, {"error": f"Could not reach the server: {e.reason}"}


def api_is_up():
    try:
        urllib.request.urlopen(BASE_URL, timeout=2)
        return True
    except urllib.error.HTTPError:
        return True
    except urllib.error.URLError:
        return False


def ensure_app_running():
    if api_is_up():
        return True

    answer = input("The app doesn't seem to be running. Start it now with Docker? (y/n): ").strip().lower()
    if answer != "y":
        print("Okay — start it yourself with: docker compose up --build")
        return False

    if not os.path.exists("docker-compose.yml"):
        print("Couldn't find docker-compose.yml here — make sure you're running this from inside the project folder.")
        return False

    try:
        result = subprocess.run(["docker", "compose", "up", "--build", "-d"], capture_output=True, text=True)
    except FileNotFoundError:
        print("Couldn't run Docker. Make sure Docker Desktop is installed and running.")
        return False

    if result.returncode != 0:
        print("Docker couldn't start the app:")
        print(result.stderr.strip() or result.stdout.strip())
        print("Usual causes: Docker Desktop isn't running, or you're not inside the project folder.")
        return False

    print("Starting the app, this can take a minute the first time...")
    for _ in range(30):
        if api_is_up():
            return True
        time.sleep(2)

    print("The app still isn't responding after starting Docker. Check `docker compose logs` for details.")
    return False


def ask(prompt, required=True, hidden=False):
    while True:
        value = getpass.getpass(prompt) if hidden else input(prompt)
        value = value.strip()
        if value or not required:
            return value
        print("This is required — please enter a value.")


def login():
    print("Let's get you logged in.")
    email = ask("Email: ")
    password = ask("Password: ", hidden=True)

    status, data = api("POST", "/api/auth/login", json_body={"email": email, "password": password})
    if status == 200:
        return data.get("access_token")

    if status == 401:
        answer = input("No account with that login. Create one? (y/n): ").strip().lower()
        if answer != "y":
            print("Okay, come back once you have an account.")
            return None

        reg_status, reg_data = api("POST", "/api/auth/register", json_body={"email": email, "password": password})
        if reg_status != 201:
            print(f"Couldn't create that account: {reg_data.get('error', 'something went wrong')}")
            return None

        login_status, login_data = api("POST", "/api/auth/login", json_body={"email": email, "password": password})
        if login_status == 200:
            return login_data.get("access_token")
        print("Something went wrong logging in after creating the account.")
        return None

    print(f"Couldn't log in: {data.get('error', 'something went wrong')}")
    return None


def list_applications(token, status_filter=None):
    path = "/api/applications"
    if status_filter:
        path += f"?status={status_filter}"

    status, data = api("GET", path, token=token)
    if status != 200:
        print(f"Couldn't load your applications: {data.get('error', 'something went wrong')}")
        return []

    apps = data.get("applications") if isinstance(data, dict) else data
    return apps if isinstance(apps, list) else []


def print_applications(apps):
    if not apps:
        print("No applications found.")
        return
    for i, a in enumerate(apps, start=1):
        print(f"{i}. {a.get('company')} -- {a.get('role_title')} [{a.get('status')}]")


def log_application(token):
    company = ask("Company: ")
    role_title = ask("Role title: ")
    platform = ask("Platform (optional): ", required=False)
    job_url = ask("Job URL (optional): ", required=False)
    notes = ask("Notes (optional): ", required=False)

    payload = {"company": company, "role_title": role_title}
    if platform:
        payload["platform"] = platform
    if job_url:
        payload["job_url"] = job_url
    if notes:
        payload["notes"] = notes

    status, data = api("POST", "/api/applications", token=token, json_body=payload)
    if status == 201:
        print(f"Saved: {data['company']} -- {data['role_title']} (applied)")
    else:
        print(f"Couldn't save that: {data.get('error', 'something went wrong')}")


def see_applications(token):
    status_filter = ask(
        "Filter by status (applied/interviewing/offer/rejected, Enter for all): ", required=False
    )
    apps = list_applications(token, status_filter or None)
    print_applications(apps)


def update_status(token):
    apps = list_applications(token)
    print_applications(apps)
    if not apps:
        return

    choice = input("Which number do you want to update? ").strip()
    try:
        index = int(choice) - 1
    except ValueError:
        index = -1

    if index < 0 or index >= len(apps):
        print("That's not a valid number from the list.")
        return

    print("Valid statuses: " + ", ".join(VALID_STATUSES))
    new_status = input("New status: ").strip().lower()
    if new_status not in VALID_STATUSES:
        print("That's not a valid status.")
        return

    app_id = apps[index]["id"]
    status, data = api("PUT", f"/api/applications/{app_id}", token=token, json_body={"status": new_status})
    if status == 200:
        print(f"Updated to {new_status}.")
    else:
        print(f"Couldn't update that: {data.get('error', 'something went wrong')}")


def see_stats(token):
    status, data = api("GET", "/api/applications/stats", token=token)
    if status != 200:
        print(f"Couldn't load your stats: {data.get('error', 'something went wrong')}")
        return

    total = 0
    for key, value in data.items():
        print(f"{key}: {value}")
        total += value
    print(f"Total: {total}")


def main():
    print("=== Job Tracker ===")
    if not ensure_app_running():
        return

    token = login()
    if not token:
        return

    while True:
        print("\nWhat next?")
        print("  1. Add a job I applied to")
        print("  2. See my applications")
        print("  3. Update a job's status")
        print("  4. See my stats")
        print("  q. Done")

        choice = input("> ").strip().lower()
        if choice == "1":
            log_application(token)
        elif choice == "2":
            see_applications(token)
        elif choice == "3":
            update_status(token)
        elif choice == "4":
            see_stats(token)
        elif choice == "q":
            print("Goodbye!")
            break
        else:
            print("Please choose 1, 2, 3, 4, or q.")


if __name__ == "__main__":
    main()
