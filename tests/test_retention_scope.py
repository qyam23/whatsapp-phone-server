import csv
import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app import app
from src import db


class RetentionScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "messages.db"
        self.db_patch = patch.object(db, "DB_PATH", self.database_path)
        self.db_patch.start()
        db.init_db()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = app.test_client()
        self._seed_messages()

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def _insert(
        self,
        message_id,
        hours_ago,
        chat_id,
        sender_id,
        sender_name,
        text,
        is_group=True,
    ):
        db.insert_message(
            {
                "source": "baileys",
                "chat_id": chat_id,
                "chat_name": "Shared Operations",
                "is_group": 1 if is_group else 0,
                "group_id": chat_id if is_group else None,
                "whatsapp_message_id": message_id,
                "sender_phone": sender_id,
                "sender_name": sender_name,
                "timestamp": (self.now - timedelta(hours=hours_ago)).isoformat(),
                "message_type": "text",
                "text_body": text,
            }
        )

    def _seed_messages(self):
        selected = "selected-group@g.us"
        other = "other-group@g.us"
        self._insert(
            "selected-open",
            5,
            selected,
            "alice@s.whatsapp.net",
            "Alice",
            "CNC 03 fault down",
        )
        self._insert(
            "selected-status",
            4,
            selected,
            "bob@s.whatsapp.net",
            "Bob",
            "Production status",
        )
        self._insert(
            "selected-close",
            3,
            selected,
            "alice@s.whatsapp.net",
            "Alice",
            "CNC 03 fixed running",
        )
        self._insert(
            "selected-week",
            48,
            selected,
            "dana@s.whatsapp.net",
            "Dana",
            "Weekly selected record",
        )
        self._insert(
            "selected-month",
            480,
            selected,
            "eli@s.whatsapp.net",
            "Eli",
            "Monthly selected record",
        )
        self._insert(
            "other-recent",
            2,
            other,
            "alice@s.whatsapp.net",
            "Alice",
            "Other group recent record",
        )
        self._insert(
            "other-week",
            72,
            other,
            "charlie@s.whatsapp.net",
            "Charlie",
            "Other group weekly record",
        )
        self._insert(
            "direct-same-id",
            1,
            selected,
            "alice@s.whatsapp.net",
            "Alice",
            "Direct record with reused chat identifier",
            is_group=False,
        )

    def _enable_selected_group(self):
        db.upsert_retention_rule(
            "chat",
            "selected-group@g.us",
            label="Shared Operations",
            is_group=1,
        )

    def test_no_active_rules_fall_back_to_all_live_messages(self):
        dashboard = db.get_management_dashboard("12h", now=self.now)
        stats = db.get_stats()

        self.assertEqual(dashboard["metrics"]["messages"], 5)
        self.assertFalse(dashboard["live_scope"]["filtered"])
        self.assertEqual(dashboard["live_scope"]["label"], "Live data: all messages")
        self.assertEqual(stats["total_messages"], 8)
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Live data: all messages", response.data)

    def test_all_management_periods_and_rankings_use_selected_group(self):
        self._enable_selected_group()
        db.upsert_machine_rule(
            machine_name="CNC-03",
            department="Machining",
            pattern="CNC 03",
            open_keywords="fault,down",
            close_keywords="fixed,running",
        )

        last_12_hours = db.get_management_dashboard("12h", now=self.now)
        last_7_days = db.get_management_dashboard("7d", now=self.now)
        last_30_days = db.get_management_dashboard("30d", now=self.now)

        self.assertEqual(last_12_hours["metrics"]["messages"], 3)
        self.assertEqual(sum(last_12_hours["trend"]["current"]), 3)
        self.assertEqual(last_12_hours["metrics"]["active_senders"], 2)
        self.assertEqual(last_12_hours["metrics"]["active_groups"], 1)
        self.assertEqual(last_12_hours["top_senders"][0]["label"], "Alice")
        self.assertEqual(last_12_hours["top_senders"][0]["count"], 2)
        self.assertEqual(
            [row["label"] for row in last_12_hours["top_groups"]],
            ["Shared Operations"],
        )
        self.assertEqual(last_12_hours["machine_period"]["opened"], 1)
        self.assertEqual(last_12_hours["machine_period"]["closed"], 1)
        self.assertEqual(
            last_12_hours["machine_month"]["recurrence"],
            [{"machine": "CNC-03", "count": 1}],
        )
        self.assertTrue(last_12_hours["live_scope"]["filtered"])
        self.assertEqual(last_7_days["metrics"]["messages"], 4)
        self.assertEqual(last_30_days["metrics"]["messages"], 5)

    def test_stats_messages_ai_and_exports_share_active_scope(self):
        self._enable_selected_group()

        stats = db.get_stats()
        messages = db.list_messages(limit=None)
        recent = db.get_query_recent_messages(period="30d", limit=30, now=self.now)

        self.assertEqual(stats["total_messages"], 5)
        self.assertEqual(stats["messages_by_chat"][0]["chat_id"], "selected-group@g.us")
        self.assertEqual({row["whatsapp_message_id"] for row in messages}, {
            "selected-open",
            "selected-status",
            "selected-close",
            "selected-week",
            "selected-month",
        })
        self.assertEqual(len(recent["messages"]), 5)

        api_stats = self.client.get("/api/stats").get_json()
        api_management = self.client.get("/api/management?period=30d").get_json()
        api_messages = self.client.get("/api/messages").get_json()["messages"]
        json_export = self.client.get("/export/messages.json").get_json()["messages"]
        csv_export = list(
            csv.DictReader(
                io.StringIO(
                    self.client.get("/export/messages.csv").data.decode("utf-8")
                )
            )
        )

        self.assertEqual(api_stats["total_messages"], 5)
        self.assertTrue(api_stats["live_scope"]["filtered"])
        self.assertEqual(api_management["metrics"]["messages"], 5)
        self.assertEqual(len(api_messages), 5)
        self.assertEqual(len(json_export), 5)
        self.assertEqual(len(csv_export), 5)
        self.assertNotIn("other-recent", {row["whatsapp_message_id"] for row in api_messages})

    def test_stable_id_wins_over_duplicate_label_and_group_flag_is_respected(self):
        self._enable_selected_group()
        messages = db.list_messages(limit=None)
        message_ids = {row["whatsapp_message_id"] for row in messages}

        self.assertNotIn("other-recent", message_ids)
        self.assertNotIn("direct-same-id", message_ids)

        options = db.get_filter_options()
        option_ids = {row["value"] for row in options["chats"]}
        self.assertIn("selected-group@g.us", option_ids)
        self.assertIn("other-group@g.us", option_ids)

    def test_name_fallback_and_sender_scope(self):
        db.upsert_retention_rule(
            "chat",
            "Shared Operations",
            label="Shared Operations",
            is_group=1,
        )
        group_messages = db.list_messages(limit=None)
        self.assertEqual(len(group_messages), 7)
        self.assertNotIn(
            "direct-same-id",
            {row["whatsapp_message_id"] for row in group_messages},
        )

        with db.get_connection() as connection:
            connection.execute("DELETE FROM retention_rules")
        db.upsert_retention_rule(
            "sender",
            "alice@s.whatsapp.net",
            label="Alice",
            is_group=0,
        )
        sender_messages = db.list_messages(limit=None)
        self.assertEqual(
            {row["whatsapp_message_id"] for row in sender_messages},
            {
                "selected-open",
                "selected-close",
                "other-recent",
                "direct-same-id",
            },
        )

    def test_dashboard_administration_and_ingestion_use_scope_without_login(self):
        self._enable_selected_group()

        dashboard = self.client.get("/dashboard?period=12h")
        administration = self.client.get("/administration")
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(administration.status_code, 200)
        self.assertIn(
            b"Live data filtered by monitored chats/groups/senders",
            dashboard.data,
        )
        self.assertIn(
            b"Live data filtered by monitored chats/groups/senders",
            administration.data,
        )
        self.assertIn(b"Shared Operations", administration.data)

        accepted = self.client.post(
            "/ingest/companion",
            json={
                "source": "baileys",
                "message_id": "accepted-scope-message",
                "chat_id": "selected-group@g.us",
                "chat_name": "Shared Operations",
                "is_group": True,
                "group_id": "selected-group@g.us",
                "sender_id": "new@s.whatsapp.net",
                "message_type": "text",
                "text_body": "Accepted",
                "timestamp": self.now.isoformat(),
            },
        )
        rejected = self.client.post(
            "/ingest/companion",
            json={
                "source": "baileys",
                "message_id": "rejected-scope-message",
                "chat_id": "other-group@g.us",
                "chat_name": "Shared Operations",
                "is_group": True,
                "group_id": "other-group@g.us",
                "sender_id": "new@s.whatsapp.net",
                "message_type": "text",
                "text_body": "Rejected",
                "timestamp": self.now.isoformat(),
            },
        )
        self.assertEqual(accepted.get_json()["status"], "received")
        self.assertEqual(rejected.get_json()["status"], "ignored")
        with db.get_connection() as connection:
            stored = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT whatsapp_message_id
                    FROM messages
                    WHERE whatsapp_message_id LIKE '%scope-message'
                    """
                ).fetchall()
            }
        self.assertEqual(stored, {"accepted-scope-message"})


if __name__ == "__main__":
    unittest.main()
