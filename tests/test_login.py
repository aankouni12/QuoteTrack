import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as quotetrack

SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"


class OwnerLoginTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = Path(directory.name) / "quotetrack.db"
        database_override = patch.object(quotetrack, "DATABASE", database)
        database_override.start()
        self.addCleanup(database_override.stop)
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(SCHEMA.read_text())
            connection.execute(
                "INSERT INTO owners (username, password_hash) VALUES (?, ?)",
                ("owner", generate_password_hash("correct-password")),
            )
            connection.commit()
        self.client = quotetrack.app.test_client()

    def log_in(self, password="correct-password", **extra):
        return self.client.post(
            "/login", data={"username": "owner", "password": password, **extra}
        )

    def test_owner_pages_redirect_to_login_when_logged_out(self):
        for path in ("/dashboard", "/requests/1"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login", response.headers["Location"])

    def test_updates_are_blocked_when_logged_out(self):
        response = self.client.post("/requests/1", data={"status": "Won"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_customer_form_stays_public(self):
        self.assertEqual(self.client.get("/request").status_code, 200)

    def test_wrong_password_is_rejected(self):
        response = self.log_in(password="wrong-password")
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Invalid username or password.", response.data)
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_unknown_username_gets_the_same_message(self):
        response = self.client.post(
            "/login", data={"username": "nobody", "password": "correct-password"}
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Invalid username or password.", response.data)

    def test_correct_login_opens_dashboard(self):
        response = self.log_in()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/dashboard"))
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Signed in as owner", dashboard.data)

    def test_login_returns_to_the_page_that_was_requested(self):
        response = self.log_in(next="/requests/1")
        self.assertTrue(response.headers["Location"].endswith("/requests/1"))

    def test_login_ignores_redirects_to_other_sites(self):
        response = self.log_in(next="//evil.example.com")
        self.assertTrue(response.headers["Location"].endswith("/dashboard"))

    def test_logout_locks_the_dashboard_again(self):
        self.log_in()
        self.client.post("/logout")
        self.assertEqual(self.client.get("/dashboard").status_code, 302)


if __name__ == "__main__":
    unittest.main()