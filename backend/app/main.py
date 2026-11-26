"""FastAPI application entry point (Fase 6: health, request IDs, metrics)."""
import logging
import time
from collections import Counter

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.security import new_token
from app.db.base import utcnow
from app.db.session import get_db
from app.services import health as health_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pli")

app = FastAPI(
    title=settings.app_name,
    version="6.0.0-fase6",
    description="Platform Pembelajaran Adaptif - Fase 6 (Analitik, Offline-first, Privasi & Produksi)",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.metrics = {
    "requests": 0,
    "status": Counter(),
    "errors": 0,
    "total_duration_sec": 0.0,
}


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or new_token()[:16]
    started = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - started
    if settings.metrics_enabled:
        metrics = app.state.metrics
        metrics["requests"] += 1
        metrics["status"][str(response.status_code)] += 1
        metrics["total_duration_sec"] += duration
        if response.status_code >= 500:
            metrics["errors"] += 1
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration * 1000,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    errors = [
        {"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": "Validasi gagal", "errors": errors})


@app.exception_handler(Exception)
async def unhandled_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Terjadi kesalahan pada server"})


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok", "service": "pli-backend", "time": utcnow().isoformat() + "Z"}


@app.get("/api/health/live", tags=["health"])
def health_live():
    return {"status": "alive", "service": "pli-backend", "time": utcnow().isoformat() + "Z"}


@app.get("/api/health/ready", tags=["health"])
def health_ready(request: Request, db=Depends(get_db)):
    from sqlalchemy.orm import Session as DBSession

    status_code, payload = health_service.readiness(db)
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/api/metrics", tags=["health"], response_class=PlainTextResponse)
def metrics():
    if not settings.metrics_enabled:
        return PlainTextResponse("metrics disabled\n", status_code=404)
    state = app.state.metrics
    lines = [
        "# HELP pli_requests_total Total permintaan yang diproses proses ini",
        "# TYPE pli_requests_total counter",
        f"pli_requests_total {state['requests']}",
        "# TYPE pli_request_errors_total counter",
        f"pli_request_errors_total {state['errors']}",
        "# TYPE pli_request_duration_seconds_total counter",
        f"pli_request_duration_seconds_total {state['total_duration_sec']:.6f}",
    ]
    for code, count in sorted(state["status"].items()):
        lines.append(f'pli_requests_by_status{{code="{code}"}} {count}')
    return PlainTextResponse("\n".join(lines) + "\n")


app.include_router(api_router)
