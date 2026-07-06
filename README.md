# WhatsApp Phone Server

## Windows desktop simulation

For local development without the phone, double-click
`START_DESKTOP_DEMO.bat`. The simulation runs at
`http://127.0.0.1:8765`, uses synthetic data, and works without an AI API key.
See [DESKTOP_DEMO.md](DESKTOP_DEMO.md) for setup and optional API access.

Lightweight Android Termux-compatible WhatsApp Cloud API webhook evidence server.

It receives Meta WhatsApp webhooks, saves every raw payload to disk, parses message records into SQLite, and exposes a browser dashboard that can be opened from a desktop browser through Cloudflare Tunnel.

It also includes an optional unofficial WhatsApp Web companion bridge using WhiskeySockets/Baileys for a personal or regular WhatsApp account that is linked as a device.

## What This Is

- Flask app for Termux.
- SQLite database at `data/messages.db`.
- Raw webhook JSON archive under `raw_events/YYYY/MM/DD/`.
- Browser dashboard at `/dashboard`.
- CSV and JSON exports.
- Placeholder hooks for a future Google Drive upload workflow.
- Optional Baileys companion ingestion at `POST /ingest/companion`.

## What This Is Not

- No Docker.
- No FastAPI.
- No PostgreSQL yet.
- No Google Drive upload yet.
- No AI, OCR, Whisper, LLM, embeddings, or model processing.
- No hardcoded tokens.

## Important Companion Mode Warning

The companion bridge uses WhatsApp Web / linked device behavior through the unofficial WhiskeySockets/Baileys library. This is not the official Meta Cloud API. It may be fragile, can break when WhatsApp changes Web behavior, and may violate WhatsApp policies or terms. Use carefully. Avoid spam, automation abuse, scraping at scale, or sending unsolicited messages.

## Android Termux Install

Run this once in Termux:

```bash
pkg update && pkg upgrade
pkg install python git cloudflared sqlite nodejs
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Clone

```bash
git clone <REPO_URL> whatsapp-phone-server
cd whatsapp-phone-server
cp .env.example .env
```

Edit `.env` and set your verify token:

```bash
nano .env
```

Required for Meta webhook verification:

```env
WHATSAPP_VERIFY_TOKEN=test123
```

Optional placeholders for future API/media workflows:

```env
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
GOOGLE_DRIVE_ROOT_FOLDER_ID=
APP_ENV=development
```

## Run Server

Termux session 1:

```bash
bash run_server.sh
```

The local server listens on:

```text
http://127.0.0.1:8000
```

## Run Cloudflare Tunnel

Termux session 2:

```bash
bash run_tunnel.sh
```

Cloudflare will print a temporary public URL like:

```text
https://xxxxx.trycloudflare.com
```

## Meta Webhook Setup

Callback URL:

```text
https://xxxxx.trycloudflare.com/webhook
```

Verify Token:

```text
Use the value from WHATSAPP_VERIFY_TOKEN in .env
```

## Routes

- `GET /health` returns `{"status":"ok"}`.
- `GET /webhook` handles Meta verification.
- `POST /webhook` receives webhook events.
- `POST /ingest/companion` receives normalized Baileys companion events.
- `GET /dashboard` opens the browser dashboard.
- `GET /query` opens the authenticated AI data assistant.
- `GET /administration` manages capture and machine classification rules.
- `GET /messages` shows recent parsed messages.
- `GET /api/stats` returns JSON stats.
- `GET /api/management?period=12h` returns management dashboard metrics.
- `GET /api/messages` returns recent messages as JSON.
- `GET /export/messages.csv` downloads CSV.
- `GET /export/messages.json` downloads JSON.

## Dashboard

Open from desktop through the same Cloudflare Tunnel:

```text
https://xxxxx.trycloudflare.com/dashboard
```

The management dashboard shows:

- Rolling windows for the last 12 hours, 7 days, and 30 days.
- Message volume compared with the previous equal period.
- Active people and WhatsApp groups.
- Message rate and average time between consecutive messages.
- Message activity trends and ranked people/groups.
- Optional machine openings, closures, resolution time, and 30-day recurrence.
- Source freshness and an automatic 12-hour browser refresh.

Machine metrics are never inferred without a rule. Configure auditable text-matching
rules under `/administration`. Until a rule matches stored messages, the dashboard
shows an explicit no-data state instead of sample or fabricated values.

Technical filters, exports, retention rules, machine classification, and recent raw
records live under `/administration`.

### Live monitored scope

When one or more retention rules are active, every live dashboard period, ranking,
machine calculation, operational API, message list, AI sample, and export is
limited to messages matching those chats/groups/senders. Active rules are combined
with OR; URL/search filters are then applied with AND.

With no active retention rules, live views fall back to all messages. The
Administration `Clear filters` action clears temporary search controls only. To
return the live dashboard to all messages, pause or delete every retention rule.
Historical baseline data remains fixed and is never filtered by live retention
rules.

## Mor / McGuyver Historical Baseline

Prepared historical evidence is stored in separate `historical_*` tables. It is
never inserted into the live `messages` table and does not inflate WhatsApp
message, sender, group, frequency, or timing metrics.

Import and validate:

```bash
python scripts/import_historical_seed.py \
  seeds/mor_mcguyver_historical_seed_initial.json \
  --backup-first \
  --strict
