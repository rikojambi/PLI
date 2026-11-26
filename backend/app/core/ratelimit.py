"""Small in-memory fixed-window limiter (single-process dev/local deployment)."""
import time
from collections import defaultdict

from fastapi import HTTPException, Request

_hits: dict[tuple[str, str], list[float]] = defaultdict(list)


def enforce(request: Request, bucket: str, limit: int, window_seconds: int) -> None:
    ip = request.client.host if request.client else "unknown"
    key = (bucket, ip)
    now = time.monotonic()
    recent = [t for t in _hits[key] if now - t < window_seconds]
    if len(recent) >= limit:
        _hits[key] = recent
        raise HTTPException(status_code=429, detail="Terlalu banyak percobaan. Coba lagi beberapa saat.")
    recent.append(now)
    _hits[key] = recent


def reset() -> None:
    """Clear all windows. Used by the test suite for isolation."""
    _hits.clear()
