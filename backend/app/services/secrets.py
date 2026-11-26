"""Server-side secret rotation.

The new key is generated here, written only to the backend `.env` file, and
never returned to the browser. The previous key is kept for one rotation cycle
so existing sessions remain valid; older keys are no longer accepted.
"""
from __future__ import annotations

import secrets
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.core.security import key_hint
from app.db.base import utcnow
from app.models.operations import SecretRotation


def _rewrite_env(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    original = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    keys = set(values)
    lines = [line for line in original if not any(line.strip().startswith(f"{key}=") for key in keys)]
    for line in original:
        if any(line.strip().startswith(f"{key}=") for key in keys):
            lines.append("# Rotasi Fase 6: nilai lama digantikan otomatis")
            break
    lines.extend(f"{key}={value}" for key, value in values.items())
    temp = path.with_name(path.name + ".tmp")
    temp.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    temp.replace(path)


def rotate_secret(
    db: DBSession | None,
    actor_id: str,
    *,
    env_path: Path | None = None,
    note: str | None = None,
) -> dict:
    """Rotate the HMAC secret and persist it outside the database."""
    old_key = settings.secret_key
    old_hint = key_hint(old_key)
    previous_key = settings.secret_key_previous
    new_key = secrets.token_urlsafe(48)
    target = env_path or settings.env_file_path
    values = {
        "PLI_SECRET_KEY": new_key,
        "PLI_SECRET_KEY_PREVIOUS": old_key,
    }
    _rewrite_env(target, values)

    settings.secret_key = new_key
    settings.secret_key_previous = old_key

    if db is not None:
        db.add(SecretRotation(
            performed_by=actor_id,
            key_hint=key_hint(new_key),
            previous_key_hint=old_hint,
            note=note or "Rotasi kunci HMAC sesi",
        ))
        db.commit()

    return {
        "rotated_at": utcnow().isoformat() + "Z",
        "key_hint": key_hint(new_key),
        "previous_key_hint": old_hint,
        "superseded_key_hint": key_hint(previous_key) if previous_key else None,
        "env_file": str(target),
        "note": "Kunci baru hanya tersimpan di server. Sesi lama tetap terverifikasi satu siklus rotasi.",
    }
