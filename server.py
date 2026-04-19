from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BLOCKS = ["AB1", "AB2", "AB3", "AB4", "AB5", "AB6", "AB7"]
COMMON_ROOMS = ["101", "102", "103", "201", "202", "203"]
ROOMS_BY_BLOCK = {block: COMMON_ROOMS[:] for block in BLOCKS}
WASTE_CATEGORIES = ["Wet Waste", "Dry Waste", "Hazardous Waste"]
DRY_WASTE_TYPES = [
    "Plastic Bottles (Recyclable)",
    "Plastic Boxes",
    "Glass",
    "Broken Glass / Ceramics",
    "Footwear",
    "Textiles",
    "Tin Cans",
    "LDPE",
    "HDPE",
    "Paper",
    "Cardboard",
]
DRY_WASTE_LOCATIONS = [
    "Guest House",
    "Hostel",
    "Academic Area",
    "Administrative Area",
    "Sports Complex",
    "Food Court",
]
WET_WASTE_LOCATIONS = [
    "Food Outlets",
    "Academic Area",
    "Hostel Mess",
    "Guest House",
    "Residential Area",
]
HAZARDOUS_WASTE_TYPES = ["Lab Waste", "Biomedical Waste"]
USERS = {
    "worker1": {"password": "password", "role": "worker"},
    "worker2": {"password": "password", "role": "worker"},
    "admin": {"password": "password", "role": "admin"},
}
SESSION_COOKIE = "waste_app_session"


