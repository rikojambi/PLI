"""Verifikasi instalasi bersih sampai Fase 6 tanpa mengubah kredensial database utama.

Jalankan dari folder proyek:

    python scripts\\fase3_clean_check.py

Skrip ini membuat database SQLite sementara di luar `data/`, menjalankan Alembic
hingg head, menjalankan seed, lalu memeriksa skema Fase 3, Fase 4, dan Fase 6. Berkas kredensial demo
harus ditulis di samping database sementara, bukan menimpa
`data/demo_credentials.txt`.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
CANONICAL_CREDENTIALS = PROJECT_ROOT / "data" / "demo_credentials.txt"


def _digest(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    canonical_before = _digest(CANONICAL_CREDENTIALS)

    with tempfile.TemporaryDirectory(prefix="pli-fase3-clean-") as folder:
        target = Path(folder)
        db_path = target / "pli_clean.db"
        env = dict(os.environ)
        env["PLI_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"

        for args in (
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            [sys.executable, "-m", "app.db.init_db"],
        ):
            result = subprocess.run(args, cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
            print("CMD", " ".join(args), "exit", result.returncode)
            if result.returncode:
                print(result.stdout)
                print(result.stderr)
                return result.returncode

        with closing(sqlite3.connect(db_path)) as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            question_columns = {row[1] for row in conn.execute("PRAGMA table_info(questions)")}
            bkt_columns = {row[1] for row in conn.execute("PRAGMA table_info(bkt_history)")}
            provider_columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_providers)")}
            usage_columns = {row[1] for row in conn.execute("PRAGMA table_info(ai_usage_logs)")}
            tutor_columns = {row[1] for row in conn.execute("PRAGMA table_info(tutor_messages)")}
            secret_columns = {row[1] for row in conn.execute("PRAGMA table_info(secret_rotations)")}
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            providers = conn.execute("SELECT COUNT(*) FROM ai_providers").fetchone()[0]
            hardcoded_models = conn.execute("SELECT COUNT(*) FROM ai_provider_models").fetchone()[0]

        credentials = target / "demo_credentials.txt"
        credential_text = credentials.read_text(encoding="utf-8") if credentials.exists() else ""
        expected_accounts = ("admin:", "guru1:", "siswa1:", "siswa2:")
        accounts_ok = all(account in credential_text for account in expected_accounts)
        canonical_unchanged = _digest(CANONICAL_CREDENTIALS) == canonical_before

        checks = {
            "DB_VERSION": version == "b6d1f7a9c2e4",
            "USERS": users == 4,
            "ADAPTIVE_PRACTICES": "adaptive_practices" in tables,
            "ENGINE_CONFIGS": "engine_configs" in tables,
            "QUESTION_GAP_CATEGORY": "gap_category" in question_columns,
            "BKT_EVIDENCE_ID": "evidence_id" in bkt_columns,
            "AI_PROVIDER_MODELS": "ai_provider_models" in tables,
            "GENERATED_CONTENTS": "generated_contents" in tables,
            "AI_PROVIDER_SCHOOL_SCOPE": "school_id" in provider_columns,
            "AI_USAGE_SCHOOL_SCOPE": "school_id" in usage_columns,
            "TUTOR_CLIENT_ID": "client_id" in tutor_columns,
            "SYNC_CONFLICTS": "sync_conflicts" in tables,
            "DELETION_REQUESTS": "deletion_requests" in tables,
            "SECRET_ROTATIONS": "secret_rotations" in tables,
            "NO_RAW_SECRET_IN_DB": not any(
                column in {"secret", "api_key", "api_key_value"} for column in secret_columns
            ),
            "SEEDED_PROVIDERS": providers == 8,
            "NO_HARDCODED_MODELS": hardcoded_models == 0,
            "TEMP_CREDENTIALS": accounts_ok,
            "CANONICAL_CREDENTIALS_UNCHANGED": canonical_unchanged,
        }
        print("DB_VERSION=", version)
        print("TABLES=", len(tables))
        print("USERS=", users)
        print("PROVIDERS=", providers)
        for key, passed in checks.items():
            print(f"{key}= {passed}")
        return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
