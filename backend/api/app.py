"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..core.config import ROOT, get_settings
from ..core.errors import PromptForgeError
from ..core.security import redact
from ..optimizer.engine import mark_interrupted_runs
from ..services.bootstrap import bootstrap
from . import routes_core, routes_experiments, routes_misc

log = logging.getLogger("promptforge")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1", "testserver"}
DEV_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}


def create_app(db_path=None, *, serve_frontend: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bootstrap(db_path)
        n = mark_interrupted_runs()
        if n:
            log.warning("%d optimisation run(s) were interrupted by a restart", n)
        yield

    app = FastAPI(title="PromptForge", version="1.0.0", lifespan=lifespan)
    s = get_settings()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # DNS-rebinding defence: only answer for loopback Host headers unless LAN mode is explicitly enabled.
        host = request.url.hostname or ""
        if not s.allow_lan and host not in LOCAL_HOSTS:
            return JSONResponse({"detail": "Host not allowed"}, status_code=403)
        # CSRF defence for the unauthenticated local API: reject cross-origin state changes.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and not s.allow_lan and origin not in DEV_ORIGINS and urlparse(origin).hostname not in {"localhost", "127.0.0.1"}:
                return JSONResponse({"detail": "Cross-origin request blocked"}, status_code=403)
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else resp.headers.get("Cache-Control", "")
        return resp

    @app.exception_handler(PromptForgeError)
    async def pf_error(_: Request, exc: PromptForgeError):
        return JSONResponse({"detail": redact(str(exc))}, status_code=exc.status_code)

    @app.exception_handler(KeyError)
    async def missing_field(_: Request, exc: KeyError):
        return JSONResponse({"detail": f"Missing required field: {exc.args[0] if exc.args else '?'}"}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"detail": f"Internal error ({type(exc).__name__}). See server log."}, status_code=500)

    for r in (routes_core.router, routes_experiments.router, routes_misc.router):
        app.include_router(r, prefix="/api")

    dist = ROOT / "frontend" / "dist"
    if serve_frontend and dist.is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")
    return app
