from datetime import datetime, timezone


SUPPORTED_TYPES = {"text", "image", "audio", "video", "document", "sticker"}


def parse_whatsapp_messages(payload, raw_json_path):
    records = []

    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            metadata = value.get("metadata", {}) or {}
            contacts_by_wa_id = _contacts_by_wa_id(value.get("contacts", []))

            for message in value.get("messages", []) or []:
                records.append(
                    _parse_message(
                        message=message,
                        metadata=metadata,
                        contacts_by_wa_id=contacts_by_wa_id,
                        raw_json_path=raw_json_path,
                    )
                )

    return records


def _contacts_by_wa_id(contacts):
    result = {}
    for contact in contacts or []:
        wa_id = contact.get("wa_id")
        if wa_id:
            result[wa_id] = contact
    return result


def _parse_message(message, metadata, contacts_by_wa_id, raw_json_path):
    message_type = message.get("type") or "unknown"
    if message_type not in SUPPORTED_TYPES:
        message_type = "unknown"

    sender_phone = message.get("from")
    contact = contacts_by_wa_id.get(sender_phone, {})
    profile = contact.get("profile", {}) or {}
    raw_timestamp = message.get("timestamp")

    record = {
        "whatsapp_message_id": message.get("id"),
        "wa_business_phone_number_id": metadata.get("phone_number_id"),
        "display_phone_number": metadata.get("display_phone_number"),
        "sender_phone": sender_phone,
        "sender_name": profile.get("name"),
        "timestamp": _timestamp_to_iso(raw_timestamp),
        "message_type": message_type,
        "text_body": None,
        "media_id": None,
        "media_mime_type": None,
        "media_sha256": None,
        "media_filename": None,
        "media_caption": None,
        "raw_json_path": raw_json_path,
        "processing_status": "new",
    }

    if message_type == "text":
        record["text_body"] = (message.get("text", {}) or {}).get("body")
    elif message_type in {"image", "audio", "video", "document", "sticker"}:
        media = message.get(message_type, {}) or {}
        record["media_id"] = media.get("id")
        record["media_mime_type"] = media.get("mime_type")
        record["media_sha256"] = media.get("sha256")
        record["media_caption"] = media.get("caption")
        record["media_filename"] = media.get("filename")

    return record


def _timestamp_to_iso(raw_timestamp):
    if raw_timestamp is None:
        return None

    try:
        return datetime.fromtimestamp(int(raw_timestamp), timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return str(raw_timestamp)
