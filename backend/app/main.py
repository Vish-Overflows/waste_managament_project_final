import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_users()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
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
