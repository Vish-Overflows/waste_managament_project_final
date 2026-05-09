from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.time_utils import campus_today


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

    def password_for(self, username: str) -> str:
        if username.startswith("staff"):
            return ""
        if username == "operator1":
            return "op_key"
        if username == "admin":
            return "admins_key"
        return ""

    def login(self, username: str, password: str | None = None) -> dict:
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": self.password_for(username) if password is None else password},
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
                "housingBlock": "1",
                "roomNumber": "101",
                "collectionDate": "2026-04-28",
            },
            headers=self.auth_headers("staff1"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["collection_date"], campus_today().isoformat())
        self.assertEqual(response.json()["housing_block"], "1")
        return response.json()["id"]

    def test_healthcheck(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("database", payload)
        self.assertIn("persistent", payload)

    def test_login_rules(self) -> None:
        staff = self.login("staff3", "")
        self.assertEqual(staff["user"]["role"], "staff")

        operator_wrong = self.client.post(
            "/api/auth/login",
            json={"username": "operator1", "password": ""},
        )
        self.assertEqual(operator_wrong.status_code, 401)

        admin_wrong = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "op_key"},
        )
        self.assertEqual(admin_wrong.status_code, 401)

        operator = self.login("operator1", "op_key")
        self.assertEqual(operator["user"]["role"], "operator")
        admin = self.login("admin", "admins_key")
        self.assertEqual(admin["user"]["role"], "admin")

    def test_staff_block_number_validation(self) -> None:
        invalid = self.client.post(
            "/api/collections",
            json={
                "housingBlock": "35",
                "roomNumber": "202",
                "collectionDate": "2026-04-28",
            },
            headers=self.auth_headers("staff1"),
        )
        self.assertEqual(invalid.status_code, 422)

        valid = self.client.post(
            "/api/collections",
            json={
                "housingBlock": "3",
                "roomNumber": "101",
                "collectionDate": "2026-04-28",
            },
            headers=self.auth_headers("staff1"),
        )
        self.assertEqual(valid.status_code, 200, valid.text)
        self.assertEqual(valid.json()["housing_block"], "3")
        self.assertEqual(valid.json()["room_number"], "101")

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

        excessive_wet_update = self.client.post(
            "/api/processing/wet",
            json={"compostQuantity": 9999},
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(excessive_wet_update.status_code, 400)

        wet_intake = self.client.post(
            "/api/processing/wet-intake",
            json={
                "wasteSubtype": "Kitchen Waste",
                "quantity": 6,
                "compostQuantity": 4,
                "biogasQuantity": 2,
            },
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(wet_intake.status_code, 200, wet_intake.text)

        missing_machine_allocation = self.client.post(
            "/api/processing/wet-intake",
            json={
                "wasteSubtype": "Food Waste",
                "quantity": 3,
                "compostQuantity": 0,
                "biogasQuantity": 0,
            },
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(missing_machine_allocation.status_code, 400)

        compost_distribution = self.client.post(
            "/api/processing/output-distributions",
            json={
                "streamType": "Compost",
                "entries": [
                    {"recipient": "workers", "quantity": 2},
                    {"recipient": "gardeners", "quantity": 3},
                ]
            },
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(compost_distribution.status_code, 200, compost_distribution.text)

        compost_missing_recipient = self.client.post(
            "/api/processing/output-distributions",
            json={"streamType": "Compost", "entries": [{"quantity": 1}]},
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(compost_missing_recipient.status_code, 400)

        biogas_distribution = self.client.post(
            "/api/processing/output-distributions",
            json={
                "streamType": "Biogas",
                "entries": [
                    {"quantity": 1.5},
                ],
            },
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(biogas_distribution.status_code, 200, biogas_distribution.text)

        large_biogas_distribution = self.client.post(
            "/api/processing/output-distributions",
            json={"streamType": "Biogas", "entries": [{"quantity": 9999}]},
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(large_biogas_distribution.status_code, 200, large_biogas_distribution.text)

        dashboard = self.client.get(
            "/api/dashboard/summary",
            headers=self.auth_headers("admin"),
        )
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        labels = {metric["label"] for metric in dashboard.json()["metrics"]}
        self.assertIn("Collections Recorded", labels)
        self.assertIn("Staff Collection Records", labels)
        self.assertIn("Wet Waste", labels)

        report = self.client.get(
            "/api/dashboard/export/weekly",
            headers=self.auth_headers("admin"),
        )
        self.assertEqual(report.status_code, 200, report.text)
        self.assertIn("text/csv", report.headers["content-type"])
        self.assertIn("Individual Staff Collection Entries", report.text)
        self.assertIn("Individual Operator Entries", report.text)
        self.assertIn("Dry Waste Source Patterns", report.text)
        self.assertIn("Wet Processing Updates", report.text)
        self.assertIn("Output Distribution Entries", report.text)
        self.assertIn("Biogas distributed kg", report.text)

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

        sources = self.client.get(
            "/api/dashboard/blocks",
            headers=self.auth_headers("admin"),
        )
        self.assertEqual(sources.status_code, 200, sources.text)
        source_weights = {item["housing_block"]: item["processed_weight"] for item in sources.json()}
        self.assertGreaterEqual(source_weights["Sports Complex"], 3.75)

        wet = self.client.post(
            "/api/processing/waste",
            json={
                "wasteCategory": "Wet Waste",
                "wasteSubtype": "Kitchen Waste",
                "quantity": 2.5,
            },
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(wet.status_code, 200, wet.text)
        self.assertEqual(wet.json()["housing_block"], "Wet Waste Stream")

        updated_sources = self.client.get(
            "/api/dashboard/blocks",
            headers=self.auth_headers("admin"),
        )
        self.assertEqual(updated_sources.status_code, 200, updated_sources.text)
        source_names = {item["housing_block"] for item in updated_sources.json()}
        self.assertNotIn("Wet Waste Stream", source_names)

    def test_dashboard_requires_admin(self) -> None:
        response = self.client.get(
            "/api/dashboard/summary",
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(response.status_code, 403)

    def test_z_admin_can_clear_operational_data(self) -> None:
        self.create_collection()
        processed = self.client.post(
            "/api/processing/waste",
            json={
                "sourceLocation": "Research Park",
                "wasteCategory": "Dry Waste",
                "wasteSubtype": "Paper",
                "quantity": 1,
            },
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(processed.status_code, 200, processed.text)

        blocked = self.client.delete(
            "/api/dashboard/data/operational",
            headers=self.auth_headers("operator1"),
        )
        self.assertEqual(blocked.status_code, 403)

        cleared = self.client.delete(
            "/api/dashboard/data/operational",
            headers=self.auth_headers("admin"),
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertGreaterEqual(cleared.json()["housing_collections"], 1)
        self.assertGreaterEqual(cleared.json()["waste_entries"], 1)

        summary = self.client.get(
            "/api/dashboard/summary",
            headers=self.auth_headers("admin"),
        )
        self.assertEqual(summary.status_code, 200, summary.text)
        metrics = {metric["label"]: metric["value"] for metric in summary.json()["metrics"]}
        self.assertEqual(metrics["Collections Recorded"], 0)
        self.assertEqual(metrics["Waste Processed"], 0)


if __name__ == "__main__":
    unittest.main()
