"""FastAPI application: middleware, error shape, and router wiring."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import auth, cameras, dashboard, ranges
from app.security import constant_time_equals

logger = logging.getLogger("terraedge")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
# A client cannot have a CSRF token before it has a session.
CSRF_EXEMPT_PATHS = {"/api/auth/login"}


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.check_production_settings()
    logger.info(
        "startup environment=%s serves_frontend=%s cookie_samesite=%s cookie_secure=%s cors=%s",
        settings.environment,
        settings.serves_frontend,
        settings.cookie_samesite,
        settings.cookie_secure,
        ",".join(settings.cors_origin_list) or "-",
    )
    yield
    logger.info("shutdown")


app = FastAPI(
    title="TerraEdge Camera Inventory API",
    version="1.0.0",
    description=(
        "Camera inventory and deployment tracking for Similipal Tiger Reserve. "
        "All demo data is fictional."
    ),
    lifespan=lifespan,
)

# Exact origins only: browsers reject a wildcard when credentials are enabled.
# Empty when this app serves the frontend itself.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """One structured line per request, correlatable end to end.

    Registered last, so it wraps every other middleware and sees the real
    status - including CSRF rejections and unhandled exceptions. The request id
    goes back in a header and into error bodies, so a user reporting a failure
    can quote something findable in the logs.
    """
    request_id = request.headers.get("X-Request-ID") or uuid4().hex[:12]
    request.state.request_id = request_id
    # Render terminates TLS, so the real client is the first forwarded hop.
    client = (request.headers.get("X-Forwarded-For", "") or "").split(",")[0].strip()
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            'request_id=%s method=%s path=%s status=500 duration_ms=%.1f client=%s error=unhandled',
            request_id,
            request.method,
            request.url.path,
            (time.perf_counter() - started) * 1000,
            client or "-",
        )
        raise

    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id

    # Health checks fire every few seconds on a platform probe; log them only
    # when they fail, so they cannot bury real traffic.
    if request.url.path == "/api/health" and response.status_code == 200:
        return response

    logger.log(
        logging.WARNING if response.status_code >= 400 else logging.INFO,
        'request_id=%s method=%s path=%s status=%s duration_ms=%.1f user=%s client=%s',
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        getattr(request.state, "user_id", None) or "-",
        client or "-",
    )
    return response


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    """Double-submit CSRF check for cookie-authenticated writes.

    Middleware rather than a decorator, so a new state-changing route is
    protected the moment it is added. Bearer requests are exempt: browsers
    never attach that header automatically.
    """
    if request.method in SAFE_METHODS or request.url.path in CSRF_EXEMPT_PATHS:
        return await call_next(request)

    if request.headers.get("Authorization", "").lower().startswith("bearer "):
        return await call_next(request)

    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    if cookie_token is None:
        if request.cookies.get(settings.session_cookie_name) is None:
            return await call_next(request)  # no session; the 401 comes later
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Missing CSRF token. Sign in again."},
        )

    header_token = request.headers.get("X-CSRF-Token", "")
    if not header_token or not constant_time_equals(header_token, cookie_token):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "CSRF token missing or invalid."},
        )

    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Flatten validation errors into one readable sentence plus per-field detail."""
    errors = []
    for err in exc.errors():
        location = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
        field = ".".join(location) or "request"
        message = err.get("msg", "Invalid value").removeprefix("Value error, ")
        errors.append({"field": field, "message": message})

    headline = errors[0]["message"] if errors else "The request could not be processed."
    if errors and errors[0]["field"] != "request":
        headline = f"{errors[0]['field']}: {headline}"

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": headline,
            "errors": errors,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe that also proves the database connection works."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check could not reach the database")
        return {"status": "degraded", "database": "unreachable"}
    return {"status": "ok", "database": "ok"}


app.include_router(auth.router)
app.include_router(ranges.router)
app.include_router(cameras.router)
app.include_router(dashboard.router)


# Serve the built frontend from this app when STATIC_DIR is set, making the web
# app and API one origin. Registered last, so /api routes win over the
# catch-all below.
if settings.serves_frontend:
    static_path = settings.static_path
    assert static_path is not None

    assets_dir = static_path / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str) -> Response:
        """Serve a real file if one exists, otherwise the app shell.

        `/cameras/12` is a client-side route, not a file on disk.
        """
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found."})

        candidate = (static_path / full_path).resolve()
        # is_relative_to stops `..` escaping the build directory.
        if full_path and candidate.is_file() and candidate.is_relative_to(static_path.resolve()):
            return FileResponse(candidate)

        return FileResponse(static_path / "index.html")
