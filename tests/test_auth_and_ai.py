import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash


os.environ["QUERY_USERNAME"] = "test-user"
os.environ["QUERY_PASSWORD_HASH"] = generate_password_hash("test-password")
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"
os.environ["SESSION_COOKIE_SECURE"] = "0"

from app import app
from src import ai_query, db


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
                "username": "test-user",
                "password": "test-password",
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_health_is_public_but_dashboard_requires_login(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_valid_login_opens_dashboard_and_security_headers_are_set(self):
        self._login()
        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")

    def test_invalid_csrf_blocks_authenticated_post(self):
        self._login()
        response = self.client.post(
            "/machine-rules",
            data={"csrf_token": "wrong", "machine_name": "A", "pattern": "A"},
        )
        self.assertEqual(response.status_code, 400)

    def test_query_page_reports_missing_api_key_without_calling_provider(self):
        self._login()
        response = self.client.get("/query")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"API key required", response.data)

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
                            "text": "לא נמצאו הודעות ב-12 השעות האחרונות.",
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
            result = ai_query.ask_database("סכם את 12 השעות האחרונות")

        self.assertEqual(
            result["tools_used"],
            ["get_operations_summary"],
        )
        self.assertIn("לא נמצאו", result["answer"])

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
