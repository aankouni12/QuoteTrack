import sqlite3
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as quotetrack

SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"


class FollowUpViewTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = Path(directory.name) / "quotetrack.db"
        for override in (
            patch.object(quotetrack, "DATABASE", database),
            patch.object(quotetrack, "today", lambda: date(2026, 11, 20)),
        ):
            override.start()
            self.addCleanup(override.stop)
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(SCHEMA.read_text())
            connection.execute(
                "INSERT INTO owners (username, password_hash) VALUES (?, ?)",
                ("owner", generate_password_hash("correct-password")),
            )
            connection.commit()
        self.client = quotetrack.app.test_client()
        self.client.post("/login", data={"username": "owner", "password": "correct-password"})

    def add_request(self, name, follow_up_date, status="Contacted"):
        email = name.lower().replace(" ", ".") + "@example.test"
        self.client.post("/request", data={
            "name": name,
            "email": email,
            "service_type": "Cleaning",
            "description": "Please clean the meeting room.",
        })
        with closing(quotetrack.get_db()) as connection, connection:
            request_id = connection.execute("SELECT MAX(id) FROM requests").fetchone()[0]
            connection.execute(
                "UPDATE requests SET status = ?, follow_up_date = ? WHERE id = ?",
                (status, follow_up_date, request_id),
            )

    def due_section(self):
        page = self.client.get("/dashboard").get_data(as_text=True)
        return page.split("<h2>All requests</h2>")[0]

    def test_shows_overdue_and_today_but_not_future(self):
        self.add_request("Past Customer", "2026-11-18")
        self.add_request("Today Customer", "2026-11-20")
        self.add_request("Future Customer", "2026-11-25")
        section = self.due_section()
        self.assertIn("Past Customer", section)
        self.assertIn("Today Customer", section)
        self.assertNotIn("Future Customer", section)

    def test_labels_overdue_and_today(self):
        self.add_request("Past Customer", "2026-11-18")
        self.add_request("Today Customer", "2026-11-20")
        section = self.due_section()
        self.assertIn("Overdue", section)
        self.assertIn("Today</span>", section)

    def test_oldest_follow_up_is_listed_first(self):
        self.add_request("Newer Customer", "2026-11-19")
        self.add_request("Older Customer", "2026-11-10")
        section = self.due_section()
        self.assertLess(section.index("Older Customer"), section.index("Newer Customer"))

    def test_closed_requests_are_not_listed(self):
        self.add_request("Won Customer", "2026-11-18", status="Won")
        self.add_request("Lost Customer", "2026-11-18", status="Lost")
        section = self.due_section()
        self.assertNotIn("Won Customer", section)
        self.assertNotIn("Lost Customer", section)
        self.assertIn("No customers need to be contacted today.", section)

    def test_requests_without_a_date_are_not_listed(self):
        self.add_request("No Date Customer", None, status="New")
        self.assertNotIn("No Date Customer", self.due_section())

    def test_section_ignores_search_filters(self):
        self.add_request("Past Customer", "2026-11-18")
        page = self.client.get("/dashboard?q=nobody").get_data(as_text=True)
        due, rest = page.split("<h2>All requests</h2>")
        self.assertIn("Past Customer", due)
        self.assertIn("No requests found.", rest)


if __name__ == "__main__":
    unittest.main()