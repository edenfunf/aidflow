from __future__ import annotations

import hmac
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.database import SessionLocal
from app.routers import agent, avl, cases, demo, health, modules, platforms, public
from app.services import platform_service

logger = logging.getLogger("aidflow")

@asynccontextmanager
async def lifespan(_: FastAPI):
    """A fresh start shows a clean workspace, not yesterday's experiments."""
    if settings.DEMO_MODE:
        try:
            with SessionLocal() as db:
                removed = platform_service.prune_generated(db)
            if removed:
                logging.getLogger("aidflow").info("retired %d generated platform(s): %s", len(removed), ", ".join(removed))
        except Exception as exc:  # noqa: BLE001 — never block startup on housekeeping
            logging.getLogger("aidflow").warning("platform housekeeping skipped: %s", exc)
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AidFlow — 災害情境驅動的災情通報、案件處理、派工與視覺化平台生成器。"
        "公開端點位於 /v1/public；其餘為政府後台端點。"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_allow_all else settings.cors_origins_list,
    allow_credentials=not settings.cors_allow_all,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,
)

# Everything the citizen-facing portal needs lives under /v1/public and stays
# open; every other route (planner, platform management, case queue, dispatch,
# internal reports with PII, demo seeding) requires X-API-Key when
# ADMIN_API_KEY is configured.
_PUBLIC_PREFIXES = ("/v1/health", "/v1/public/", "/docs", "/openapi.json", "/redoc")


def _is_public(path: str) -> bool:
    return path == "/" or any(path.startswith(p) for p in _PUBLIC_PREFIXES)


@app.middleware("http")
async def api_key_gate(request: Request, call_next):
    if settings.ADMIN_API_KEY and request.method != "OPTIONS" and not _is_public(request.url.path):
        provided = request.headers.get("X-API-Key", "")
        if not hmac.compare_digest(provided, settings.ADMIN_API_KEY):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid X-API-Key."})
    return await call_next(request)


app.include_router(health.router)
app.include_router(public.router)
app.include_router(agent.router)
app.include_router(modules.router)
app.include_router(platforms.router)
app.include_router(cases.router)
app.include_router(demo.router)
app.include_router(avl.router)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal database error."})


def _custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    schema.setdefault("components", {})["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "設定 ADMIN_API_KEY 後，/v1/public 與 /v1/health 以外的端點需帶此標頭。",
        }
    }
    schema["security"] = [{"ApiKeyAuth": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _custom_openapi  # type: ignore[method-assign]


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "aidflow-api", "version": settings.APP_VERSION, "docs": "/docs", "health": "/v1/health"}
