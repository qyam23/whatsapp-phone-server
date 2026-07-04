import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


PEOPLE = [
    ("Dana Levi", "demo-dana"),
    ("Avi Cohen", "demo-avi"),
    ("Noa Shalom", "demo-noa"),
    ("Eli Ben David", "demo-eli"),
    ("Maya Azulay", "demo-maya"),
]
CHATS = [
    ("Production Control", "demo-production"),
    ("Maintenance Team", "demo-maintenance"),
    ("Packaging Line", "demo-packaging"),
]
MACHINES = [
    ("CNC-03", "Machining", "CNC-03"),
    ("PACK-07", "Packaging", "PACK-07"),
    ("MIX-02", "Mixing", "MIX-02"),
]


def _message(index, occurred_at):
    sender_name, sender_id = PEOPLE[index % len(PEOPLE)]
    chat_name, chat_id = CHATS[index % len(CHATS)]
    _, _, pattern = MACHINES[(index // 2) % len(MACHINES)]
    if index % 2:
        text = f"{pattern} fault opened - production stopped for inspection"
    else:
        text = f"{pattern} fixed and closed - machine running"

    timestamp = occurred_at.isoformat(timespec="seconds")
    return {
        "source": "desktop-demo",
        "chat_id": chat_id,
        "chat_name": chat_name,
        "is_group": 1,
        "group_id": chat_id,
        "whatsapp_message_id": f"desktop-demo-{index:04d}",
        "sender_phone": sender_id,
        "sender_name": sender_name,
        "timestamp": timestamp,
        "message_type": "text",
        "text_body": text,
        "processing_status": "demo",
        "created_at": timestamp,
    }


def seed_if_empty():
    from src.db import (
        get_connection,
        init_db,
        insert_message,
        upsert_machine_rule,
    )

    init_db()
    with get_connection() as connection:
        current_count = connection.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0]
    if current_count:
        return current_count

    now = datetime.now(timezone.utc)
    records = []
    for index in range(48):
        records.append(_message(index, now - timedelta(minutes=index * 15)))
    for previous_index in range(36):
        index = previous_index + 48
        records.append(
            _message(
                index,
                now - timedelta(hours=12, minutes=previous_index * 20),
            )
        )
    for historical_index in range(48):
        index = historical_index + 84
        records.append(
            _message(index, now - timedelta(hours=24 + 12 * historical_index))
        )

    for record in records:
        insert_message(record)
    for machine_name, department, pattern in MACHINES:
        upsert_machine_rule(
            machine_name=machine_name,
            department=department,
            pattern=pattern,
        )
    return len(records)


if __name__ == "__main__":
    print(f"Desktop demo contains {seed_if_empty()} messages.")
