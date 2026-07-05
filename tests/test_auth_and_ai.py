import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.pop("QUERY_USERNAME", None)
os.environ.pop("QUERY_PASSWORD_HASH", None)
os.environ.pop("FLASK_SECRET_KEY", None)
os.environ["SESSION_COOKIE_SECURE"] = "0"

from app import app
from src import ai_query, db, query


AI_PASSWORD = "m" + "or"


class AuthAndAIQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(
            db, "DB_PATH", Path(self.temp_dir.name) / "messages.db"
        )
        self.db_patch.start()
        db.init_db()
        app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = app.test_client()
        os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        self.db_patch.stop()
        self.temp_dir.cleanup()

    def _csrf(self):
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def _login(self):
        self.client.get("/login")
        response = self.client.post(
            "/login",
            data={
                "csrf_token": self._csrf(),
                "username": "qyam2323",
                "password": AI_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/query", response.headers["Location"])

    def test_app_starts_without_authentication_environment(self):
        self.assertTrue(app.secret_key)
        self.assertNotIn("QUERY_USERNAME", os.environ)
        self.assertNotIn("QUERY_PASSWORD_HASH", os.environ)

    def test_normal_dashboard_routes_are_open_without_login(self):
        routes = [
            "/health",
            "/dashboard",
            "/administration",
            "/messages",
            "/api/stats",
            "/api/management",
            "/api/messages",
            "/export/messages.csv",
            "/export/messages.json",
        ]
        for route in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

    def test_administration_write_is_open_but_keeps_csrf_protection(self):
        self.client.get("/administration")
        response = self.client.post(
            "/machine-rules",
            data={
                "csrf_token": self._csrf(),
                "machine_name": "CNC-01",
                "pattern": "CNC-01",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(db.list_machine_rules()), 1)

        invalid = self.client.post(
            "/machine-rules",
            data={"csrf_token": "wrong", "machine_name": "A", "pattern": "A"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_capture_rule_can_be_selected_from_known_group_dropdown(self):
        db.insert_message(
            {
                "source": "baileys",
                "chat_id": "factory-group@g.us",
                "chat_name": "Factory Maintenance",
                "is_group": 1,
                "group_id": "factory-group@g.us",
                "whatsapp_message_id": "known-group-1",
                "sender_phone": "demo-sender",
                "sender_name": "Demo Operator",
                "timestamp": "2026-07-05T08:00:00+00:00",
                "message_type": "text",
                "text_body": "Maintenance update",
            }
        )

        page = self.client.get("/administration")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Factory Maintenance (1)", page.data)
        self.assertIn(b"chat:factory-group@g.us", page.data)

        response = self.client.post(
            "/retention-rules",
            data={
                "csrf_token": self._csrf(),
                "rule_selection": "chat:factory-group@g.us",
            },
        )
        self.assertEqual(response.status_code, 302)
        rules = db.list_retention_rules()
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["rule_type"], "chat")
        self.assertEqual(rules[0]["value"], "factory-group@g.us")
        self.assertEqual(rules[0]["label"], "Factory Maintenance")
        self.assertEqual(rules[0]["is_group"], 1)

    def test_baileys_ingestion_remains_open_without_login(self):
        response = self.client.post(
            "/ingest/companion",
            json={
                "source": "baileys",
                "message_id": "public-ingest-1",
                "chat_id": "demo-chat",
                "sender_id": "demo-sender",
                "timestamp": "2026-07-04T12:00:00+00:00",
                "message_type": "text",
                "text_body": "Open ingestion test",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(db.list_messages()), 1)

    def test_ai_browser_and_api_routes_are_blocked_before_login(self):
        browser_response = self.client.get("/query")
        self.assertEqual(browser_response.status_code, 302)
        self.assertIn("/login", browser_response.headers["Location"])

        api_response = self.client.post(
            "/api/ai/query",
            json={"question": "status"},
        )
        self.assertEqual(api_response.status_code, 401)
        self.assertEqual(
            api_response.get_json()["error"],
            "ai_authentication_required",
        )

    def test_fixed_local_login_opens_ai_mode(self):
        self._login()
        response = self.client.get("/query")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"API key required", response.data)
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")

    def test_ai_api_works_after_login(self):
        self._login()
        os.environ["OPENAI_API_KEY"] = "test-key"
        expected = {"answer": "No production alerts.", "tools_used": []}
        with patch.object(query, "ask_database", return_value=expected):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "status"},
                headers={"X-CSRF-Token": self._csrf()},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), expected)

    def test_readonly_connection_rejects_writes(self):
        with db.get_readonly_connection() as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM messages")

    def test_model_can_only_call_allowlisted_tool_then_return_answer(self):
        os.environ["OPENAI_API_KEY"] = "test-key"
        first_response = {
            "id": "resp_1",
            "output": [
                {
                    "type": "function_call",
                    "name": "get_operations_summary",
                    "arguments": '{"period":"12h"}',
                    "call_id": "call_1",
                }
            ],
        }
        second_response = {
            "id": "resp_2",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "No messages were found in the last 12 hours.",
                        }
                    ],
                }
            ],
        }

        with patch.object(
            ai_query,
            "_responses_request",
            side_effect=[first_response, second_response],
        ):
            result = ai_query.ask_database("Summarize the last 12 hours")

        self.assertEqual(result["tools_used"], ["get_operations_summary"])
        self.assertIn("No messages", result["answer"])

    def test_unsupported_tool_is_rejected(self):
        with self.assertRaises(ai_query.AIQueryError):
            ai_query.execute_tool("execute_sql", {"period": "12h"})

    def test_message_redaction_removes_phone_and_email(self):
        redacted = ai_query._redact_text(
            "Call +972 50 123 4567 or send mail to operator@example.com"
        )
        self.assertNotIn("123 4567", redacted)
        self.assertNotIn("operator@example.com", redacted)
        self.assertIn("[phone]", redacted)
        self.assertIn("[email]", redacted)


if __name__ == "__main__":
    unittest.main()
