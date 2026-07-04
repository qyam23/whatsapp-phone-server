# Mor Factory Desktop Simulation

This package runs the dashboard locally on a Windows computer. It uses synthetic
demo records and does not connect to the phone database.

## Start

1. Double-click `START_DESKTOP_DEMO.bat`.
2. Open `http://127.0.0.1:8765/dashboard`.
3. The operational dashboard works without login or an OpenAI API key.

AI mode uses the fixed local account:

```text
username: qyam2323
password: mor
```

The first run creates a private Python environment, installs the required
packages, creates `data/desktop-demo.db` with synthetic current and historical
records, and opens the browser.

## Add or change AI access

1. Stop the running simulation.
2. Double-click `CONFIGURE_DESKTOP.bat`.
3. Paste an OpenAI API key when prompted, or leave it blank to keep AI disabled.
4. Run `START_DESKTOP_DEMO.bat` again.

The API key is stored only in `.env.desktop`. This file is excluded from Git.
The application sends only bounded, redacted results through approved read-only
analysis tools. The model cannot execute arbitrary SQL.

## Local files

- `.env.desktop`: private session key and optional API key.
- `.desktop_venv`: private Python environment.
- `data/desktop-demo.db`: synthetic desktop database.

To create a fresh demo database, stop the simulation and remove
`data\desktop-demo.db`. It will be recreated at the next start.

The fixed AI password is stored in application code only as a one-way hash.
