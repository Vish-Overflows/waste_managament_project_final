from __future__ import annotations

import argparse
import base64
import json
import hashlib
import hmac
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

BLOCKS = [f"HB {index}" for index in range(1, 8)]
COMMON_ROOMS = ["101", "102", "103", "201", "202", "203"]
ROOMS_BY_BLOCK = {block: COMMON_ROOMS[:] for block in BLOCKS}
PROCESSING_CATEGORIES = ["Dry Waste", "Wet Waste"]
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
WET_WASTE_TYPES = ["Mixed Organic Waste", "Food Waste", "Leaf and Garden Waste"]
USERS = {
    "staff1": {"password": "password", "role": "staff"},
    "staff2": {"password": "password", "role": "staff"},
    "operator1": {"password": "password", "role": "operator"},
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
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS housing_collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                housing_block TEXT NOT NULL,
                room_number TEXT NOT NULL,
                collection_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'collected',
                created_at TEXT NOT NULL
            )
            """
        )
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
                entry_kind TEXT NOT NULL DEFAULT 'segregation',
                collection_id INTEGER,
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
        seed_demo_users(connection)
        connection.commit()


def hash_password(password: str, salt: str | None = None) -> str:
    password_salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt.encode("utf-8"),
        200000,
    )
    encoded = base64.b64encode(derived).decode("ascii")
    return f"pbkdf2_sha256${password_salt}${encoded}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, digest = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    comparison = hash_password(password, salt)
    return hmac.compare_digest(comparison, stored_hash)


def seed_demo_users(connection: sqlite3.Connection) -> None:
    for username, data in USERS.items():
        existing = connection.execute(
            "SELECT username FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if existing:
            continue
        connection.execute(
            """
            INSERT INTO users (username, password_hash, role, active, created_at)
            VALUES (?, ?, ?, 1, ?)
            """,
            (
                username,
                hash_password(data["password"]),
                data["role"],
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    existing = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def migrate_waste_entries_schema(connection: sqlite3.Connection) -> None:
    ensure_column(connection, "waste_entries", "source_location", "TEXT")
    ensure_column(connection, "waste_entries", "entry_kind", "TEXT NOT NULL DEFAULT 'segregation'")
    ensure_column(connection, "waste_entries", "collection_id", "INTEGER")

    columns = {
        row[1]: {
            "notnull": row[3],
        }
        for row in connection.execute("PRAGMA table_info(waste_entries)").fetchall()
    }
    needs_rebuild = "waste_subtype" in columns and columns["waste_subtype"]["notnull"] == 1
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
            entry_kind TEXT NOT NULL DEFAULT 'segregation',
            collection_id INTEGER,
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
            collection_id,
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
            COALESCE(entry_kind, 'segregation'),
            collection_id,
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
        server_version = "WasteApp/3.0"

        def do_HEAD(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/styles.css", "/app.js", "/api/config", "/api/session", "/api/operator/collections", "/api/wet-processing-status", "/api/dashboard", "/healthz"}:
                self.send_response(HTTPStatus.OK)
                self.end_headers()
                return
            self.send_error(HTTPStatus.NOT_FOUND)

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
                        "blocks": BLOCKS,
                        "roomsByBlock": ROOMS_BY_BLOCK,
                        "processingCategories": PROCESSING_CATEGORIES,
                        "dryWasteTypes": DRY_WASTE_TYPES,
                        "wetWasteTypes": WET_WASTE_TYPES,
                        "demoUsers": [
                            {"username": username, "role": data["role"]}
                            for username, data in USERS.items()
                        ],
                    }
                )
                return
            if path == "/healthz":
                self.send_json({"status": "ok"})
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
            if path == "/api/operator/collections":
                session = self.require_session()
                if not session:
                    return
                if session["role"] not in {"operator", "admin"}:
                    self.send_error_json(HTTPStatus.FORBIDDEN, "Operator access required.")
                    return
                self.send_json({"collections": self.load_operator_collections()})
                return
            if path == "/api/wet-processing-status":
                session = self.require_session()
                if not session:
                    return
                if session["role"] not in {"operator", "admin"}:
                    self.send_error_json(HTTPStatus.FORBIDDEN, "Operator access required.")
                    return
                self.send_json(self.load_wet_processing_status())
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
                with sqlite3.connect(config.db_path) as connection:
                    connection.row_factory = sqlite3.Row
                    user = connection.execute(
                        """
                        SELECT username, password_hash, role, active
                        FROM users
                        WHERE username = ?
                        """,
                        (username,),
                    ).fetchone()
                if not user or not bool(user["active"]) or not verify_password(password, user["password_hash"]):
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
            if path == "/api/staff-collections":
                session = self.require_session()
                if not session:
                    return
                if session["role"] != "staff":
                    self.send_error_json(HTTPStatus.FORBIDDEN, "Staff access required.")
                    return
                payload = self.read_json_body()
                if payload is None:
                    return
                validation_error, entry = self.validate_staff_collection(payload, session)
                if validation_error:
                    self.send_error_json(HTTPStatus.BAD_REQUEST, validation_error)
                    return
                self.insert_staff_collection(entry)
                self.send_json({"message": "Housing collection marked successfully."}, status=HTTPStatus.CREATED)
                return
            if path == "/api/processing-entries":
                session = self.require_session()
                if not session:
                    return
                if session["role"] != "operator":
                    self.send_error_json(HTTPStatus.FORBIDDEN, "Operator access required.")
                    return
                payload = self.read_json_body()
                if payload is None:
                    return
                validation_error, entry = self.validate_processing_entry(payload, session)
                if validation_error:
                    self.send_error_json(HTTPStatus.BAD_REQUEST, validation_error)
                    return
                self.insert_processing_entry(entry)
                self.send_json({"message": "Segregation entry saved successfully."}, status=HTTPStatus.CREATED)
                return
            if path == "/api/wet-processing-updates":
                session = self.require_session()
                if not session:
                    return
                if session["role"] != "operator":
                    self.send_error_json(HTTPStatus.FORBIDDEN, "Operator access required.")
                    return
                payload = self.read_json_body()
                if payload is None:
                    return
                validation_error, update = self.validate_wet_processing_update(payload, session)
                if validation_error:
                    self.send_error_json(HTTPStatus.BAD_REQUEST, validation_error)
                    return
                self.insert_wet_processing_update(update)
                self.send_json({"message": "Compost update saved successfully."}, status=HTTPStatus.CREATED)
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

        def validate_staff_collection(
            self, payload: dict[str, Any], session: dict[str, Any]
        ) -> tuple[str | None, dict[str, Any] | None]:
            block = str(payload.get("housingBlock", "")).strip()
            room = str(payload.get("roomNumber", "")).strip()
            collection_date = str(payload.get("collectionDate", "")).strip()

            if block not in BLOCKS:
                return "Select a valid housing block.", None
            if room not in ROOMS_BY_BLOCK.get(block, []):
                return "Select a valid room number.", None
            try:
                date.fromisoformat(collection_date)
            except ValueError:
                return "Select a valid collection date.", None

            return (
                None,
                {
                    "employee_id": session["employee_id"],
                    "housing_block": block,
                    "room_number": room,
                    "collection_date": collection_date,
                    "status": "collected",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )

        def validate_processing_entry(
            self, payload: dict[str, Any], session: dict[str, Any]
        ) -> tuple[str | None, dict[str, Any] | None]:
            collection_id_raw = payload.get("collectionId")
            try:
                collection_id = int(collection_id_raw)
            except (TypeError, ValueError):
                return "Select a valid collected housing entry.", None

            category = str(payload.get("wasteCategory", "")).strip()
            subtype = str(payload.get("wasteSubtype", "")).strip()
            quantity_error, quantity = self.parse_positive_number(payload.get("quantity"), "waste quantity")
            if quantity_error:
                return quantity_error, None

            if category not in PROCESSING_CATEGORIES:
                return "Select a valid waste category.", None
            valid_subtypes = DRY_WASTE_TYPES if category == "Dry Waste" else WET_WASTE_TYPES
            if subtype not in valid_subtypes:
                return "Select a valid waste sub type.", None

            with sqlite3.connect(config.db_path) as connection:
                connection.row_factory = sqlite3.Row
                collection = connection.execute(
                    """
                    SELECT id, housing_block, room_number
                    FROM housing_collections
                    WHERE id = ?
                    """,
                    (collection_id,),
                ).fetchone()

            if collection is None:
                return "Selected housing collection could not be found.", None

            return (
                None,
                {
                    "employee_id": session["employee_id"],
                    "collection_id": collection_id,
                    "waste_category": category,
                    "waste_subtype": subtype,
                    "housing_block": collection["housing_block"],
                    "room_number": collection["room_number"],
                    "quantity": quantity,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )

        def validate_wet_processing_update(
            self, payload: dict[str, Any], session: dict[str, Any]
        ) -> tuple[str | None, dict[str, Any] | None]:
            with sqlite3.connect(config.db_path) as connection:
                total_wet = total_wet_processed(connection)

            if total_wet <= 0:
                return "No wet waste segregation entries exist yet.", None

            compost_error, compost_quantity = self.parse_positive_number(
                payload.get("compostQuantity"), "compost quantity"
            )
            if compost_error:
                return compost_error, None
            assert compost_quantity is not None
            if compost_quantity > total_wet:
                return "Compost quantity cannot exceed total wet waste processed so far.", None

            biogas_quantity = round(total_wet - compost_quantity, 2)
            return (
                None,
                {
                    "employee_id": session["employee_id"],
                    "compost_quantity": round(compost_quantity, 2),
                    "biogas_quantity": biogas_quantity,
                    "total_wet_reference": round(total_wet, 2),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                },
            )

        def insert_staff_collection(self, entry: dict[str, Any]) -> None:
            with sqlite3.connect(config.db_path) as connection:
                connection.execute(
                    """
                    INSERT INTO housing_collections (
                        employee_id,
                        housing_block,
                        room_number,
                        collection_date,
                        status,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry["employee_id"],
                        entry["housing_block"],
                        entry["room_number"],
                        entry["collection_date"],
                        entry["status"],
                        entry["created_at"],
                    ),
                )
                connection.commit()

        def insert_processing_entry(self, entry: dict[str, Any]) -> None:
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
                        collection_id,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry["employee_id"],
                        entry["waste_category"],
                        entry["waste_subtype"],
                        None,
                        entry["housing_block"],
                        entry["room_number"],
                        entry["quantity"],
                        None,
                        None,
                        "segregation",
                        entry["collection_id"],
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

        def load_operator_collections(self) -> list[dict[str, Any]]:
            with sqlite3.connect(config.db_path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT
                        hc.id,
                        hc.employee_id,
                        hc.housing_block,
                        hc.room_number,
                        hc.collection_date,
                        hc.status,
                        hc.created_at,
                        COUNT(we.id) AS processed_entries_count,
                        ROUND(COALESCE(SUM(we.quantity), 0), 2) AS processed_weight
                    FROM housing_collections hc
                    LEFT JOIN waste_entries we ON we.collection_id = hc.id
                    GROUP BY hc.id
                    ORDER BY hc.id DESC
                    LIMIT 30
                    """
                ).fetchall()

            return [
                {
                    "id": row["id"],
                    "employeeId": row["employee_id"],
                    "housingBlock": row["housing_block"],
                    "roomNumber": row["room_number"],
                    "collectionDate": row["collection_date"],
                    "status": row["status"],
                    "timestamp": row["created_at"],
                    "processedEntriesCount": int(row["processed_entries_count"]),
                    "processedWeight": float(row["processed_weight"]),
                }
                for row in rows
            ]

        def load_wet_processing_status(self) -> dict[str, Any]:
            with sqlite3.connect(config.db_path) as connection:
                connection.row_factory = sqlite3.Row
                total_wet = total_wet_processed(connection)
                latest = connection.execute(
                    """
                    SELECT employee_id, compost_quantity, biogas_quantity, total_wet_reference, created_at
                    FROM wet_processing_updates
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

            latest_update = None
            if latest:
                latest_update = {
                    "employeeId": latest["employee_id"],
                    "compostQuantity": float(latest["compost_quantity"]),
                    "biogasQuantity": float(latest["biogas_quantity"]),
                    "totalWetReference": float(latest["total_wet_reference"]),
                    "timestamp": latest["created_at"],
                }

            return {
                "totalWetProcessed": round(total_wet, 2),
                "latestUpdate": latest_update,
            }

        def load_dashboard(self) -> dict[str, Any]:
            today = datetime.now().date().isoformat()
            last_7_days = connection_rows = None
            with sqlite3.connect(config.db_path) as connection:
                connection.row_factory = sqlite3.Row
                metrics = connection.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM housing_collections WHERE collection_date = ?) AS collections_today,
                        (SELECT COUNT(*) FROM waste_entries WHERE substr(created_at, 1, 10) = ?) AS processed_entries_today,
                        (SELECT COALESCE(SUM(quantity), 0) FROM waste_entries WHERE waste_category = 'Dry Waste' AND substr(created_at, 1, 10) = ?) AS dry_today,
                        (SELECT COALESCE(SUM(quantity), 0) FROM waste_entries WHERE waste_category = 'Wet Waste' AND substr(created_at, 1, 10) = ?) AS wet_today,
                        (SELECT COALESCE(SUM(quantity), 0) FROM waste_entries WHERE substr(created_at, 1, 10) = ?) AS total_processed_today
                    """,
                    (today, today, today, today, today),
                ).fetchone()

                breakdown_rows = connection.execute(
                    """
                    SELECT waste_category, COUNT(*) AS entries_count, ROUND(COALESCE(SUM(quantity), 0), 2) AS total_weight
                    FROM waste_entries
                    GROUP BY waste_category
                    ORDER BY waste_category
                    """
                ).fetchall()

                recent_collections = connection.execute(
                    """
                    SELECT employee_id, housing_block, room_number, collection_date, created_at
                    FROM housing_collections
                    ORDER BY id DESC
                    LIMIT 10
                    """
                ).fetchall()

                recent_processing = connection.execute(
                    """
                    SELECT employee_id, waste_category, waste_subtype, housing_block, room_number, quantity, created_at
                    FROM waste_entries
                    ORDER BY id DESC
                    LIMIT 10
                    """
                ).fetchall()

                block_rows = connection.execute(
                    """
                    SELECT
                        hc.housing_block,
                        COUNT(hc.id) AS collections_count,
                        ROUND(COALESCE(SUM(we.quantity), 0), 2) AS processed_weight
                    FROM housing_collections hc
                    LEFT JOIN waste_entries we ON we.collection_id = hc.id
                    GROUP BY hc.housing_block
                    ORDER BY hc.housing_block
                    """
                ).fetchall()

                operator_rows = connection.execute(
                    """
                    SELECT employee_id, COUNT(*) AS entries_count, ROUND(COALESCE(SUM(quantity), 0), 2) AS total_weight
                    FROM waste_entries
                    GROUP BY employee_id
                    ORDER BY total_weight DESC, entries_count DESC
                    LIMIT 5
                    """
                ).fetchall()

                last_7_days = connection.execute(
                    """
                    SELECT
                        substr(created_at, 1, 10) AS entry_date,
                        ROUND(COALESCE(SUM(quantity), 0), 2) AS total_weight
                    FROM waste_entries
                    WHERE date(substr(created_at, 1, 10)) >= date('now', '-6 days')
                    GROUP BY substr(created_at, 1, 10)
                    ORDER BY entry_date
                    """
                ).fetchall()

                wet_status = self.load_wet_processing_status()

            total_processed_all_time = sum(item["totalWeight"] for item in [
                {
                    "wasteCategory": row["waste_category"],
                    "entriesCount": int(row["entries_count"]),
                    "totalWeight": float(row["total_weight"]),
                }
                for row in breakdown_rows
            ])

            return {
                "metrics": {
                    "collectionsToday": int(metrics["collections_today"]),
                    "processedEntriesToday": int(metrics["processed_entries_today"]),
                    "dryWasteToday": round(float(metrics["dry_today"]), 2),
                    "wetWasteToday": round(float(metrics["wet_today"]), 2),
                    "totalProcessedToday": round(float(metrics["total_processed_today"]), 2),
                },
                "breakdown": [
                    {
                        "wasteCategory": row["waste_category"],
                        "entriesCount": int(row["entries_count"]),
                        "totalWeight": float(row["total_weight"]),
                        "sharePercent": round(
                            (float(row["total_weight"]) / total_processed_all_time * 100) if total_processed_all_time else 0,
                            1,
                        ),
                    }
                    for row in breakdown_rows
                ],
                "blockAnalytics": [
                    {
                        "housingBlock": row["housing_block"],
                        "collectionsCount": int(row["collections_count"]),
                        "processedWeight": float(row["processed_weight"]),
                    }
                    for row in block_rows
                ],
                "operatorAnalytics": [
                    {
                        "employeeId": row["employee_id"],
                        "entriesCount": int(row["entries_count"]),
                        "totalWeight": float(row["total_weight"]),
                    }
                    for row in operator_rows
                ],
                "trendAnalytics": [
                    {
                        "date": row["entry_date"],
                        "totalWeight": float(row["total_weight"]),
                    }
                    for row in last_7_days
                ],
                "recentCollections": [
                    {
                        "employeeId": row["employee_id"],
                        "housingBlock": row["housing_block"],
                        "roomNumber": row["room_number"],
                        "collectionDate": row["collection_date"],
                        "timestamp": row["created_at"],
                    }
                    for row in recent_collections
                ],
                "recentProcessingEntries": [
                    {
                        "employeeId": row["employee_id"],
                        "wasteCategory": row["waste_category"],
                        "wasteSubtype": row["waste_subtype"],
                        "housingBlock": row["housing_block"],
                        "roomNumber": row["room_number"],
                        "quantity": float(row["quantity"]),
                        "timestamp": row["created_at"],
                    }
                    for row in recent_processing
                ],
                "wetProcessing": wet_status,
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


def total_wet_processed(connection: sqlite3.Connection) -> float:
    row = connection.execute(
        """
        SELECT COALESCE(SUM(quantity), 0)
        FROM waste_entries
        WHERE waste_category = 'Wet Waste'
        """
    ).fetchone()
    return float(row[0] or 0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Campus waste management portal")
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
