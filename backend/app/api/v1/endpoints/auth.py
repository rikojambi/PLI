"""Login, session, and password endpoints."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.ratelimit import enforce
from app.core.security import candidate_token_hashes, csrf_token, hash_password, new_token, token_hash, verify_password
from app.db.base import utcnow
from app.db.session import get_db
from app.models.core import Session, User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse, UserOut
from app.schemas.common import Message
from app.services.audit import log_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
) -> LoginResponse:
    enforce(request, "login", limit=10, window_seconds=300)
    user = db.scalar(
        select(User).where(
            (User.username == payload.username) | (User.email == payload.username)
        )
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = utcnow() + timedelta(minutes=15)
                user.failed_login_count = 0
            db.commit()
        raise HTTPException(status_code=401, detail="Username atau password salah")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Akun dinonaktifkan. Hubungi administrator.")
    if user.locked_until and user.locked_until > utcnow():
        raise HTTPException(status_code=423, detail="Akun sementara terkunci. Coba lagi nanti.")

    raw = new_token()
    session = Session(
        user_id=user.id,
        token_hash=token_hash(raw),
        csrf_token=csrf_token(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:300],
        created_at=utcnow(),
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        last_seen_at=utcnow(),
    )
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    db.add(session)
    log_audit(db, user, "login", "user", user.id, {"method": "password"}, request)
    db.commit()

    response.set_cookie(
        key=settings.cookie_name,
        value=raw,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    return LoginResponse(csrf_token=session.csrf_token, user=UserOut.model_validate(user))


@router.post("/logout", response_model=Message)
def logout(
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Message:
    raw = request.cookies.get(settings.cookie_name, "")
    session = db.scalar(select(Session).where(Session.token_hash.in_(candidate_token_hashes(raw))))
    if session:
        session.revoked_at = utcnow()
        log_audit(db, user, "logout", "user", user.id, {}, request)
        db.commit()
    response.delete_cookie(settings.cookie_name, path="/")
    return Message(message="Berhasil keluar")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=Message)
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Message:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password lama salah")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    # Revoke all other sessions so a stolen session cannot survive a password change.
    raw = request.cookies.get(settings.cookie_name, "")
    current_hashes = set(candidate_token_hashes(raw))
    for session in db.scalars(select(Session).where(Session.user_id == user.id)):
        if session.token_hash not in current_hashes:
            session.revoked_at = utcnow()
    log_audit(db, user, "change_password", "user", user.id, {}, request)
    db.commit()
    return Message(message="Password berhasil diubah")
