import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app import app
from scripts import import_historical_seed, reset_live_messages
from src import db


ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seeds" / "mor_mcguyver_historical_seed_initial.json"


class HistoricalBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "messages.db"
        self.db_patch = patch.object(db, "DB_PATH", self.database_path)
        self.db_patch.start()
        db.init_db()
        db.insert_message(
            {
                "source": "baileys",
                "chat_id": "live-validation",
                "whatsapp_message_id": "live-message-1",
                "sender_phone": "live-sender",
                "timestamp": "2026-07-06T12:00:00+00:00",
                "message_type": "text",
                "text_body": "Live message must remain separate",
            }
        )
        app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = app.test_client()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def _import_seed(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = import_historical_seed.main(
                [str(SEED), "--db", str(self.database_path), "--strict"]
            )
        self.assertEqual(result, 0, output.getvalue())
        return output.getvalue()

    def test_import_is_idempotent_and_does_not_touch_live_messages(self):
        first_output = self._import_seed()
        self.assertIn('"inserted": 119', first_output)

        with db.get_connection() as connection:
            first_counts = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in db.HISTORICAL_TABLES[:-1]
            }
            live_count = connection.execute(
                "SELECT COUNT(*) FROM messages"
            ).fetchone()[0]
        self.assertEqual(live_count, 1)
        self.assertEqual(first_counts["historical_events"], 78)
        self.assertEqual(first_counts["historical_machine_metrics"], 24)
        self.assertEqual(first_counts["historical_fault_families"], 11)

        second_output = self._import_seed()
        self.assertIn('"inserted": 0', second_output)
        self.assertIn('"skipped": 119', second_output)
        with db.get_connection() as connection:
            second_counts = {
                table: connection.execute(
                    f"SELECT COUNT(*) FROM {table}"
                ).fetchone()[0]
                for table in db.HISTORICAL_TABLES[:-1]
            }
        self.assertEqual(first_counts, second_counts)

    def test_historical_dashboard_administration_and_apis_are_open(self):
        self._import_seed()

        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Historical Baseline - Mor / McGuyver", dashboard.data)
        self.assertIn("Comexi".encode(), dashboard.data)

        administration = self.client.get("/administration")
        self.assertEqual(administration.status_code, 200)
        self.assertIn(b"Historical Baseline", administration.data)
        self.assertIn(b"<strong>78</strong><span>events</span>", administration.data)

        expected_keys = {
            "/api/historical/summary": "available",
            "/api/historical/sources": "sources",
            "/api/historical/machines": "machines",
            "/api/historical/faults": "faults",
            "/api/historical/actions": "actions",
        }
        for route, key in expected_keys.items():
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn(key, response.get_json())

        summary = self.client.get("/api/historical/summary").get_json()
        self.assertEqual(summary["metrics"]["total_events"], 78)
        self.assertEqual(summary["metrics"]["machines_covered"], 24)
        self.assertEqual(len(summary["machines"]), 24)
        self.assertEqual(len(summary["faults"]), 11)

        live_stats = self.client.get("/api/stats").get_json()
        self.assertEqual(live_stats["total_messages"], 1)

    def test_reset_removes_live_messages_and_preserves_history(self):
        self._import_seed()
        with db.get_connection() as connection:
            historical_before = connection.execute(
                "SELECT COUNT(*) FROM historical_events"
            ).fetchone()[0]

        output = io.StringIO()
        with redirect_stdout(output):
            result = reset_live_messages.main(
                [
                    "--db",
                    str(self.database_path),
                    "--all-live",
                    "--confirm",
                ]
            )
        self.assertEqual(result, 0, output.getvalue())

        with db.get_connection() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                0,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM historical_events"
                ).fetchone()[0],
                historical_before,
            )

    def test_meta_webhook_stays_live_and_separate_from_history(self):
        self._import_seed()
        response = self.client.post(
            "/webhook",
            json={
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {
                                        "phone_number_id": "validation-business",
                                        "display_phone_number": "validation-display",
                                    },
                                    "contacts": [
                                        {
                                            "wa_id": "validation-meta-sender",
                                            "profile": {"name": "Validation Sender"},
                                        }
                                    ],
                                    "messages": [
                                        {
                                            "id": "historical-meta-validation-001",
                                            "from": "validation-meta-sender",
                                            "timestamp": "1783353600",
                                            "type": "text",
                                            "text": {"body": "Meta validation message"},
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "received")
        with db.get_connection() as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM historical_events"
                ).fetchone()[0],
                78,
            )

    def test_empty_database_shows_historical_no_data_state(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No historical baseline imported yet.", response.data)


if __name__ == "__main__":
    unittest.main()
