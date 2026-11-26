"""Password hashing and opaque session token helpers.

Fase 6: session tokens are HMAC-bound to a server-side secret. A previous key
remains usable during rotation so an administrator can rotate without forcing
every user to log in again. The legacy plain SHA-256 hash is still accepted for
sessions created before this upgrade, but new sessions always use the current
key. Raw secrets never leave the server.
"""
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


def new_token() -> str:
    return secrets.token_urlsafe(48)


def _hmac_hash(token: str, key: str) -> str:
    return hmac.new(key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def token_hash(token: str) -> str:
    """Hash a token with the current secret (used when creating sessions)."""
    return _hmac_hash(token, settings.secret_key)


def candidate_token_hashes(token: str) -> list[str]:
    """All hashes that may legitimately match a stored session."""
    values = [token_hash(token)]
    previous = settings.secret_key_previous
    if previous and previous != settings.secret_key:
        values.append(_hmac_hash(token, previous))
    # Backward compatibility with sessions created before Fase 6.
    values.append(hashlib.sha256(token.encode("utf-8")).hexdigest())
    return list(dict.fromkeys(values))


def key_hint(value: str | None) -> str | None:
    """Non-reversible label for audit records; never returns the raw secret."""
    if not value:
        return None
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{len(value)}:{digest}"


def csrf_token() -> str:
    return secrets.token_urlsafe(32)
