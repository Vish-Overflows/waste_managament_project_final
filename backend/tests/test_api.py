from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class UpgradedApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.temp_dir.name) / "upgraded_stack.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ["SECRET_KEY"] = "test-secret-key"
        os.environ["SECURE_COOKIES"] = "false"
        os.environ["CORS_ORIGINS"] = "http://127.0.0.1:5173"

        from app.main import app

        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        cls.temp_dir.cleanup()

    def login(self, username: str) -> dict:
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "password"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def auth_headers(self, username: str) -> dict[str, str]:
        payload = self.login(username)
        return {"Authorization": f"Bearer {payload['access_token']}"}

    def create_collection(self) -> int:
        response = self.client.post(
            "/api/collections",
            json={
                "housingBlock": "HB 1",
                "roomNumber": "101",
                "collectionDate": "2026-04-28",
            },
            headers=self.auth_headers("staff1"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def test_healthcheck(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_staff_operator_admin_workflow(self) -> None:
        collection_id = self.create_collection()

        pending = self.client.get(
            "/api/collections?status=collected",
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(pending.status_code, 200, pending.text)
        self.assertGreaterEqual(pending.json()["total"], 1)

        processed = self.client.post(
            "/api/processing/waste",
            json={
                "collectionId": collection_id,
                "wasteCategory": "Wet Waste",
                "wasteSubtype": "Food Waste",
                "quantity": 8.5,
            },
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(processed.status_code, 200, processed.text)
        self.assertEqual(processed.json()["collection_id"], collection_id)

        wet_update = self.client.post(
            "/api/processing/wet",
            json={"compostQuantity": 4.25, "notes": "integration test"},
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(wet_update.status_code, 200, wet_update.text)

        dashboard = self.client.get(
            "/api/dashboard/summary",
            headers=self.auth_headers("admin"),
        )
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        labels = {metric["label"] for metric in dashboard.json()["metrics"]}
        self.assertIn("Collections Recorded", labels)
        self.assertIn("Wet Waste", labels)

    def test_operator_can_quantify_public_bin_waste(self) -> None:
        processed = self.client.post(
            "/api/processing/waste",
            json={
                "sourceLocation": "Sports Complex",
                "wasteCategory": "Dry Waste",
                "wasteSubtype": "Paper",
                "quantity": 3.75,
            },
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(processed.status_code, 200, processed.text)
        self.assertIsNone(processed.json()["collection_id"])
        self.assertEqual(processed.json()["housing_block"], "Sports Complex")

        totals = self.client.get(
            "/api/processing/totals",
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(totals.status_code, 200, totals.text)
        self.assertGreaterEqual(totals.json()["total_weight"], 3.75)

    def test_dashboard_requires_admin(self) -> None:
        response = self.client.get(
            "/api/dashboard/summary",
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
