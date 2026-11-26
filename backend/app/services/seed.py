"""Idempotent demo data seeder. Demo passwords are random and never reused in production."""
import secrets
import string
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, settings
from app.core.security import hash_password
from app.db.base import utcnow
from app.models.academic import Class, ClassMember, Competency, Subject, TeacherClass
from app.models.ai import AIProvider
from app.models.core import AcademicYear, Role, School, Semester, User

DEMO_NPSN = "DEMO-0001"


def _password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#"
    return "D3mo-" + "".join(secrets.choice(alphabet) for _ in range(14))


def _credentials_path() -> Path | None:
    """Write demo credentials beside the active SQLite database.

    A clean-install check often points PLI_DATABASE_URL at a temporary file.
    Writing to the shared ``data/`` directory in that case would overwrite the
    credentials of the real local database, so the file always follows the DB.
    """
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        return None
    db_path = Path(settings.database_url[len(prefix):])
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path
    return db_path.with_name("demo_credentials.txt")


PROVIDER_SEED_ROWS = [
    ("ollama", "Ollama (lokal)", "ollama", "http://127.0.0.1:11434"),
    ("gemini", "Google Gemini", "gemini", "https://generativelanguage.googleapis.com/v1beta"),
    ("groq", "Groq", "openai_compatible", "https://api.groq.com/openai/v1"),
    ("openrouter", "OpenRouter", "openai_compatible", "https://openrouter.ai/api/v1"),
    ("huggingface", "Hugging Face Router", "openai_compatible", "https://router.huggingface.co/v1"),
    ("cerebras", "Cerebras", "openai_compatible", "https://api.cerebras.ai/v1"),
    ("mistral", "Mistral", "openai_compatible", "https://api.mistral.ai/v1"),
    ("openai_compatible", "OpenAI-compatible Lainnya", "openai_compatible", ""),
]


def _seed_providers(db: Session, school_id: str) -> int:
    """Add missing provider endpoints without overwriting admin changes."""
    existing = {
        row.name for row in db.query(AIProvider).filter(AIProvider.school_id == school_id).all()
    }
    added = 0
    for name, display, adapter, base_url in PROVIDER_SEED_ROWS:
        if name in existing:
            continue
        db.add(AIProvider(
            school_id=school_id,
            name=name,
            display_name=display,
            adapter=adapter,
            base_url=base_url,
            model="",  # admin must choose an available model; nothing is hardcoded
            embedding_model="",
            api_key_env=f"PLI_AI_{name.upper()}_API_KEY",
            is_active=name == "ollama",
            is_primary=name == "ollama",
            is_fallback=False,
            priority=10 if name == "ollama" else 100,
            input_cost_per_million=0.0,
            output_cost_per_million=0.0,
            config_json={"notes": "Model dan kuota harus diverifikasi administrator sebelum dipakai."},
        ))
        added += 1
    return added


def seed(db: Session) -> dict[str, str]:
    school = db.query(School).filter(School.npsn == DEMO_NPSN).first()
    if school is not None:
        added = _seed_providers(db, school.id)
        if added:
            db.commit()
        return {"status": "already_seeded", "providers_added": str(added)}

    roles = {name: Role(name=name, description=desc) for name, desc in {
        "admin": "Administrator sekolah",
        "teacher": "Guru / pendidik",
        "student": "Peserta didik",
    }.items()}
    db.add_all(roles.values())
    db.flush()

    school = School(
        name="SMK Negeri Contoh",
        npsn=DEMO_NPSN,
        address="Jl. Pendidikan No. 1, Kota Contoh",
        phone="021-0000000",
        email="admin@contoh.sch.id",
    )
    db.add(school)
    db.flush()

    now = utcnow()
    year = AcademicYear(
        school_id=school.id,
        name="2026/2027",
        start_date=now.replace(month=7, day=1),
        end_date=now.replace(year=now.year + 1, month=6, day=30),
        is_active=True,
    )
    db.add(year)
    db.flush()
    semester = Semester(
        academic_year_id=year.id,
        name="Ganjil",
        start_date=now.replace(month=7, day=1),
        end_date=now.replace(month=12, day=31),
        is_active=True,
    )
    db.add(semester)

    subjects = [
        Subject(school_id=school.id, code="MTK", name="Matematika", color="#6366f1"),
        Subject(school_id=school.id, code="Bindo", name="Bahasa Indonesia", color="#0ea5e9"),
        Subject(school_id=school.id, code="Bing", name="Bahasa Inggris", color="#f59e0b"),
        Subject(school_id=school.id, code="PKJ", name="Produktif Kejuruan", color="#10b981"),
    ]
    db.add_all(subjects)
    db.flush()

    db.add_all([
        Competency(subject_id=subjects[0].id, code="MTK-K1", name="Bilangan dan operasi", order_index=1),
        Competency(subject_id=subjects[0].id, code="MTK-K2", name="Barisan dan deret", order_index=2,
                   prerequisite_codes=["MTK-K1"]),
        Competency(subject_id=subjects[1].id, code="BIN-K1", name="Ide pokok paragraf", order_index=1),
        Competency(subject_id=subjects[3].id, code="PKJ-K1", name="Dasar pemrograman", order_index=1),
    ])

    credentials: dict[str, str] = {}
    accounts = [
        ("admin", "Administrator", "admin", None),
        ("guru1", "Guru Contoh", "teacher", None),
        ("siswa1", "Siswa Contoh", "student", "2026001"),
        ("siswa2", "Siswa Kedua", "student", "2026002"),
    ]
    users = {}
    for username, full_name, role, student_number in accounts:
        pwd = _password() if settings.demo_mode else "PLEASE-CHANGE-ME-123"
        user = User(
            school_id=school.id,
            role_id=roles[role].id,
            username=username,
            full_name=full_name,
            email=f"{username}@contoh.sch.id",
            password_hash=hash_password(pwd),
            student_number=student_number,
            must_change_password=True,
        )
        db.add(user)
        users[username] = user
        credentials[username] = pwd
    db.flush()

    klass = Class(
        school_id=school.id,
        academic_year_id=year.id,
        semester_id=semester.id,
        name="XII RPL 1",
        grade_level="12",
        homeroom_teacher_id=users["guru1"].id,
    )
    db.add(klass)
    db.flush()
    db.add_all([
        ClassMember(class_id=klass.id, user_id=users["siswa1"].id, student_number="2026001"),
        ClassMember(class_id=klass.id, user_id=users["siswa2"].id, student_number="2026002"),
        TeacherClass(class_id=klass.id, teacher_id=users["guru1"].id, subject_id=subjects[0].id),
    ])

    # Fase 4: provider endpoints are known, but NO model id is assumed. An
    # administrator must discover/verify models before the router can use them.
    _seed_providers(db, school.id)

    db.commit()

    cred_path = _credentials_path()
    if cred_path is not None:
        cred_path.parent.mkdir(parents=True, exist_ok=True)
        cred_path.write_text(
            "AKUN DEMO - HANYA UNTUK PENGUJIAN LOKAL. JANGAN DIPAKAI DI PRODUKSI.\n"
            + "\n".join(f"{u}: {p}" for u, p in credentials.items())
            + "\n",
            encoding="utf-8",
        )
        try:
            cred_path.chmod(0o600)
        except OSError:
            pass
    return {"status": "seeded", "credentials_file": str(cred_path)}
