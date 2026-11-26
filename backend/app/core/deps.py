"""Authentication, CSRF and role/tenant scoping dependencies."""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.security import candidate_token_hashes
from app.db.base import utcnow
from app.db.session import get_db
from app.models.core import Session, User


def _unauthorized(detail: str = "Autentikasi diperlukan") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Session"},
    )


def get_current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    raw = request.cookies.get(settings.cookie_name)
    if not raw:
        raise _unauthorized()

    session = db.scalar(select(Session).where(Session.token_hash.in_(candidate_token_hashes(raw))))
    if session is None or session.revoked_at is not None:
        raise _unauthorized("Sesi tidak valid")
    if session.expires_at <= utcnow():
        raise _unauthorized("Sesi berakhir, silakan masuk kembali")

    user = session.user
    if not user.is_active:
        raise _unauthorized("Akun dinonaktifkan")

    # Double-submit CSRF: cookie is httpOnly, token is exposed once at login
    # and must be echoed in a header for every state-changing request.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or supplied != session.csrf_token:
            raise HTTPException(status_code=403, detail="Token CSRF tidak valid atau hilang")

    session.last_seen_at = utcnow()
    db.commit()
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in roles:
            raise HTTPException(status_code=403, detail="Akses ditolak untuk peran ini")
        return user

    return checker


def require_admin(user: User = Depends(require_roles("admin"))) -> User:
    return user


def require_teacher(user: User = Depends(require_roles("admin", "teacher"))) -> User:
    return user


def assert_school_scope(user: User, school_id: str) -> None:
    if user.school_id != school_id:
        raise HTTPException(status_code=403, detail="Data di luar sekolah Anda tidak dapat diakses")


def teacher_class_ids(db: DBSession, user: User) -> list[str]:
    """Class IDs a teacher is allowed to see (empty => no classes)."""
    from app.models.academic import TeacherClass

    return list(
        db.scalars(
            select(TeacherClass.class_id).where(TeacherClass.teacher_id == user.id)
        ).all()
    )
