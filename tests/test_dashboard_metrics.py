import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src import db


NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


class ManagementDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(
            db, "DB_PATH", Path(self.temp_dir.name) / "messages.db"
        )
        self.db_patch.start()
        db.init_db()
        self._seed_messages()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def _insert(self, message_id, hours_ago, sender, group, text):
        db.insert_message(
            {
                "source": "baileys",
                "chat_id": f"{group.lower().replace(' ', '-') }@g.us",
                "chat_name": group,
                "is_group": 1,
                "whatsapp_message_id": message_id,
                "sender_phone": f"{sender.lower()}@s.whatsapp.net",
                "sender_name": sender,
                "timestamp": (NOW - timedelta(hours=hours_ago)).isoformat(),
                "message_type": "text",
                "text_body": text,
            }
        )

    def _seed_messages(self):
        self._insert("m1", 2.5, "Alice", "Machining", "CNC 03 fault down")
        self._insert("m2", 1.5, "Bob", "Machining", "Checking the machine")
        self._insert("m3", 0.5, "Alice", "Machining", "CNC 03 fixed and running")
        self._insert("m4", 3.5, "Charlie", "Packing", "Packaging update")
        self._insert("m5", 4.5, "Alice", "Machining", "Shift handover")
        self._insert("m6", 5.5, "Bob", "Packing", "Production status")
        self._insert("p1", 13, "Alice", "Machining", "Previous period")
        self._insert("p2", 18, "Bob", "Packing", "Previous period")
        self._insert("w1", 72, "Dana", "Packing", "Weekly history")
        self._insert("m30", 480, "Eli", "Machining", "Monthly history")

    def test_time_windows_and_comparison_do_not_double_count(self):
        last_12_hours = db.get_management_dashboard("12h", now=NOW)
        last_7_days = db.get_management_dashboard("7d", now=NOW)
        last_30_days = db.get_management_dashboard("30d", now=NOW)
        with db.get_connection() as conn:
            direct_12_hour_count = conn.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE datetime(COALESCE(timestamp, created_at)) >= datetime(?)
                  AND datetime(COALESCE(timestamp, created_at)) < datetime(?)
                """,
                ((NOW - timedelta(hours=12)).isoformat(), NOW.isoformat()),
            ).fetchone()[0]

        self.assertEqual(last_12_hours["metrics"]["messages"], 6)
        self.assertEqual(last_12_hours["metrics"]["messages"], direct_12_hour_count)
        self.assertEqual(sum(last_12_hours["trend"]["current"]), 6)
        self.assertEqual(sum(last_12_hours["trend"]["previous"]), 2)
        self.assertEqual(last_7_days["metrics"]["messages"], 9)
        self.assertEqual(last_30_days["metrics"]["messages"], 10)

    def test_people_groups_rate_and_gap_use_current_period_only(self):
        dashboard = db.get_management_dashboard("12h", now=NOW)

        self.assertEqual(dashboard["metrics"]["active_senders"], 3)
        self.assertEqual(dashboard["metrics"]["active_groups"], 2)
        self.assertEqual(dashboard["metrics"]["messages_per_hour"], 0.5)
        self.assertEqual(dashboard["metrics"]["average_gap"], "1.0 hr")
        self.assertEqual(dashboard["top_senders"][0]["label"], "Alice")
        self.assertEqual(dashboard["top_senders"][0]["count"], 3)

    def test_machine_metrics_are_unavailable_without_rules(self):
        dashboard = db.get_management_dashboard("12h", now=NOW)

        self.assertFalse(dashboard["machine_data_available"])
        self.assertEqual(dashboard["machine_period"]["opened"], 0)
        self.assertEqual(dashboard["machine_period"]["closed"], 0)

    def test_machine_rules_enable_auditable_open_close_metrics(self):
        db.upsert_machine_rule(
            machine_name="CNC-03",
            department="Machining",
            pattern="CNC 03",
            open_keywords="fault,down",
            close_keywords="fixed,running",
        )

        dashboard = db.get_management_dashboard("12h", now=NOW)

        self.assertTrue(dashboard["machine_data_available"])
        self.assertEqual(dashboard["machine_period"]["opened"], 1)
        self.assertEqual(dashboard["machine_period"]["closed"], 1)
        self.assertEqual(dashboard["machine_period"]["average_resolution"], "2.0 hr")
        self.assertEqual(
            dashboard["machine_month"]["recurrence"],
            [{"machine": "CNC-03", "count": 1}],
        )

    def test_empty_database_returns_zeroes_and_honest_no_data_states(self):
        with tempfile.TemporaryDirectory() as empty_dir:
            with patch.object(db, "DB_PATH", Path(empty_dir) / "empty.db"):
                db.init_db()
                dashboard = db.get_management_dashboard("12h", now=NOW)

        self.assertEqual(dashboard["metrics"]["messages"], 0)
        self.assertEqual(dashboard["metrics"]["average_gap"], "No data")
        self.assertFalse(dashboard["machine_data_available"])
        self.assertEqual(sum(dashboard["trend"]["current"]), 0)


if __name__ == "__main__":
    unittest.main()
