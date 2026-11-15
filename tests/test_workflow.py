import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app as quotetrack

SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"


class RequestWorkflowTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database = Path(directory.name) / "quotetrack.db"
        database_override = patch.object(quotetrack, "DATABASE", database)
        database_override.start()
        self.addCleanup(database_override.stop)
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(SCHEMA.read_text())
        self.client = quotetrack.app.test_client()

    def submit_request(self, **overrides):
        details = {
            "name": "Sample Customer",
            "email": "customer@example.test",
            "service_type": "Cleaning",
            "description": "Please clean the meeting room.",
        }
        return self.client.post("/request", data=details | overrides, follow_redirects=True)

    def request_record(self):
        with closing(quotetrack.get_db()) as connection:
            return tuple(connection.execute(
                "SELECT status, notes, follow_up_date FROM requests WHERE id = 1"
            ).fetchone())

    def test_customer_submission_through_follow_up_and_dashboard(self):
        self.assertIn(b"Request a Service", self.client.get("/", follow_redirects=True).data)
        invalid = self.submit_request(email="invalid")
        self.assertEqual(invalid.status_code, 400)
        self.assertIn(b"No requests found.", self.client.get("/dashboard").data)

        self.assertIn(b"Request received", self.submit_request().data)
        dashboard = self.client.get("/dashboard?q=Sample&status=New")
        self.assertIn(b'Sample Customer', dashboard.data)
        self.assertIn(b'href="/requests/1"', dashboard.data)
        detail = self.client.get("/requests/1")
        self.assertIn(b'Please clean the meeting room.', detail.data)

        updated = self.client.post(
            "/requests/1",
            data={"status": "Contacted", "notes": "Call back", "follow_up_date": "2026-11-20"},
            follow_redirects=True,
        )
        self.assertIn(b"Changes saved.", updated.data)
        self.assertIn(b'value="2026-11-20"', updated.data)
        self.assertEqual(self.request_record(), ("Contacted", "Call back", "2026-11-20"))
        filtered = self.client.get("/dashboard?q=customer%40example.test&status=Contacted")
        self.assertIn(b'<time datetime="2026-11-20">2026-11-20</time>', filtered.data)
        self.assertIn(b"No requests found.", self.client.get("/dashboard?status=New").data)

        self.client.post("/requests/1", data={
            "status": "Contacted", "notes": "Move call", "follow_up_date": "2026-11-23",
        })
        self.assertEqual(self.request_record(), ("Contacted", "Move call", "2026-11-23"))

        self.client.post("/requests/1", data={
            "status": "Won", "notes": "Confirmed", "follow_up_date": "",
        })
        self.assertEqual(self.request_record(), ("Won", "Confirmed", None))
        self.assertNotIn(b"2026-11-23", self.client.get("/dashboard").data)

    def test_invalid_date_preserves_saved_record_and_retains_form_values(self):
        self.submit_request()
        self.client.post("/requests/1", data={
            "status": "Contacted", "notes": "Current note", "follow_up_date": "2026-11-20",
        })
        for invalid_date in ("2026-02-30", "20261120", "2026-W47-5"):
            with self.subTest(invalid_date=invalid_date):
                response = self.client.post("/requests/1", data={
                    "status": "Won", "notes": "Keep this edit", "follow_up_date": invalid_date,
                })
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"Enter a valid follow-up date", response.data)
                self.assertIn(b'aria-invalid="true"', response.data)
                self.assertIn(b"Keep this edit", response.data)
                self.assertEqual(self.request_record(), ("Contacted", "Current note", "2026-11-20"))

    def test_update_without_date_preserves_date_on_an_existing_request(self):
        self.submit_request()
        self.client.post("/requests/1", data={
            "status": "Contacted", "notes": "", "follow_up_date": "2026-11-20",
        })
        previous_form = self.client.post(
            "/requests/1", data={"status": "Won", "notes": "Confirmed"},
        )
        self.assertEqual(previous_form.status_code, 302)
        self.assertEqual(self.request_record(), ("Won", "Confirmed", "2026-11-20"))


if __name__ == "__main__":
    unittest.main()
