#!/data/data/com.termux/files/usr/bin/bash
set -e

cd "$(dirname "$0")"

mkdir -p data raw_events exports

python app.py
