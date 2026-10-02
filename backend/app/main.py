"""FastAPI application entry point.

Local:       python run.py                      (from the repository root)
Production:  uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
"""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import config
from .auth import ensure_admin_user
from .db import SessionLocal, init_db
from .intelligence import column_model
from .routers import auth_routes, data_routes, order_routes
from .services import storage, workspace

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ordertrack")
_state = {"ready": False, "started": time.time()}


@asynccontextmanager
async def lifespan(_: FastAPI):
    problems = config.validate()
    if problems:
        for p in problems:
            log.critical("CONFIGURATION ERROR: %s", p)
        raise RuntimeError("Refusing to start in production: " + " | ".join(problems))
    init_db()
    if config.STORAGE_BACKEND == "s3":
        try:
            storage.get().check()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Cannot reach the S3 bucket '{config.S3_BUCKET}': {e}. Check S3_ENDPOINT_URL and the keys.") from e
    ensure_admin_user()
    from .ingest.pipeline import resume_interrupted
    resume_interrupted()                  # uploads cut off by a restart/deploy are processed again

    def warm():                           # load (or train) the models and build the workspace in the background
        try:
            column_model.train()
            workspace.get()
        finally:
            _state["ready"] = True
    threading.Thread(target=warm, daemon=True, name="warm-up").start()
    log.info("OrderTrack Pro started (env=%s, database=%s, files=%s)", config.ENV,
             "sqlite" if config.IS_SQLITE else "postgresql", config.STORAGE_BACKEND)
    yield


app = FastAPI(title="OrderTrack Pro", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs" if config.API_DOCS else None, redoc_url=None,
              openapi_url="/api/openapi.json" if config.API_DOCS else None)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_origin_regex=config.CORS_ORIGIN_REGEX,
                   allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type"], expose_headers=["Content-Disposition"], max_age=3600)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
        resp.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    if config.IS_PRODUCTION:
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Something went wrong on the server. The error has been logged."}, status_code=500)


app.include_router(auth_routes.router)
app.include_router(data_routes.router)
app.include_router(order_routes.router)


@app.get("/api/health")
def health():
    """Liveness + readiness: database reachable, models warmed up."""
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    body = {"status": "ok" if db_ok else "degraded", "database": db_ok, "ready": _state["ready"],
            "uptime_s": int(time.time() - _state["started"]), "version": app.version}
    return JSONResponse(body, status_code=200 if db_ok else 503)


# ---- optionally serve the built single-page app (frontend/dist) from the same server
if (config.STATIC_DIR / "index.html").exists():
    if (config.STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = (config.STATIC_DIR / path).resolve()
        if path and f.is_file() and config.STATIC_DIR in f.parents:
            return FileResponse(f)
        return FileResponse(config.STATIC_DIR / "index.html")
