import argparse
import configparser
import json
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

PERMIT_ID = 445860
API_URL_TEMPLATE = (
    "https://www.recreation.gov/api/permitinyo/{permit_id}/availabilityv2"
    "?start_date={start_date}&end_date={end_date}"
)
BOOKING_URL = "https://www.recreation.gov/permits/445860"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

STATE_FILE = Path(__file__).parent / ".cache" / "state.json"
CONFIG_FILE = Path(__file__).parent / "config.ini"

CHECK_INTERVAL_SECONDS = 60

def load_config():
    if not CONFIG_FILE.exists():
        print("ERROR: config.ini not found. Copy config.example.ini to config.ini and fill it in.")
        sys.exit(1)
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    required = ["email", "app_password", "start_date", "end_date"]
    for key in required:
        if not config["settings"].get(key):
            print(f"ERROR: Missing '{key}' in config.ini")
            sys.exit(1)
    return config["settings"]


def fetch_availability(start_date, end_date):
    url = API_URL_TEMPLATE.format(
        permit_id=PERMIT_ID,
        start_date=start_date,
        end_date=end_date,
    )
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking {start_date} to {end_date}...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json().get("payload", {})
    except requests.RequestException as e:
        print(f"WARNING: Failed to fetch data: {e}", file=sys.stderr)
        return None


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def find_newly_available(payload, previous_state):
    newly = []
    for date, date_data in payload.items():
        for entry_point_id, ep_data in date_data.items():
            quota = ep_data.get("quota_usage_by_member_daily") or {}
            remaining = quota.get("remaining", 0)
            is_walkup = ep_data.get("is_walkup", False)
            key = f"{date}-{entry_point_id}"
            was_available = previous_state.get(key) == "available"
            if remaining > 0 and not is_walkup and not was_available:
                newly.append({
                    "date": date[:10],
                    "entry_point_id": entry_point_id,
                    "remaining": remaining,
                    "key": key,
                })
    return newly


def build_current_state(payload):
    state = {}
    for date, date_data in payload.items():
        for entry_point_id, ep_data in date_data.items():
            quota = ep_data.get("quota_usage_by_member_daily") or {}
            remaining = quota.get("remaining", 0)
            is_walkup = ep_data.get("is_walkup", False)
            key = f"{date}-{entry_point_id}"
            state[key] = "available" if (remaining > 0 and not is_walkup) else "unavailable"
    return state


def send_email(config, newly_available):
    sender = config.get("sender_email") or config["email"]
    sender_password = config.get("sender_app_password") or config["app_password"]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sorted_avail = sorted(newly_available, key=lambda x: x["date"])

    first_date = sorted_avail[0]["date"]
    subject = f"🏔️ Mt Whitney Permit Available! {first_date}"
    if len(sorted_avail) > 1:
        subject += f" (+{len(sorted_avail) - 1} more)"

    dates_list = "\n".join(
        f"  • {item['date']} — {item['remaining']} spot(s) available"
        for item in sorted_avail
    )

    body_plain = f"""Mt Whitney permit(s) are now available!

Detected at: {now}

Available dates:
{dates_list}

🔗 Book now: {BOOKING_URL}

---
You will only be notified once per availability window.
This alert was sent by your Mt Whitney permit notifier.
"""

    html_parts = [
        "<html><body>",
        "<h2>🏔️ Mt Whitney permits are available!</h2>",
        f"<p><strong>Detected at:</strong> {now}</p>",
        "<h3>Available dates:</h3><ul>",
    ]
    for item in sorted_avail:
        html_parts.append(
            f"<li><strong>{item['date']}</strong> — {item['remaining']} spot(s) available</li>"
        )
    html_parts += [
        "</ul>",
        f'<p><a href="{BOOKING_URL}" style="font-size:1.2em;font-weight:bold;">🔗 Book now →</a></p>',
        "<hr><small>You will only be notified once per availability window.</small>",
        "</body></html>",
    ]
    body_html = "\n".join(html_parts)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = config["email"]
    msg.attach(MIMEText(body_plain, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(sender, sender_password)
        server.sendmail(sender, config["email"], msg.as_string())

    print(f"Email sent for {len(newly_available)} availability window(s).")


def check_once(config, previous_state, test_mode=False):
    payload = fetch_availability(config["start_date"], config["end_date"])
    if payload is None:
        return previous_state

    if test_mode:
        print("\n--- RAW API RESPONSE ---")
        print(json.dumps(payload, indent=2))
        print("--- END RAW RESPONSE ---\n")

    newly_available = find_newly_available(payload, previous_state)
    new_state = build_current_state(payload)

    if test_mode and not newly_available:
        print("[TEST MODE] No real availability found — injecting fake permit to test email...")
        newly_available = [{
            "date": "2026-07-15",
            "entry_point_id": "1",
            "remaining": 3,
            "key": "test-2026-07-15-1",
        }]

    if newly_available:
        print(f"🏔️  {len(newly_available)} new availability window(s) found!")
        try:
            send_email(config, newly_available)
        except Exception as e:
            print(f"ERROR: Failed to send email: {e}", file=sys.stderr)
    else:
        print("No new availability found.")

    if not test_mode:
        save_state(new_state)

    return new_state


def main():
    parser = argparse.ArgumentParser(description="Mt Whitney Permit Notifier")
    parser.add_argument("--test", action="store_true", help="Hit the API but simulate availability if none found, to verify email works")
    args = parser.parse_args()

    config = load_config()
    print("=" * 40)
    print("Mt Whitney Permit Notifier")
    print("=" * 40)
    print(f"Watching:  {config['start_date']} to {config['end_date']}")
    print(f"Alerts →   {config['email']}")

    if args.test:
        print("[TEST MODE] Single check, email will be sent.\n")
        check_once(config, load_state(), test_mode=True)
        return

    print(f"Interval:  every {CHECK_INTERVAL_SECONDS // 60} minutes")
    print("Press Ctrl+C to stop.\n")

    state = load_state()
    while True:
        state = check_once(config, state)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
