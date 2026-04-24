# Mt. Whitney Permit Notifier

Get an email the moment a Mt. Whitney permit becomes available on [recreation.gov](https://www.recreation.gov/permits/445860).

## Setup

### Step 1 — Install Python

Download and install Python from [python.org](https://www.python.org/downloads/).

> **Windows:** Check "Add Python to PATH" during installation.

### Step 2 — Install dependencies

**Mac/Linux:**

```bash
pip3 install -r requirements.txt
```

**Windows:**

```bash
pip install -r requirements.txt
```

### Step 3 — Set up your config file

Rename `config.example.ini` to `config.ini` (you can do this in File Explorer or Finder), then open it in any text editor and fill in:

- **`email`** — the email address where you want alerts sent
- **`app_password`** — your Gmail App Password _(not your regular password)_
- **`start_date` / `end_date`** — the date range you want to watch (YYYY-MM-DD)

**How to get a Gmail App Password:**

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Sign in and create a new app password
3. Copy the 16-character password into `config.ini`

### Step 4 — Run it

**Mac/Linux:**

```bash
python3 notifier.py
```

**Windows:**

```bash
python notifier.py
```

Leave the window open. You'll get an email the moment a permit becomes available. Press `Ctrl+C` to stop.

## Test your setup

Run with `--test` to verify your email is configured correctly before leaving it running:

**Mac/Linux:**

```bash
python3 notifier.py --test
```

**Windows:**

```bash
python notifier.py --test
```

This hits the real API and sends a test email (simulating availability if none is currently found).
