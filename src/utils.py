import csv
import io
import os
from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_utc_parts():
    now = datetime.now(timezone.utc)
    return now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")


def get_env(name, default=None):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def rows_to_csv(rows):
    if not rows:
        return ""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
