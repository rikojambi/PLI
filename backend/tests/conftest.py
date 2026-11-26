"""Test database + API client fixtures (isolated in-memory SQLite)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base, utcnow
from app.db.session import get_db
from app.main import app
from app.models import (  # noqa: F401 - register metadata
    AcademicYear,
    Class,
    ClassMember,
    Role,
    School,
    Semester,
    Subject,
    TeacherClass,
    User,
)

TEST_PASSWORD = "Testing12345!"


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(db_engine):
    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine, db):
    from app.core import ratelimit

    ratelimit.reset()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def fixtures(db):
    school = School(name="SMK Uji", npsn="TEST-1")
    db.add(school)
    db.flush()
    roles = {n: Role(name=n) for n in ("admin", "teacher", "student")}
    db.add_all(roles.values())
    db.flush()

    now = utcnow()
    year = AcademicYear(
        school_id=school.id,
        name="2026/2027",
        start_date=now,
        end_date=now,
        is_active=True,
    )
    db.add(year)
    db.flush()
    semester = Semester(
        academic_year_id=year.id, name="Ganjil", start_date=now, end_date=now, is_active=True
    )
    db.add(semester)
    db.flush()

    users = {}
    for username, role in [("admin", "admin"), ("guru", "teacher"), ("siswa", "student")]:
        user = User(
            school_id=school.id,
            role_id=roles[role].id,
            username=username,
            full_name=username.title(),
            password_hash=hash_password(TEST_PASSWORD),
        )
        db.add(user)
        users[username] = user
    db.flush()

    klass1 = Class(
        school_id=school.id,
        academic_year_id=year.id,
        semester_id=semester.id,
        name="XII A",
    )
    klass2 = Class(
        school_id=school.id,
        academic_year_id=year.id,
        semester_id=semester.id,
        name="XII B",
    )
    db.add_all([klass1, klass2])
    db.flush()
    db.add_all([
        ClassMember(class_id=klass1.id, user_id=users["siswa"].id),
        TeacherClass(class_id=klass1.id, teacher_id=users["guru"].id),
    ])
    db.commit()
    return {
        "school": school,
        "year": year,
        "semester": semester,
        "roles": roles,
        "users": users,
        "class1": klass1,
        "class2": klass2,
    }


def login(client: TestClient, username: str, password: str = TEST_PASSWORD):
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()