@dataclass
class SessionStore:
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def create(self, username: str, role: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.sessions[token] = {
                "username": username,
                "employee_id": username,
                "role": role,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        return token

    def get(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self.lock:
            return self.sessions.get(token)

    def delete(self, token: str | None) -> None:
        if not token:
            return
        with self.lock:
            self.sessions.pop(token, None)


@dataclass
class AppConfig:
    static_dir: Path
    db_path: Path
    host: str
    port: int
    session_store: SessionStore = field(default_factory=SessionStore)


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS waste_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                waste_category TEXT NOT NULL,
                waste_subtype TEXT,
                source_location TEXT,
                housing_block TEXT NOT NULL,
                room_number TEXT NOT NULL,
                quantity REAL NOT NULL,
                start_date TEXT,
                end_date TEXT,
                entry_kind TEXT NOT NULL DEFAULT 'collection',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS wet_processing_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                compost_quantity REAL NOT NULL,
                biogas_quantity REAL NOT NULL,
                total_wet_reference REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        migrate_waste_entries_schema(connection)
        connection.commit()


def ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    existing = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def migrate_waste_entries_schema(connection: sqlite3.Connection) -> None:
    ensure_column(connection, "waste_entries", "source_location", "TEXT")
    ensure_column(connection, "waste_entries", "entry_kind", "TEXT NOT NULL DEFAULT 'collection'")

    columns = {
        row[1]: {
            "type": row[2],
            "notnull": row[3],
        }
        for row in connection.execute("PRAGMA table_info(waste_entries)").fetchall()
    }

    needs_rebuild = (
        "waste_subtype" in columns and columns["waste_subtype"]["notnull"] == 1
    ) or (
        "housing_block" in columns and columns["housing_block"]["notnull"] == 0
    ) or (
        "room_number" in columns and columns["room_number"]["notnull"] == 0
    )

    if not needs_rebuild:
        return

    connection.execute(
        """
        CREATE TABLE waste_entries_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            waste_category TEXT NOT NULL,
            waste_subtype TEXT,
            source_location TEXT,
            housing_block TEXT NOT NULL,
            room_number TEXT NOT NULL,
            quantity REAL NOT NULL,
            start_date TEXT,
            end_date TEXT,
            entry_kind TEXT NOT NULL DEFAULT 'collection',
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO waste_entries_v2 (
            id,
            employee_id,
            waste_category,
            waste_subtype,
            source_location,
            housing_block,
            room_number,
            quantity,
            start_date,
            end_date,
            entry_kind,
            created_at
        )
        SELECT
            id,
            employee_id,
            waste_category,
            NULLIF(waste_subtype, ''),
            source_location,
            housing_block,
            room_number,
            quantity,
            start_date,
            end_date,
            COALESCE(entry_kind, 'collection'),
            created_at
        FROM waste_entries
        """
    )
    connection.execute("DROP TABLE waste_entries")
    connection.execute("ALTER TABLE waste_entries_v2 RENAME TO waste_entries")


def create_server(host: str, port: int, base_dir: Path | None = None, db_path: Path | None = None) -> ThreadingHTTPServer:
    root = (base_dir or Path(__file__).resolve().parent).resolve()
    database_path = (db_path or root / "data" / "waste_management.db").resolve()
    static_dir = (root / "static").resolve()
    init_db(database_path)

    config = AppConfig(
        static_dir=static_dir,
        db_path=database_path,
        host=host,
        port=port,
    )
    handler = build_handler(config)
    server = ThreadingHTTPServer((host, port), handler)
    server.config = config  # type: ignore[attr-defined]
    return server


def build_handler(config: AppConfig) -> type[BaseHTTPRequestHandler]:
    class WasteAppHandler(BaseHTTPRequestHandler):
        server_version = "WasteApp/2.0"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                self.serve_static("index.html")
                return
            if path == "/styles.css":
                self.serve_static("styles.css")
                return
            if path == "/app.js":
                self.serve_static("app.js")
                return
            if path == "/api/config":
                self.send_json(
                    {
                        "wasteCategories": WASTE_CATEGORIES,
                        "dryWasteTypes": DRY_WASTE_TYPES,
                        "dryWasteLocations": DRY_WASTE_LOCATIONS,
                        "wetWasteLocations": WET_WASTE_LOCATIONS,
                        "hazardousWasteTypes": HAZARDOUS_WASTE_TYPES,
                        "blocks": BLOCKS,
                        "roomsByBlock": ROOMS_BY_BLOCK,
                        "demoUsers": list(USERS.keys()),
                    }
                )
                return
            if path == "/api/session":
                session = self.require_session(optional=True)
                if session is None:
                    self.send_json({"authenticated": False})
                else:
                    self.send_json(
                        {
                            "authenticated": True,
                            "user": {
                                "username": session["username"],
                                "employee_id": session["employee_id"],
                                "role": session["role"],
                            },
                        }
                    )
                return
            if path == "/api/dashboard":
                session = self.require_session()
                if not session:
                    return
                if session["role"] != "admin":
                    self.send_error_json(HTTPStatus.FORBIDDEN, "Admin access required.")
                    return
                self.send_json(self.load_dashboard())
                return
            if path == "/api/wet-processing-status":
                session = self.require_session()
                if not session:
                    return
                self.send_json(self.load_wet_processing_status())
                return
            self.send_error_json(HTTPStatus.NOT_FOUND, "Resource not found.")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/login":
                payload = self.read_json_body()
                if payload is None:
                    return
                username = str(payload.get("username", "")).strip()
                password = str(payload.get("password", "")).strip()
                user = USERS.get(username)
                if not user or user["password"] != password:
                    self.send_error_json(HTTPStatus.UNAUTHORIZED, "Invalid username or password.")
                    return
                token = config.session_store.create(username, user["role"])
                self.send_json(
                    {
                        "message": "Login successful.",
                        "user": {
                            "username": username,
                            "employee_id": username,
                            "role": user["role"],
                        },
                    },
                    cookie=f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax",
                )
                return
            if path == "/api/logout":
                session_token = self.get_session_token()
                config.session_store.delete(session_token)
                self.send_json(
                    {"message": "Logged out."},
                    cookie=f"{SESSION_COOKIE}=deleted; HttpOnly; Path=/; Max-Age=0; SameSite=Lax",
                )
                return
            if path == "/api/entries":
                session = self.require_session()
                if not session:
                    return
                payload = self.read_json_body()
                if payload is None:
                    return
                validation_error, entry = self.validate_collection_entry(payload, session)
                if validation_error:
                    self.send_error_json(HTTPStatus.BAD_REQUEST, validation_error)
                    return
                try:
                    self.insert_entry(entry)
                except sqlite3.IntegrityError:
                    self.send_error_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        "Entry could not be saved because the stored database schema does not match the form data.",
                    )
                    return
                self.send_json({"message": "Waste entry saved successfully."}, status=HTTPStatus.CREATED)
                return
            if path == "/api/wet-processing-updates":
                session = self.require_session()
                if not session:
                    return
                payload = self.read_json_body()
                if payload is None:
                    return
                validation_error, update = self.validate_wet_processing_update(payload, session)
                if validation_error:
                    self.send_error_json(HTTPStatus.BAD_REQUEST, validation_error)
                    return
                self.insert_wet_processing_update(update)
                self.send_json(
                    {"message": "Wet waste processing update saved successfully."},
                    status=HTTPStatus.CREATED,
                )
                return
            self.send_error_json(HTTPStatus.NOT_FOUND, "Resource not found.")

        def log_message(self, format: str, *args: Any) -> None:
            print(
                "%s - - [%s] %s"
                % (self.address_string(), self.log_date_time_string(), format % args)
            )

        def serve_static(self, filename: str) -> None:
            file_path = (config.static_dir / filename).resolve()
            if not str(file_path).startswith(str(config.static_dir)):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Forbidden.")
                return
            if not file_path.exists():
                self.send_error_json(HTTPStatus.NOT_FOUND, "Static asset not found.")
                return
            content_type, _ = mimetypes.guess_type(file_path.name)
            body = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def get_session_token(self) -> str | None:
            raw_cookie = self.headers.get("Cookie")
            if not raw_cookie:
                return None
            cookie = SimpleCookie()
            cookie.load(raw_cookie)
            morsel = cookie.get(SESSION_COOKIE)
            return morsel.value if morsel else None

        def require_session(self, optional: bool = False) -> dict[str, Any] | None:
            token = self.get_session_token()
            session = config.session_store.get(token)
            if session:
                return session
            if optional:
                return None
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Authentication required.")
            return None

        def read_json_body(self) -> dict[str, Any] | None:
            content_length = self.headers.get("Content-Length")
            if not content_length:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Request body is required.")
                return None
            try:
                raw_body = self.rfile.read(int(content_length))
                return json.loads(raw_body.decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid JSON body.")
                return None

        def parse_positive_number(self, value: Any, field_label: str) -> tuple[str | None, float | None]:
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                return f"Enter a valid {field_label}.", None
            if parsed <= 0:
                return f"{field_label.capitalize()} must be a positive number.", None
            return None, parsed

        def validate_collection_entry(
            self, payload: dict[str, Any], session: dict[str, Any]
        ) -> tuple[str | None, dict[str, Any] | None]:
            category = str(payload.get("wasteCategory", "")).strip()
            subtype = str(payload.get("wasteSubtype", "")).strip() or None
            source_location = str(payload.get("sourceLocation", "")).strip() or None
            block = str(payload.get("housingBlock", "")).strip() or None
            room = str(payload.get("roomNumber", "")).strip() or None
            start_date = str(payload.get("startDate", "")).strip() or None
            end_date = str(payload.get("endDate", "")).strip() or None

            if category not in WASTE_CATEGORIES:
                return "Select a valid waste category.", None

            quantity_error, quantity = self.parse_positive_number(payload.get("quantity"), "waste quantity")
            if quantity_error:
                return quantity_error, None

            if block not in BLOCKS:
                return "Select a valid academic block.", None
            valid_rooms = ROOMS_BY_BLOCK.get(block, [])
            if room not in valid_rooms:
                return "Select a valid room number.", None

            if category == "Dry Waste":
                if subtype not in DRY_WASTE_TYPES:
                    return "Select a valid dry waste type.", None
                if source_location not in DRY_WASTE_LOCATIONS:
                    return "Select a valid dry waste location.", None
                start_date = None
                end_date = None
            elif category == "Wet Waste":
                if source_location not in WET_WASTE_LOCATIONS:
                    return "Select a valid wet waste location.", None
                subtype = None
                start_date = None
                end_date = None
            elif category == "Hazardous Waste":
                if subtype not in HAZARDOUS_WASTE_TYPES:
                    return "Select a valid hazardous waste type.", None
                if not start_date or not end_date:
                    return "Start date and end date are required for hazardous waste.", None
                try:
                    start = date.fromisoformat(start_date)
                    end = date.fromisoformat(end_date)
                except ValueError:
                    return "Enter valid hazardous waste dates.", None
                if end < start:
                    return "End date cannot be earlier than start date.", None
                source_location = None

            return (
                None,
                {
                    "employee_id": session["employee_id"],
                    "waste_category": category,
                    "waste_subtype": subtype,
                    "source_location": source_location,
                    "housing_block": block,
                    "room_number": room,
                    "quantity": quantity,
                    "start_date": start_date,
                    "end_date": end_date,
                    "entry_kind": "collection",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )

        def validate_wet_processing_update(
            self, payload: dict[str, Any], session: dict[str, Any]
        ) -> tuple[str | None, dict[str, Any] | None]:
            with sqlite3.connect(config.db_path) as connection:
                total_wet = total_wet_collected(connection)

            if total_wet <= 0:
                return "No wet waste has been logged yet, so a processing update cannot be saved.", None

            compost_raw = payload.get("compostQuantity")
            biogas_raw = payload.get("biogasQuantity")

            compost = parse_optional_float(compost_raw)
            biogas = parse_optional_float(biogas_raw)

            if compost is None and biogas is None:
                return "Enter compost quantity, biogas quantity, or both.", None
            if compost is not None and compost < 0:
                return "Compost quantity cannot be negative.", None
            if biogas is not None and biogas < 0:
                return "Biogas quantity cannot be negative.", None

            if compost is not None and biogas is None:
                biogas = round(total_wet - compost, 2)
            elif biogas is not None and compost is None:
                compost = round(total_wet - biogas, 2)

            assert compost is not None
            assert biogas is not None

            if compost < 0 or biogas < 0:
                return "Processing quantities cannot exceed total wet waste logged so far.", None
            if compost > total_wet or biogas > total_wet:
                return "Processing quantities cannot exceed total wet waste logged so far.", None
            if abs((compost + biogas) - total_wet) > 0.05:
                return "Compost and biogas quantities must add up to the total wet waste logged so far.", None

            return (
                None,
                {
                    "employee_id": session["employee_id"],
                    "compost_quantity": round(compost, 2),
                    "biogas_quantity": round(biogas, 2),
                    "total_wet_reference": round(total_wet, 2),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )

        def insert_entry(self, entry: dict[str, Any]) -> None:
            with sqlite3.connect(config.db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO waste_entries (
                        employee_id,
                        waste_category,
                        waste_subtype,
                        source_location,
                        housing_block,
                        room_number,
                        quantity,
                        start_date,
                        end_date,
                        entry_kind,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry["employee_id"],
                        entry["waste_category"],
                        entry["waste_subtype"],
                        entry["source_location"],
                        entry["housing_block"],
                        entry["room_number"],
                        entry["quantity"],
                        entry["start_date"],
                        entry["end_date"],
                        entry["entry_kind"],
                        entry["created_at"],
                    ),
                )
                connection.commit()

        def insert_wet_processing_update(self, update: dict[str, Any]) -> None:
            with sqlite3.connect(config.db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO wet_processing_updates (
                        employee_id,
                        compost_quantity,
                        biogas_quantity,
                        total_wet_reference,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        update["employee_id"],
                        update["compost_quantity"],
                        update["biogas_quantity"],
                        update["total_wet_reference"],
                        update["created_at"],
                    ),
                )
                connection.commit()

        def load_wet_processing_status(self) -> dict[str, Any]:
            with sqlite3.connect(config.db_path) as connection:
                connection.row_factory = sqlite3.Row
                total_wet = total_wet_collected(connection)
                latest = connection.execute(
                    """
                    SELECT employee_id, compost_quantity, biogas_quantity, total_wet_reference, created_at
                    FROM wet_processing_updates
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

            latest_update = None
            allocated_compost = 0.0
            allocated_biogas = 0.0
            reference_total = round(total_wet, 2)
            if latest:
                allocated_compost = float(latest["compost_quantity"])
                allocated_biogas = float(latest["biogas_quantity"])
                reference_total = float(latest["total_wet_reference"])
                latest_update = {
                    "employeeId": latest["employee_id"],
                    "compostQuantity": allocated_compost,
                    "biogasQuantity": allocated_biogas,
                    "totalWetReference": reference_total,
                    "timestamp": latest["created_at"],
                }

            return {
                "totalWetCollected": round(total_wet, 2),
                "latestUpdate": latest_update,
                "pendingAllocation": round(max(total_wet - allocated_compost - allocated_biogas, 0), 2),
            }

        def load_dashboard(self) -> dict[str, Any]:
            today = datetime.now().date().isoformat()
            with sqlite3.connect(config.db_path) as connection:
                connection.row_factory = sqlite3.Row
                metrics_row = connection.execute(
                    """
                    SELECT
                        COALESCE(SUM(quantity), 0) AS total_weight,
                        COALESCE(SUM(CASE WHEN waste_category = 'Wet Waste' THEN quantity END), 0) AS wet_weight,
                        COALESCE(SUM(CASE WHEN waste_category = 'Dry Waste' THEN quantity END), 0) AS dry_weight,
                        COALESCE(SUM(CASE WHEN waste_category = 'Hazardous Waste' THEN quantity END), 0) AS hazardous_weight,
                        COUNT(*) AS entries_count
                    FROM waste_entries
                    WHERE COALESCE(entry_kind, 'collection') = 'collection'
                    AND substr(created_at, 1, 10) = ?
                    """,
                    (today,),
                ).fetchone()
                breakdown_rows = connection.execute(
                    """
                    SELECT waste_category, COUNT(*) AS entries_count, ROUND(COALESCE(SUM(quantity), 0), 2) AS total_weight
                    FROM waste_entries
                    WHERE COALESCE(entry_kind, 'collection') = 'collection'
                    GROUP BY waste_category
                    ORDER BY waste_category
                    """
                ).fetchall()
                recent_rows = connection.execute(
                    """
                    SELECT
                        employee_id,
                        waste_category,
                        waste_subtype,
                        source_location,
                        housing_block,
                        room_number,
                        quantity,
                        start_date,
                        end_date,
                        created_at
                    FROM waste_entries
                    WHERE COALESCE(entry_kind, 'collection') = 'collection'
                    ORDER BY id DESC
                    LIMIT 10
                    """
                ).fetchall()

                total_wet = total_wet_collected(connection)
                latest_processing = connection.execute(
                    """
                    SELECT employee_id, compost_quantity, biogas_quantity, total_wet_reference, created_at
                    FROM wet_processing_updates
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

            metrics = {
                "totalWasteToday": round(float(metrics_row["total_weight"]), 2),
                "wetWasteToday": round(float(metrics_row["wet_weight"]), 2),
                "dryWasteToday": round(float(metrics_row["dry_weight"]), 2),
                "hazardousWasteToday": round(float(metrics_row["hazardous_weight"]), 2),
                "entriesToday": int(metrics_row["entries_count"]),
            }
            breakdown = [
                {
                    "wasteCategory": row["waste_category"],
                    "entriesCount": int(row["entries_count"]),
                    "totalWeight": float(row["total_weight"]),
                }
                for row in breakdown_rows
            ]
            recent_entries = [
                {
                    "employeeId": row["employee_id"],
                    "wasteCategory": row["waste_category"],
                    "wasteSubtype": row["waste_subtype"],
                    "location": derive_location_label(row["source_location"], row["housing_block"], row["room_number"]),
                    "quantity": float(row["quantity"]),
                    "startDate": row["start_date"],
                    "endDate": row["end_date"],
                    "timestamp": row["created_at"],
                }
                for row in recent_rows
            ]

            latest_processing_update = None
            if latest_processing:
                latest_processing_update = {
                    "employeeId": latest_processing["employee_id"],
                    "compostQuantity": float(latest_processing["compost_quantity"]),
                    "biogasQuantity": float(latest_processing["biogas_quantity"]),
                    "totalWetReference": float(latest_processing["total_wet_reference"]),
                    "timestamp": latest_processing["created_at"],
                }

            wet_processing = {
                "totalWetCollected": round(total_wet, 2),
                "latestUpdate": latest_processing_update,
                "pendingAllocation": round(
                    max(
                        total_wet
                        - (float(latest_processing["compost_quantity"]) if latest_processing else 0.0)
                        - (float(latest_processing["biogas_quantity"]) if latest_processing else 0.0),
                        0,
                    ),
                    2,
                ),
            }
            return {
                "metrics": metrics,
                "breakdown": breakdown,
                "recentEntries": recent_entries,
                "wetProcessing": wet_processing,
            }

        def send_json(
            self,
            payload: dict[str, Any],
            *,
            status: HTTPStatus = HTTPStatus.OK,
            cookie: str | None = None,
        ) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)

        def send_error_json(self, status: HTTPStatus, message: str) -> None:
            self.send_json({"error": message}, status=status)

    return WasteAppHandler


def parse_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def total_wet_collected(connection: sqlite3.Connection) -> float:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(quantity), 0)
        FROM waste_entries
        WHERE waste_category = 'Wet Waste'
        AND COALESCE(entry_kind, 'collection') = 'collection'
        """
    ).fetchone()
    return float(row[0] or 0)


def derive_location_label(source_location: str | None, housing_block: str | None, room_number: str | None) -> str:
    if source_location:
        return source_location
    if housing_block and room_number:
        return f"{housing_block} / {room_number}"
    if housing_block:
        return housing_block
    return "Not specified"


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus waste management demo app")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind")
    parser.add_argument(
        "--port",
        default=int(os.environ.get("PORT", "8000")),
        type=int,
        help="Port to run the web server on",
    )
    parser.add_argument(
        "--db-path",
        default=os.environ.get("DB_PATH"),
        help="Optional database file path",
    )
    args = parser.parse_args()

    db_path = Path(args.db_path).resolve() if args.db_path else None
    server = create_server(args.host, args.port, db_path=db_path)
    print(f"Waste management demo running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
