"""Administrator endpoints: school, users, academic structure, audit."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.deps import assert_school_scope, require_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models.academic import Class, ClassMember, Competency, Subject, TeacherClass
from app.models.core import AcademicYear, AuditLog, Role, School, Semester, User
from app.schemas.admin import (
    AcademicYearCreate,
    ClassCreate,
    ClassMemberUpdate,
    CompetencyCreate,
    PasswordReset,
    SchoolUpdate,
    SemesterCreate,
    SubjectCreate,
    TeacherAssign,
    UserCreate,
    UserUpdate,
)
from app.schemas.auth import UserOut
from app.schemas.common import Message, ORMModel, Page
from app.services.audit import log_audit

router = APIRouter(prefix="/admin", tags=["admin"])


class SchoolSchema(ORMModel):
    id: str
    name: str
    npsn: str | None
    address: str | None
    phone: str | None
    email: str | None


class AcademicYearSchema(ORMModel):
    id: str
    name: str
    start_date: datetime
    end_date: datetime
    is_active: bool


class SemesterSchema(ORMModel):
    id: str
    academic_year_id: str
    name: str
    start_date: datetime
    end_date: datetime
    is_active: bool


class TeacherClassSchema(ORMModel):
    id: str
    teacher_id: str
    subject_id: str | None


class ClassSchema(ORMModel):
    id: str
    name: str
    academic_year_id: str
    semester_id: str
    grade_level: str | None
    homeroom_teacher_id: str | None
    description: str | None
    is_active: bool
    student_count: int = 0
    teachers: list[TeacherClassSchema] = []


class StudentBrief(ORMModel):
    id: str
    full_name: str
    username: str
    student_number: str | None
    email: str | None
    is_active: bool


class SubjectSchema(ORMModel):
    id: str
    code: str
    name: str
    description: str | None
    color: str | None
    is_active: bool


class CompetencySchema(ORMModel):
    id: str
    subject_id: str
    code: str
    name: str
    description: str | None
    grade_level: str | None
    parent_id: str | None
    order_index: int
    is_active: bool


class AuditSchema(ORMModel):
    id: str
    actor_id: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    details_json: dict
    ip_address: str | None
    created_at: datetime


def _class_schema(db: DBSession, row: Class) -> ClassSchema:
    count = db.scalar(
        select(func.count(ClassMember.id)).where(ClassMember.class_id == row.id)
    ) or 0
    teachers = db.scalars(select(TeacherClass).where(TeacherClass.class_id == row.id)).all()
    data = ClassSchema.model_validate(row)
    data.student_count = count
    data.teachers = [TeacherClassSchema.model_validate(t) for t in teachers]
    return data


# ---------- School ----------

@router.get("/school", response_model=SchoolSchema)
def get_school(
    admin: User = Depends(require_admin), db: DBSession = Depends(get_db)
) -> SchoolSchema:
    school = db.get(School, admin.school_id)
    return SchoolSchema.model_validate(school)


@router.put("/school", response_model=SchoolSchema)
def update_school(
    payload: SchoolUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
) -> SchoolSchema:
    school = db.get(School, admin.school_id)
    for field, value in payload.model_dump().items():
        setattr(school, field, value)
    log_audit(db, admin, "update_school", "school", school.id, payload.model_dump(), request)
    db.commit()
    return SchoolSchema.model_validate(school)


# ---------- Users ----------

@router.get("/users", response_model=dict)
def list_users(
    role: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
) -> dict:
    query = select(User).where(User.school_id == admin.school_id)
    if role:
        query = query.join(Role).where(Role.name == role)
    if search:
        like = f"%{search.lower()}%"
        query = query.where(
            (func.lower(User.full_name).like(like)) | (func.lower(User.username).like(like))
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(User.created_at.desc()).limit(limit).offset(offset)).all()
    return {
        "items": [UserOut.model_validate(u).model_dump(mode="json") for u in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/users", response_model=dict, status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
) -> dict:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="Username sudah digunakan")
    if payload.email and db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email sudah digunakan")
    role = db.scalar(select(Role).where(Role.name == payload.role))
    if role is None:
        raise HTTPException(status_code=400, detail="Peran tidak ditemukan")

    user = User(
        school_id=admin.school_id,
        role_id=role.id,
        username=payload.username,
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        student_number=payload.student_number,
        password_hash=hash_password(payload.password),
        must_change_password=True,
    )
    db.add(user)
    db.flush()

    if payload.role == "student" and payload.class_id:
        klass = db.get(Class, payload.class_id)
        if klass is None or klass.school_id != admin.school_id:
            raise HTTPException(status_code=400, detail="Kelas tidak valid")
        db.add(ClassMember(class_id=klass.id, user_id=user.id))
    if payload.role == "teacher":
        db.add(TeacherClass(class_id=payload.class_id, teacher_id=user.id)) if payload.class_id else None

    log_audit(db, admin, "create_user", "user", user.id, {"role": payload.role}, request)
    db.commit()
    return UserOut.model_validate(user).model_dump(mode="json")


@router.patch("/users/{user_id}", response_model=dict)
def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
) -> dict:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    assert_school_scope(admin, user.school_id)
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="Tidak dapat menonaktifkan akun sendiri")

    data = payload.model_dump(exclude_unset=True)
    if "role" in data:
        role = db.scalar(select(Role).where(Role.name == data.pop("role")))
        if role is None:
            raise HTTPException(status_code=400, detail="Peran tidak ditemukan")
        user.role_id = role.id
    for field, value in data.items():
        setattr(user, field, value)
    log_audit(db, admin, "update_user", "user", user.id, payload.model_dump(mode="json"), request)
    db.commit()
    return UserOut.model_validate(user).model_dump(mode="json")


@router.post("/users/{user_id}/reset-password", response_model=Message)
def reset_password(
    user_id: str,
    payload: PasswordReset,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
) -> Message:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    assert_school_scope(admin, user.school_id)
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = True
    log_audit(db, admin, "reset_password", "user", user.id, {}, request)
    db.commit()
    return Message(message="Password berhasil direset")


# ---------- Academic years and semesters ----------

@router.get("/academic-years", response_model=list[AcademicYearSchema])
def list_years(admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    return db.scalars(
        select(AcademicYear).where(AcademicYear.school_id == admin.school_id).order_by(AcademicYear.start_date.desc())
    ).all()


@router.post("/academic-years", response_model=AcademicYearSchema, status_code=201)
def create_year(
    payload: AcademicYearCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    row = AcademicYear(school_id=admin.school_id, **payload.model_dump())
    if row.is_active:
        db.query(AcademicYear).filter(AcademicYear.school_id == admin.school_id).update({"is_active": False})
    db.add(row)
    log_audit(db, admin, "create_academic_year", "academic_year", row.id, {}, request)
    db.commit()
    return row


@router.get("/semesters", response_model=list[SemesterSchema])
def list_semesters(
    academic_year_id: str | None = None,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    query = select(Semester).join(AcademicYear).where(AcademicYear.school_id == admin.school_id)
    if academic_year_id:
        query = query.where(Semester.academic_year_id == academic_year_id)
    return db.scalars(query.order_by(Semester.start_date.desc())).all()


@router.post("/semesters", response_model=SemesterSchema, status_code=201)
def create_semester(
    payload: SemesterCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    year = db.get(AcademicYear, payload.academic_year_id)
    if not year or year.school_id != admin.school_id:
        raise HTTPException(status_code=400, detail="Tahun ajaran tidak valid")
    row = Semester(**payload.model_dump())
    if row.is_active:
        db.query(Semester).filter(Semester.academic_year_id == year.id).update({"is_active": False})
    db.add(row)
    log_audit(db, admin, "create_semester", "semester", row.id, {}, request)
    db.commit()
    return row


# ---------- Subjects and competencies ----------

@router.get("/subjects", response_model=list[SubjectSchema])
def list_subjects(admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    return db.scalars(select(Subject).where(Subject.school_id == admin.school_id).order_by(Subject.name)).all()


@router.post("/subjects", response_model=SubjectSchema, status_code=201)
def create_subject(
    payload: SubjectCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    if db.scalar(select(Subject).where(Subject.school_id == admin.school_id, Subject.code == payload.code)):
        raise HTTPException(status_code=409, detail="Kode mata pelajaran sudah digunakan")
    row = Subject(school_id=admin.school_id, **payload.model_dump())
    db.add(row)
    log_audit(db, admin, "create_subject", "subject", row.id, {}, request)
    db.commit()
    return row


@router.get("/competencies", response_model=list[CompetencySchema])
def list_competencies(
    subject_id: str | None = None,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    query = select(Competency).join(Subject).where(Subject.school_id == admin.school_id)
    if subject_id:
        query = query.where(Competency.subject_id == subject_id)
    return db.scalars(query.order_by(Competency.order_index, Competency.code)).all()


@router.post("/competencies", response_model=CompetencySchema, status_code=201)
def create_competency(
    payload: CompetencyCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    subject = db.get(Subject, payload.subject_id)
    if not subject or subject.school_id != admin.school_id:
        raise HTTPException(status_code=400, detail="Mata pelajaran tidak valid")
    if db.scalar(
        select(Competency).where(Competency.subject_id == subject.id, Competency.code == payload.code)
    ):
        raise HTTPException(status_code=409, detail="Kode kompetensi sudah digunakan")
    row = Competency(**payload.model_dump())
    db.add(row)
    log_audit(db, admin, "create_competency", "competency", row.id, {}, request)
    db.commit()
    return row


# ---------- Classes ----------

@router.get("/classes", response_model=list[ClassSchema])
def list_classes(admin: User = Depends(require_admin), db: DBSession = Depends(get_db)):
    rows = db.scalars(
        select(Class).where(Class.school_id == admin.school_id).order_by(Class.name)
    ).all()
    return [_class_schema(db, row) for row in rows]


@router.post("/classes", response_model=ClassSchema, status_code=201)
def create_class(
    payload: ClassCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    year = db.get(AcademicYear, payload.academic_year_id)
    semester = db.get(Semester, payload.semester_id)
    if not year or year.school_id != admin.school_id or not semester:
        raise HTTPException(status_code=400, detail="Tahun ajaran atau semester tidak valid")
    if semester.academic_year_id != year.id:
        raise HTTPException(status_code=400, detail="Semester tidak sesuai tahun ajaran")
    if db.scalar(
        select(Class).where(
            Class.school_id == admin.school_id,
            Class.academic_year_id == year.id,
            Class.semester_id == semester.id,
            Class.name == payload.name,
        )
    ):
        raise HTTPException(status_code=409, detail="Kelas dengan nama ini sudah ada")

    row = Class(
        school_id=admin.school_id,
        academic_year_id=year.id,
        semester_id=semester.id,
        name=payload.name,
        grade_level=payload.grade_level,
        homeroom_teacher_id=payload.homeroom_teacher_id,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(row)
    db.flush()
    _sync_class_members(db, row.id, payload.student_ids, admin.school_id)
    for teacher_id in payload.teacher_ids:
        teacher = db.get(User, teacher_id)
        if not teacher or teacher.school_id != admin.school_id or teacher.role.name != "teacher":
            raise HTTPException(status_code=400, detail="Guru tidak valid")
        db.add(TeacherClass(class_id=row.id, teacher_id=teacher_id))
    log_audit(db, admin, "create_class", "class", row.id, {"name": row.name}, request)
    db.commit()
    return _class_schema(db, row)


@router.patch("/classes/{class_id}", response_model=ClassSchema)
def update_class(
    class_id: str,
    payload: ClassCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    row = db.get(Class, class_id)
    if not row:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    assert_school_scope(admin, row.school_id)
    row.name = payload.name
    row.grade_level = payload.grade_level
    row.homeroom_teacher_id = payload.homeroom_teacher_id
    row.description = payload.description
    row.is_active = payload.is_active
    _sync_class_members(db, row.id, payload.student_ids, admin.school_id)
    db.query(TeacherClass).filter(TeacherClass.class_id == row.id).delete()
    for teacher_id in payload.teacher_ids:
        teacher = db.get(User, teacher_id)
        if not teacher or teacher.school_id != admin.school_id:
            raise HTTPException(status_code=400, detail="Guru tidak valid")
        db.add(TeacherClass(class_id=row.id, teacher_id=teacher_id))
    log_audit(db, admin, "update_class", "class", row.id, {"name": row.name}, request)
    db.commit()
    return _class_schema(db, row)


@router.put("/classes/{class_id}/members", response_model=ClassSchema)
def set_class_members(
    class_id: str,
    payload: ClassMemberUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    row = db.get(Class, class_id)
    if not row:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    assert_school_scope(admin, row.school_id)
    _sync_class_members(db, row.id, payload.student_ids, admin.school_id)
    log_audit(db, admin, "set_class_members", "class", row.id, {}, request)
    db.commit()
    return _class_schema(db, row)


@router.get("/classes/{class_id}/students", response_model=list[StudentBrief])
def class_students(
    class_id: str,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    row = db.get(Class, class_id)
    if not row:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    assert_school_scope(admin, row.school_id)
    users = db.scalars(
        select(User).join(ClassMember).where(ClassMember.class_id == class_id).order_by(User.full_name)
    ).all()
    return users


@router.post("/classes/{class_id}/teachers", response_model=Message)
def assign_teacher(
    class_id: str,
    payload: TeacherAssign,
    request: Request,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    row = db.get(Class, class_id)
    if not row:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    assert_school_scope(admin, row.school_id)
    teacher = db.get(User, payload.teacher_id)
    if not teacher or teacher.school_id != admin.school_id or teacher.role.name != "teacher":
        raise HTTPException(status_code=400, detail="Guru tidak valid")
    subject_filter = (
        TeacherClass.subject_id.is_(None)
        if payload.subject_id is None
        else TeacherClass.subject_id == payload.subject_id
    )
    exists = db.scalar(
        select(TeacherClass).where(
            TeacherClass.class_id == class_id,
            TeacherClass.teacher_id == teacher.id,
            subject_filter,
        )
    )
    if not exists:
        db.add(TeacherClass(class_id=class_id, teacher_id=teacher.id, subject_id=payload.subject_id))
    log_audit(db, admin, "assign_teacher", "class", class_id, {"teacher_id": teacher.id}, request)
    db.commit()
    return Message(message="Guru berhasil ditugaskan")


def _sync_class_members(db: DBSession, class_id: str, student_ids: list[str], school_id: str) -> None:
    """Replace class membership with validated student IDs (transaction-safe)."""
    unique_ids = list(dict.fromkeys(student_ids))
    if unique_ids:
        students = db.scalars(select(User).where(User.id.in_(unique_ids))).all()
        if len(students) != len(unique_ids):
            raise HTTPException(status_code=400, detail="Sebagian siswa tidak ditemukan")
        for student in students:
            if student.school_id != school_id or student.role.name != "student":
                raise HTTPException(status_code=400, detail="Anggota kelas harus siswa di sekolah ini")
    db.query(ClassMember).filter(ClassMember.class_id == class_id).delete()
    for student_id in unique_ids:
        db.add(ClassMember(class_id=class_id, user_id=student_id))


@router.get("/audit-logs", response_model=Page[AuditSchema])
def audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
) -> Page[AuditSchema]:
    total = db.scalar(select(func.count(AuditLog.id))) or 0
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)).all()
    return Page[AuditSchema](items=rows, total=total, limit=limit, offset=offset)
