import argparse
import getpass
import secrets
from pathlib import Path

from dotenv import dotenv_values
from werkzeug.security import generate_password_hash


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.desktop"


def _prompt(label, current="", default=""):
    fallback = current or default
    suffix = f" [{fallback}]" if fallback else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or fallback


def configure_desktop():
    existing = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    username = _prompt(
        "Dashboard username",
        existing.get("QUERY_USERNAME", ""),
        "qyam2323",
    )
    if not username or any(character in username for character in "\r\n="):
        raise SystemExit("Username cannot be empty or contain '=', CR, or LF.")

    existing_hash = existing.get("QUERY_PASSWORD_HASH", "")
    password = getpass.getpass(
        "Dashboard password (leave blank to keep the current password): "
    )
    if password:
        confirmation = getpass.getpass("Confirm dashboard password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match.")
        password_hash = generate_password_hash(password)
    elif existing_hash:
        password_hash = existing_hash
    else:
        raise SystemExit("A dashboard password is required on first setup.")

    existing_key = existing.get("OPENAI_API_KEY", "")
    api_key = getpass.getpass(
        "OpenAI API key (optional, leave blank to skip or keep current): "
    )
    api_key = api_key or existing_key
    if any(character in api_key for character in "\r\n"):
        raise SystemExit("API key cannot contain CR or LF.")

    model = _prompt(
        "OpenAI model",
        existing.get("OPENAI_MODEL", ""),
        "gpt-5.4-mini",
    )
    port = existing.get("DESKTOP_PORT", "8765")
    secret_key = existing.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    database_path = (ROOT / "data" / "desktop-demo.db").resolve().as_posix()

    content = "\n".join(
        [
            f"QUERY_USERNAME={username}",
            f"QUERY_PASSWORD_HASH={password_hash}",
            f"FLASK_SECRET_KEY={secret_key}",
            "SESSION_COOKIE_SECURE=0",
            f"OPENAI_API_KEY={api_key}",
            f"OPENAI_MODEL={model}",
            f"WHATSAPP_DB_PATH={database_path}",
            "DESKTOP_DEMO=1",
            f"DESKTOP_PORT={port}",
            "",
        ]
    )
    ENV_PATH.write_text(content, encoding="utf-8")
    print(f"\nDesktop settings saved to {ENV_PATH}")
    print("The password and API key were not displayed.")


def main():
    parser = argparse.ArgumentParser(description="Configure the local desktop demo.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Open configuration even when it already exists.",
    )
    args = parser.parse_args()
    if ENV_PATH.exists() and not args.force:
        print(f"Desktop settings already exist at {ENV_PATH}")
        return
    configure_desktop()


if __name__ == "__main__":
    main()
