from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.database import SessionLocal
from app.routers import auth, cases, demo, health, line, modules, platforms, public
from app.services import auth_service, platform_service

logger = logging.getLogger("aidflow")

_problems = settings.startup_problems()
if _problems:
    raise RuntimeError(
        "不安全的部署設定，已停止啟動（ENVIRONMENT=" + settings.ENVIRONMENT + "）：\n  - "
        + "\n  - ".join(_problems)
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with SessionLocal() as db:
            created = auth_service.bootstrap_admin(db)
            if created:
                logger.info("created initial administrator account '%s' (must change password)", created.username)
            if settings.DEMO_MODE:
                # a fresh start shows a clean workspace, not yesterday's experiments
                removed = platform_service.prune_generated(db)
                if removed:
                    logger.info("retired %d generated platform(s): %s", len(removed), ", ".join(removed))
    except Exception as exc:  # noqa: BLE001 — never block startup on housekeeping
        logger.warning("startup housekeeping skipped: %s", exc)
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    # the interactive API browser is a development aid, not a public surface
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
    description=(
        "AidFlow 災情通報與處理平台：民眾通報 → 同地點聚合 → 承辦審核（上報 EMIC／民間可處理）→ "
        "處理進度公開。公開端點位於 /v1/public（免登入）；其餘為政府管理後台端點，需登入並依角色授權。"
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # the API serves JSON and stored photos only — never frame it, never run scripts from it
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    )
    if request.url.path.startswith("/v1/") and not request.url.path.startswith("/v1/public/media"):
        response.headers.setdefault("Cache-Control", "no-store")
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.include_router(health.router)
app.include_router(public.router)
app.include_router(auth.router)
app.include_router(modules.router)
app.include_router(platforms.router)
app.include_router(cases.router)
app.include_router(demo.router)
app.include_router(line.router)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal database error."})


def _custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "POST /v1/auth/login 取得權杖。/v1/public、/v1/health 與 /v1/line/webhook 免登入。",
        },
    }
    schema["security"] = [{"BearerAuth": []}]
    # every operation can answer these; spelling them out keeps the published
    # contract complete (原始碼檢測：OpenAPI Missing Error Handling)
    schema.setdefault("components", {}).setdefault("schemas", {})["ErrorResponse"] = {
        "title": "ErrorResponse",
        "type": "object",
        "properties": {"detail": {"title": "Detail", "type": "string", "description": "錯誤說明（使用者可讀）"}},
        "required": ["detail"],
    }
    error_ref = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}}}
    common_errors = {
        "401": {"description": "未登入或權杖失效", **error_ref},
        "403": {"description": "角色沒有此操作權限", **error_ref},
        "429": {"description": "請求過於頻繁（頻率限制）", **error_ref},
        "500": {"description": "伺服器內部錯誤", **error_ref},
    }
    public_errors = {k: v for k, v in common_errors.items() if k in ("429", "500")}
    for path, ops in schema.get("paths", {}).items():
        is_public = path.startswith("/v1/public") or path in ("/v1/health", "/v1/line/webhook", "/v1/auth/login")
        for method, op in ops.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            responses = op.setdefault("responses", {})
            for code, body in (public_errors if is_public else common_errors).items():
                responses.setdefault(code, body)
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _custom_openapi  # type: ignore[method-assign]


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {"service": "aidflow-api", "health": "/v1/health"}
