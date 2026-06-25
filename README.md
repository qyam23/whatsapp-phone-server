# WhatsApp Phone Server

Lightweight Android Termux-compatible WhatsApp Cloud API webhook evidence server.

It receives Meta WhatsApp webhooks, saves every raw payload to disk, parses message records into SQLite, and exposes a browser dashboard that can be opened from a desktop browser through Cloudflare Tunnel.

## What This Is

- Flask app for Termux.
- SQLite database at `data/messages.db`.
- Raw webhook JSON archive under `raw_events/YYYY/MM/DD/`.
- Browser dashboard at `/dashboard`.
- CSV and JSON exports.
- Placeholder hooks for a future Google Drive upload workflow.

## What This Is Not

- No Docker.
- No FastAPI.
- No PostgreSQL yet.
- No Google Drive upload yet.
- No AI, OCR, Whisper, LLM, embeddings, or model processing.
- No hardcoded tokens.

## Android Termux Install

Run this once in Termux:

```bash
pkg update && pkg upgrade
pkg install python git cloudflared sqlite
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
- `GET /dashboard` opens the browser dashboard.
- `GET /messages` shows recent parsed messages.
- `GET /api/stats` returns JSON stats.
- `GET /api/messages` returns recent messages as JSON.
- `GET /export/messages.csv` downloads CSV.
- `GET /export/messages.json` downloads JSON.

## Dashboard

Open from desktop through the same Cloudflare Tunnel:

```text
https://xxxxx.trycloudflare.com/dashboard
```

The dashboard shows:

- Total messages.
- Messages today.
- Counts for text, image, audio, video, document, and unknown messages.
- Last webhook received time.
- Last message received time.
- Messages by type.
- Messages by sender.
- Messages by day.
- Last 20 messages.

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
