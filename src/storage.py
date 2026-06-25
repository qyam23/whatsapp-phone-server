import json
from pathlib import Path
from uuid import uuid4

from src.db import get_connection
from src.utils import now_iso, today_utc_parts


def save_raw_event(payload):
    year, month, day = today_utc_parts()
    folder = Path("raw_events") / year / month / day
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / f"{now_iso().replace(':', '-')}--{uuid4().hex}.json"
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    return str(path)


def upload_file_to_drive(local_path):
    """Placeholder for future Google Drive upload integration."""
    return {
        "local_path": local_path,
        "drive_file_id": None,
        "drive_link": None,
        "upload_status": "not_implemented",
    }


def save_drive_link_to_db(message_id, drive_file_id, drive_link):
    """Placeholder helper for a later Drive workflow."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE media_files
            SET drive_file_id = ?, drive_link = ?, upload_status = 'uploaded'
            WHERE message_id = ?
            """,
            (drive_file_id, drive_link, message_id),
        )
