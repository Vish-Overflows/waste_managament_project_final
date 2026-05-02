import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.api import auth, collections, dashboard, processing
from app.core.config import get_settings
from app.core.security import get_password_hash
from app.db import Base, SessionLocal, engine
from app.models import User

settings = get_settings()
logger = logging.getLogger("campus-waste")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def seed_users() -> None:
    demo_users = {
        "staff1": "staff",
        "staff2": "staff",
        "operator1": "operator",
        "admin": "admin",
    }
    with SessionLocal() as db:
        for username, role in demo_users.items():
            existing = db.query(User).filter(User.username == username).first()
            if existing:
                continue
            db.add(
                User(
                    username=username,
                    password_hash=get_password_hash("password"),
                    role=role,
                    active=True,
                )
            )
        db.commit()


def allow_direct_waste_entries() -> None:
    inspector = inspect(engine)
    if "waste_entries" not in inspector.get_table_names():
        return

    columns = {column["name"]: column for column in inspector.get_columns("waste_entries")}
    collection_id = columns.get("collection_id")
    if not collection_id or collection_id.get("nullable"):
        return

    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE waste_entries RENAME TO waste_entries_old"))
            connection.execute(
                text(
                    """
                    CREATE TABLE waste_entries (
                        id INTEGER NOT NULL,
                        employee_id VARCHAR(120) NOT NULL,
                        waste_category VARCHAR(32) NOT NULL,
                        waste_subtype VARCHAR(120) NOT NULL,
                        housing_block VARCHAR(32) NOT NULL,
                        room_number VARCHAR(32) NOT NULL,
                        quantity NUMERIC(10, 2) NOT NULL,
                        collection_id INTEGER,
                        created_at DATETIME DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(collection_id) REFERENCES housing_collections (id)
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO waste_entries (
                        id,
                        employee_id,
                        waste_category,
                        waste_subtype,
                        housing_block,
                        room_number,
                        quantity,
                        collection_id,
                        created_at
                    )
                    SELECT
                        id,
                        employee_id,
                        waste_category,
                        waste_subtype,
                        housing_block,
                        room_number,
                        quantity,
                        collection_id,
                        created_at
                    FROM waste_entries_old
                    """
                )
            )
            connection.execute(text("DROP TABLE waste_entries_old"))
            connection.execute(text("CREATE INDEX ix_waste_entries_employee_id ON waste_entries (employee_id)"))
            connection.execute(text("CREATE INDEX ix_waste_entries_collection_id ON waste_entries (collection_id)"))
            connection.execute(text("CREATE INDEX ix_waste_entries_id ON waste_entries (id)"))
            connection.execute(text("CREATE INDEX ix_waste_entries_waste_category ON waste_entries (waste_category)"))
            connection.execute(text("CREATE INDEX ix_waste_entries_housing_block ON waste_entries (housing_block)"))
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE waste_entries ALTER COLUMN collection_id DROP NOT NULL"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    allow_direct_waste_entries()
    seed_users()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            json.dumps(
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                }
            )
        )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled application error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(collections.router, prefix=settings.api_prefix)
app.include_router(processing.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)
