import os
import sys
import threading
import webbrowser
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.desktop"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    os.chdir(ROOT)
    load_dotenv(ENV_PATH, override=True)
    os.environ.setdefault(
        "WHATSAPP_DB_PATH",
        str((ROOT / "data" / "desktop-demo.db").resolve()),
    )
    os.environ["DESKTOP_DEMO"] = "1"

    if not os.getenv("QUERY_PASSWORD_HASH") or not os.getenv("FLASK_SECRET_KEY"):
        raise SystemExit(
            "Desktop settings are missing. Run CONFIGURE_DESKTOP.bat first."
        )

    from scripts.seed_desktop_demo import seed_if_empty

    message_count = seed_if_empty()

    from app import app

    port = int(os.getenv("DESKTOP_PORT", "8765"))
    url = f"http://127.0.0.1:{port}/login"
    print("")
    print("Mor Factory Desktop Simulation")
    print(f"URL: {url}")
    print(f"Synthetic messages: {message_count}")
    print("Close this window or press Ctrl+C to stop the server.")
    if os.getenv("DESKTOP_OPEN_BROWSER", "1") != "0":
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
