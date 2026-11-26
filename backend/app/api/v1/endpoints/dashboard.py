"""Fase 5: scoped dashboard filters, progress series, profiles and exports."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session as DBSession

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.core import User
from app.services import dashboard as service
from app.services.export import build_pdf, build_xlsx, safe_filename

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _args(
    class_id: str | None,
    subject_id: str | None,
    competency_id: str | None,
    student_id: str | None,
    period: str | None,
    date_from: str | None,
    date_to: str | None,
) -> dict:
    return {
        "class_id": class_id,
        "subject_id": subject_id,
        "competency_id": competency_id,
        "student_id": student_id,
        "period": period,
        "date_from": date_from,
        "date_to": date_to,
    }


@router.get("/filters", response_model=dict)
def filters(
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    return service.dashboard_filters(db, user)


@router.get("/overview", response_model=dict)
def overview(
    class_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    student_id: str | None = None,
    period: str | None = "30d",
    date_from: str | None = None,
    date_to: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    return service.overview(db, user, **_args(class_id, subject_id, competency_id, student_id, period, date_from, date_to))


@router.get("/progress", response_model=dict)
def progress(
    class_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    student_id: str | None = None,
    period: str | None = "30d",
    date_from: str | None = None,
    date_to: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    return service.progress(db, user, **_args(class_id, subject_id, competency_id, student_id, period, date_from, date_to))


@router.get("/students/{student_id}/profile", response_model=dict)
def profile(
    student_id: str,
    class_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    period: str | None = "90d",
    date_from: str | None = None,
    date_to: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    args = _args(class_id, subject_id, competency_id, None, period, date_from, date_to)
    args.pop("student_id")
    return service.student_profile(db, user, student_id, **args)


@router.get("/export")
def export(
    format: Literal["xlsx", "pdf"] = Query("xlsx", description="xlsx atau pdf"),
    class_id: str | None = None,
    subject_id: str | None = None,
    competency_id: str | None = None,
    student_id: str | None = None,
    period: str | None = "30d",
    date_from: str | None = None,
    date_to: str | None = None,
    user: User = Depends(require_roles("admin", "teacher", "student")),
    db: DBSession = Depends(get_db),
):
    data = service.export_data(
        db,
        user,
        **_args(class_id, subject_id, competency_id, student_id, period, date_from, date_to),
    )
    scope = "data-saya" if user.role.name == "student" else "data-sekolah"
    if format == "pdf":
        content = build_pdf(data, scope)
        media_type = "application/pdf"
    else:
        content = build_xlsx(data)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    filename = safe_filename(f"pli-{scope}", format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
