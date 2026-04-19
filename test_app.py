from __future__ import annotations

import http.cookiejar
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from server import create_server


class WasteAppIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        base_dir = Path(__file__).resolve().parent
        db_path = Path(cls.temp_dir.name) / "test.db"
        cls.server = create_server("127.0.0.1", 0, base_dir=base_dir, db_path=db_path)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp_dir.cleanup()

    def build_opener(self) -> urllib.request.OpenerDirector:
        jar = http.cookiejar.CookieJar()
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def api_request(
        self,
        opener: urllib.request.OpenerDirector,
        path: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
    ) -> tuple[int, dict]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with opener.open(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def login(self, opener: urllib.request.OpenerDirector, username: str) -> tuple[int, dict]:
        return self.api_request(
            opener,
            "/api/login",
            method="POST",
            payload={"username": username, "password": "password"},
        )

    def test_worker_can_login_and_create_dry_entry(self) -> None:
        opener = self.build_opener()
        status, payload = self.login(opener, "worker1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["role"], "worker")

        status, payload = self.api_request(
            opener,
            "/api/entries",
            method="POST",
            payload={
                "wasteCategory": "Dry Waste",
                "housingBlock": "AB1",
                "roomNumber": "101",
                "wasteSubtype": "Paper",
                "sourceLocation": "Academic Area",
                "quantity": "2.5",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["message"], "Waste entry saved successfully.")

    def test_hazardous_entry_requires_date_range(self) -> None:
        opener = self.build_opener()
        self.login(opener, "worker2")

        status, payload = self.api_request(
            opener,
            "/api/entries",
            method="POST",
            payload={
                "wasteCategory": "Hazardous Waste",
                "wasteSubtype": "Lab Waste",
                "housingBlock": "AB2",
                "roomNumber": "102",
                "quantity": "1.2",
            },
        )
        self.assertEqual(status, 400)
        self.assertIn("required for hazardous waste", payload["error"])

    def test_wet_processing_update_can_derive_biogas_from_total(self) -> None:
        opener = self.build_opener()
        self.login(opener, "worker1")

        self.api_request(
            opener,
            "/api/entries",
            method="POST",
            payload={
                "wasteCategory": "Wet Waste",
                "housingBlock": "AB1",
                "roomNumber": "101",
                "sourceLocation": "Food Outlets",
                "quantity": "10",
            },
        )
        self.api_request(
            opener,
            "/api/entries",
            method="POST",
            payload={
                "wasteCategory": "Wet Waste",
                "housingBlock": "AB2",
                "roomNumber": "102",
                "sourceLocation": "Academic Area",
                "quantity": "5",
            },
        )

        status, payload = self.api_request(
            opener,
            "/api/wet-processing-updates",
            method="POST",
            payload={"compostQuantity": "9"},
        )
        self.assertEqual(status, 201)
        self.assertIn("saved successfully", payload["message"])

        status, payload = self.api_request(opener, "/api/wet-processing-status")
        self.assertEqual(status, 200)
        self.assertEqual(payload["totalWetCollected"], 15.0)
        self.assertEqual(payload["latestUpdate"]["compostQuantity"], 9.0)
        self.assertEqual(payload["latestUpdate"]["biogasQuantity"], 6.0)

    def test_dashboard_requires_admin(self) -> None:
        worker_opener = self.build_opener()
        self.login(worker_opener, "worker1")
        status, _ = self.api_request(worker_opener, "/api/dashboard")
        self.assertEqual(status, 403)

        admin_opener = self.build_opener()
        self.login(admin_opener, "admin")
        status, payload = self.api_request(admin_opener, "/api/dashboard")
        self.assertEqual(status, 200)
        self.assertIn("metrics", payload)
        self.assertIn("recentEntries", payload)
        self.assertIn("wetProcessing", payload)


if __name__ == "__main__":
    unittest.main()
