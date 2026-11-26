"""Fase 6 encrypted SQLite backup/restore helpers.

A backup contains student personal data. When `PLI_BACKUP_ENCRYPTION_KEY` is
configured, the archive is a Fernet ciphertext and the sidecar records only a
checksum of that ciphertext. The key is never written to the archive.
"""
from __future__ import annotations

import hashlib
import json
import os
from contextlib import closing
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import PROJECT_ROOT, settings


def sqlite_source_path() -> Path:
    if not settings.database_url.startswith("sqlite"):
        raise RuntimeError("Backup otomatis hanya mendukung SQLite. Gunakan pg_dump untuk PostgreSQL.")
    raw = settings.database_url.split("sqlite:///", 1)[1]
    path = Path(raw)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _fernet(key: str | None) -> Fernet:
    value = key or settings.backup_encryption_key
    if not value:
        raise RuntimeError("PLI_BACKUP_ENCRYPTION_KEY belum diisi. Buat dengan Fernet.generate_key().")
    try:
        return Fernet(value.encode("utf-8") if isinstance(value, str) else value)
    except (ValueError, TypeError):
        raise RuntimeError("PLI_BACKUP_ENCRYPTION_KEY bukan kunci Fernet yang valid") from None


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_backup(
    source_db: Path | None = None,
    backup_dir: Path | None = None,
    key: str | None = None,
) -> dict:
    source = (source_db or sqlite_source_path()).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Database tidak ditemukan: {source}")
    destination_dir = (backup_dir or (PROJECT_ROOT / "backups")).resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    cipher = _fernet(key)

    with tempfile.TemporaryDirectory(prefix="pli-backup-") as folder:
        snapshot = Path(folder) / "pli.db"
        with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(snapshot)) as dst:
            src.backup(dst)
            src.commit()
            dst.commit()
        ciphertext = cipher.encrypt(snapshot.read_bytes())

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = destination_dir / f"pli-{stamp}.db.enc"
    target.write_bytes(ciphertext)
    metadata = {
        "algorithm": "fernet",
        "checksum_sha256": _digest(ciphertext),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": source.name,
        "key_note": "Kunci berada di server melalui PLI_BACKUP_ENCRYPTION_KEY",
    }
    meta_path = target.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {
        "path": target,
        "metadata_path": meta_path,
        "checksum_sha256": metadata["checksum_sha256"],
        "encrypted": True,
    }


def restore_backup(
    source_path: Path,
    target_db: Path | None = None,
    key: str | None = None,
) -> dict:
    source = source_path.resolve()
    if not source.exists():
        raise FileNotFoundError(f"File backup tidak ditemukan: {source}")
    target = (target_db or sqlite_source_path()).resolve()
    data = source.read_bytes()

    if source.suffix == ".enc":
        meta_path = source.with_suffix(".meta.json")
        if not meta_path.exists():
            raise RuntimeError("Metadata backup tidak ditemukan; restore ditolak")
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if metadata.get("algorithm") != "fernet":
            raise RuntimeError("Algoritma backup tidak dikenal")
        if _digest(data) != metadata.get("checksum_sha256"):
            raise RuntimeError("Checksum backup tidak cocok; restore dibatalkan")
        try:
            plaintext = _fernet(key).decrypt(data)
        except InvalidToken:
            raise RuntimeError("Kunci backup salah atau berkas rusak; restore dibatalkan") from None
        encrypted = True
    else:
        # Legacy plaintext backup: checksum sidecar is verified when present.
        sidecar = source.with_suffix(".sha256")
        if sidecar.exists():
            expected = sidecar.read_text(encoding="utf-8").split(maxsplit=1)[0]
            if _digest(data) != expected:
                raise RuntimeError("Checksum backup lama tidak cocok; restore dibatalkan")
        plaintext = data
        encrypted = False

    target.parent.mkdir(parents=True, exist_ok=True)
    safety = target.with_suffix(".before-restore.db")
    if target.exists():
        shutil.copyfile(target, safety)
    temp = target.with_name(target.name + ".restore.tmp")
    temp.write_bytes(plaintext)
    os.replace(temp, target)
    return {
        "target": target,
        "safety": safety if safety.exists() else None,
        "encrypted": encrypted,
        "bytes": len(plaintext),
    }
