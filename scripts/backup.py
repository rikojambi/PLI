"""Backup SQLite PLI ke backups/ dengan enkripsi Fernet (Fase 6).

Kunci dibaca hanya dari PLI_BACKUP_ENCRYPTION_KEY di server/.env. Tanpa kunci,
skrip berhenti dan tidak membuat backup plaintext baru.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import settings  # noqa: E402
from app.services.backup_crypto import create_backup  # noqa: E402


def main() -> None:
    try:
        result = create_backup()
    except (RuntimeError, FileNotFoundError) as error:
        print(f"Backup gagal: {error}")
        sys.exit(1)
    print(f"Backup terenkripsi selesai: {result['path']}")
    print(f"Metadata: {result['metadata_path']}")
    print(f"SHA-256 ciphertext: {result['checksum_sha256']}")
    print(f"Database sumber: {settings.database_url}")


if __name__ == "__main__":
    main()
