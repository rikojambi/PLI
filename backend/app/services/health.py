"""Fase 6 health and monitoring checks without exposing secrets."""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session as DBSession

from app.core.config import DATA_DIR, settings

EXPECTED_REVISION = "b6d1f7a9c2e4"


def database_ok(db: DBSession) -> bool:
    try:
        return db.execute(text("SELECT 1")).scalar_one() == 1
    except Exception:
        return False


def migration_head(db: DBSession) -> str | None:
    try:
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        return None


def detailed(db: DBSession) -> dict[str, Any]:
    tables = len(inspect(db.get_bind()).get_table_names())
    writable = DATA_DIR.exists() and os.access(DATA_DIR, os.W_OK)
    head = migration_head(db)
    checks = {
        "database": database_ok(db),
        "data_directory_writable": writable,
        "migration_current": head == EXPECTED_REVISION,
        "backup_key_configured": bool(settings.backup_encryption_key),
        "metrics_enabled": settings.metrics_enabled,
    }
    return {
        "status": "ok" if all(value for key, value in checks.items() if key != "backup_key_configured") else "degraded",
        "service": "pli-backend",
        "environment": settings.environment,
        "version": "6.0.0-fase6",
        "database_url_kind": settings.database_url.split(":", 1)[0],
        "tables": tables,
        "migration_head": head,
        "expected_migration_head": EXPECTED_REVISION,
        "checks": checks,
    }


def readiness(db: DBSession) -> tuple[int, dict[str, Any]]:
    database = database_ok(db)
    writable = DATA_DIR.exists() and os.access(DATA_DIR, os.W_OK)
    ready = database and writable
    return (
        200 if ready else 503,
        {
            "status": "ready" if ready else "not_ready",
            "database": database,
            "data_directory_writable": writable,
            "migration_head": migration_head(db),
        },
    )