python scripts/validate_historical_db.py
```

The dashboard shows a separate historical machine/fault section. Administration
shows source provenance, report coverage, table counts, and import-run status.

Read-only routes:

- `GET /api/historical/summary`
- `GET /api/historical/sources`
- `GET /api/historical/machines`
- `GET /api/historical/faults`
- `GET /api/historical/actions`

See `docs/HISTORICAL_BASELINE.md` and
`docs/HISTORICAL_FIELD_DICTIONARY.md` for the complete workflow and field map.

## Dashboard and AI Authentication

Normal operations are open immediately after startup. No login or authentication
variables are required for the dashboard, administration, messages, operational
APIs, exports, Baileys ingestion, Meta webhooks, or health checks.

Only features that can send data to an external AI service or consume API credits
require AI-mode login:

```text
username: qyam2323
password: mor
```

The application stores only the generated password hash in the authentication
module. The clear password is not rendered in the UI or written to logs. AI
sessions expire after 30 minutes, and five failed login attempts from one client
trigger a temporary 15-minute lockout.

`FLASK_SECRET_KEY` is optional. The app includes a stable local fallback so a
fresh pull starts without `.env` authentication fields. Set a private
`FLASK_SECRET_KEY` and `SESSION_COOKIE_SECURE=1` when exposing the server through
an HTTPS Cloudflare hostname.

## AI Data Assistant

The optional assistant uses the OpenAI Responses API. The model has no arbitrary
SQL tool and no database connection. It can only request these server-owned,
read-only operations:

- operations summary
- top people
- top groups
- activity trend
- machine recurrence
- up to 30 recent matching messages

Phone numbers and email addresses are redacted from message samples before they
are sent to the API. Every question, tool name, status, and execution duration is
recorded locally in `query_audit`.

Configure the API on the phone:

```env
OPENAI_API_KEY=<server-side-api-key>
OPENAI_MODEL=gpt-5.4-mini
```

Never place the API key in HTML, JavaScript, Git, screenshots, or chat messages.
The key is optional until an AI action is used. After changing `.env`, restart
Flask.

## Storage

SQLite database:

```text
data/messages.db
```

Raw JSON payloads:

```text
raw_events/YYYY/MM/DD/
```

Exports:

```text
exports/
```

## Supported Message Types

- `text`
- `image`
- `audio`
- `video`
- `document`
- `sticker`
- `unknown`

For text messages, the text body is saved.

For image, video, document, audio, and sticker messages, the media metadata is saved when present. Media file download is intentionally not implemented yet.

## Optional Baileys Companion Bridge

Use this only if you need a second ingestion path for a personal or regular WhatsApp account that is not moved to WhatsApp Cloud API.

Start the Flask server first:

```bash
bash run_server.sh
```

Open a second Termux session:

```bash
cd companion_bridge
npm install
npm start
```

The bridge will print a QR code. On your phone, open WhatsApp and link it from:

```text
WhatsApp > Linked devices
```

By default, the bridge posts normalized records to:

```text
http://127.0.0.1:8000/ingest/companion
```

You can override this if needed:

```bash
FLASK_INGEST_URL=http://127.0.0.1:8000/ingest/companion npm start
```

The bridge currently supports text ingestion first. It detects image, audio, video, document, and sticker metadata paths for future media handling, but media binary download is not implemented yet.

Companion raw events are saved locally by the bridge under:

```text
raw_events/baileys/YYYY/MM/DD/
```

The Flask endpoint also stores the normalized companion payload under:

```text
raw_events/baileys/YYYY/MM/DD/
```

## Google Drive Placeholder

`src/storage.py` contains future hooks:

- `upload_file_to_drive(local_path)`
- `save_drive_link_to_db(message_id, drive_file_id, drive_link)`

These are placeholders only. No Google Drive upload happens yet.

## Validation Checklist

- `/health` returns ok.
- Meta webhook verify returns the challenge.
- Meta messages test creates a raw JSON file.
- `data/messages.db` is created.
- Dashboard opens at `/dashboard`.
- `/api/stats` returns counts.
- `/export/messages.csv` downloads CSV.
- Companion bridge starts and prints a QR code.
- A direct WhatsApp message appears in `/dashboard` with `source=baileys`.
- A group WhatsApp message appears with its `chat_id` and group name when available.

## Local Desktop Smoke Test

For quick local validation outside Termux:

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/dashboard
```
