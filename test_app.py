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

    def test_staff_can_mark_housing_collection(self) -> None:
        opener = self.build_opener()
        status, payload = self.login(opener, "staff1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["role"], "staff")

        status, payload = self.api_request(
            opener,
            "/api/staff-collections",
            method="POST",
            payload={
                "housingBlock": "HB 1",
                "roomNumber": "101",
                "collectionDate": "2026-04-20",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["message"], "Housing collection marked successfully.")

    def test_operator_can_create_segregation_entry_from_staff_collection(self) -> None:
        staff = self.build_opener()
        self.login(staff, "staff1")
        self.api_request(
            staff,
            "/api/staff-collections",
            method="POST",
            payload={
                "housingBlock": "HB 2",
                "roomNumber": "102",
                "collectionDate": "2026-04-20",
            },
        )

        operator = self.build_opener()
        status, payload = self.login(operator, "operator1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["role"], "operator")

        status, payload = self.api_request(operator, "/api/operator/collections")
        self.assertEqual(status, 200)
        collection_id = payload["collections"][0]["id"]

        status, payload = self.api_request(
            operator,
            "/api/processing-entries",
            method="POST",
            payload={
                "collectionId": collection_id,
                "wasteCategory": "Dry Waste",
                "wasteSubtype": "Paper",
                "quantity": "2.5",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["message"], "Segregation entry saved successfully.")

    def test_operator_compost_update_derives_biogas(self) -> None:
        staff = self.build_opener()
        self.login(staff, "staff2")
        self.api_request(
            staff,
            "/api/staff-collections",
            method="POST",
            payload={
                "housingBlock": "HB 3",
                "roomNumber": "103",
                "collectionDate": "2026-04-20",
            },
        )

        operator = self.build_opener()
        self.login(operator, "operator1")
        status, payload = self.api_request(operator, "/api/operator/collections")
        collection_id = payload["collections"][0]["id"]

        self.api_request(
            operator,
            "/api/processing-entries",
            method="POST",
            payload={
                "collectionId": collection_id,
                "wasteCategory": "Wet Waste",
                "wasteSubtype": "Food Waste",
                "quantity": "10",
            },
        )
        self.api_request(
            operator,
            "/api/processing-entries",
            method="POST",
            payload={
                "collectionId": collection_id,
                "wasteCategory": "Wet Waste",
                "wasteSubtype": "Mixed Organic Waste",
                "quantity": "5",
            },
        )

        status, payload = self.api_request(
            operator,
            "/api/wet-processing-updates",
            method="POST",
            payload={"compostQuantity": "9"},
        )
        self.assertEqual(status, 201)
        self.assertIn("saved successfully", payload["message"])

        status, payload = self.api_request(operator, "/api/wet-processing-status")
        self.assertEqual(status, 200)
        self.assertEqual(payload["totalWetProcessed"], 15.0)
        self.assertEqual(payload["latestUpdate"]["compostQuantity"], 9.0)
        self.assertEqual(payload["latestUpdate"]["biogasQuantity"], 6.0)

    def test_admin_dashboard_requires_admin(self) -> None:
        operator = self.build_opener()
        self.login(operator, "operator1")
        status, _ = self.api_request(operator, "/api/dashboard")
        self.assertEqual(status, 403)

        admin = self.build_opener()
        self.login(admin, "admin")
        status, payload = self.api_request(admin, "/api/dashboard")
        self.assertEqual(status, 200)
        self.assertIn("metrics", payload)
        self.assertIn("recentCollections", payload)
        self.assertIn("recentProcessingEntries", payload)


if __name__ == "__main__":
    unittest.main()
