# AGENTS.md

## Project Goal

This project is a lightweight Android Termux-compatible Flask webhook evidence server for Meta WhatsApp Cloud API events.

## Runtime Rules

- Target runtime is Android Termux with Python 3.
- Use Flask only.
- Use Python stdlib `sqlite3`.
- Keep dependencies lightweight.
- Do not add FastAPI, pydantic, Celery, Redis, Docker, PostgreSQL, AI, OCR, Whisper, embeddings, LLMs, or Hugging Face models.
- All secrets must come from `.env`.
- Never hardcode or print access tokens.

## Current Architecture

- `app.py` defines the Flask app and webhook/export routes.
- `src/db.py` owns SQLite schema, inserts, queries, and stats.
- `src/parser.py` parses Meta WhatsApp webhook payloads.
- `src/storage.py` saves raw JSON and contains Google Drive placeholders.
- `src/dashboard.py` owns dashboard/API routes.
- `templates/` contains Flask HTML templates.
- `static/style.css` contains dashboard styling.
- `run_server.sh` starts the Flask server on Termux.
- `run_tunnel.sh` starts Cloudflare Tunnel.

## Scope Boundaries

- Incoming webhooks are captured and stored.
- Media metadata is captured, but media binary download is not implemented yet.
- Google Drive upload is not implemented yet.
- The server should remain simple enough to edit and debug from Termux.
