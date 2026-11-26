"""Demo credential files must follow the active database, not a shared folder."""
from pathlib import Path

from app.core.config import PROJECT_ROOT, settings
from app.models.ai import AIProvider
from app.models.core import School
from app.services.seed import seed


def test_seed_writes_credentials_beside_active_database(tmp_path, monkeypatch, db):
    canonical = PROJECT_ROOT / "data" / "demo_credentials.txt"
    before = canonical.read_text(encoding="utf-8") if canonical.exists() else None

    custom_db = tmp_path / "clean.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{custom_db.as_posix()}")

    result = seed(db)
    assert result["status"] == "seeded"

    custom_credentials = tmp_path / "demo_credentials.txt"
    assert custom_credentials.exists()
    assert "admin:" in custom_credentials.read_text(encoding="utf-8")

    after = canonical.read_text(encoding="utf-8") if canonical.exists() else None
    assert after == before


def test_seed_upgrade_adds_missing_providers_without_changing_credentials(tmp_path, monkeypatch, db):
    custom_db = tmp_path / "upgrade.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{custom_db.as_posix()}")

    seed(db)
    school = db.query(School).first()
    db.query(AIProvider).filter(AIProvider.name.in_(["groq", "mistral"])).delete(
        synchronize_session=False
    )
    db.commit()
    credentials = tmp_path / "demo_credentials.txt"
    before = credentials.read_text(encoding="utf-8")

    result = seed(db)

    names = {row.name for row in db.query(AIProvider).all()}
    assert len(names) == 8
    assert {"groq", "mistral"} <= names
    assert result["providers_added"] == "2"
    assert credentials.read_text(encoding="utf-8") == before
