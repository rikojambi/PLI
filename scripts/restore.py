"""Restore SQLite PLI dari backup terenkripsi (Fase 6).

Hentikan server sebelum restore. Backup lama plaintext masih dapat dipulihkan,
tetapi checksum akan tetap diverifikasi bila berkas .sha256 tersedia.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
from app.services.backup_crypto import restore_backup  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("Penggunaan: python scripts/restore.py backups/pli-YYYYMMDD-HHMMSS.db.enc")
        sys.exit(1)
    source = Path(sys.argv[1])
    if not source.is_absolute():
        source = PROJECT_ROOT / source
    source = source.resolve()
    backups = (PROJECT_ROOT / "backups").resolve()
    if backups not in source.parents and source.parent != backups:
        print("File backup harus berada di folder backups/.")
        sys.exit(1)
    try:
        result = restore_backup(source)
    except (RuntimeError, FileNotFoundError, ValueError) as error:
        print(f"Restore gagal: {error}")
        sys.exit(1)
    print(f"Restore selesai dari {source} ke {result['target']}")
    if result["safety"]:
        print(f"Database lama disimpan sebagai: {result['safety']}")
    print("Jalankan ulang backend setelah ini.")


if __name__ == "__main__":
    main()
