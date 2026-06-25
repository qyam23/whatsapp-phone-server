#!/data/data/com.termux/files/usr/bin/bash
set -e

cloudflared tunnel --url http://127.0.0.1:8000
