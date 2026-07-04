# Mor Factory Desktop Simulation

This package runs the dashboard locally on a Windows computer. It uses synthetic
demo records and does not connect to the phone database.

## Start

1. Double-click `START_DESKTOP_DEMO.bat`.
2. On the first run, choose a dashboard username and password.
3. The OpenAI API key is optional. Press Enter to continue without AI.
4. Sign in at `http://127.0.0.1:8765/login`.

The first run creates a private Python environment, installs the required
packages, creates `data/desktop-demo.db` with synthetic current and historical
records, and opens the browser.

## Add or change AI access

1. Stop the running simulation.
2. Double-click `CONFIGURE_DESKTOP.bat`.
3. Leave the password blank to keep it unchanged.
4. Paste an OpenAI API key when prompted, or leave it blank to keep AI disabled.
5. Run `START_DESKTOP_DEMO.bat` again.

The API key is stored only in `.env.desktop`. This file is excluded from Git.
The application sends only bounded, redacted results through approved read-only
analysis tools. The model cannot execute arbitrary SQL.

## Local files

- `.env.desktop`: private username, password hash, session key, and optional API key.
- `.desktop_venv`: private Python environment.
- `data/desktop-demo.db`: synthetic desktop database.

To create a fresh demo database, stop the simulation and remove
`data\desktop-demo.db`. It will be recreated at the next start.

Use a new dashboard password. Do not reuse a password that was sent in chat.
