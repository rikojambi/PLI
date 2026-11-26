"""Data available to teachers and students, always tenant/role scoped."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.deps import require_roles, teacher_class_ids
from app.db.session import get_db
from app.models.academic import Class, ClassMember, Subject
from app.models.core import AcademicYear, Role, School, Semester, User
from app.models.intelligence import StudentCompetencyMastery

router = APIRouter(prefix="/portal", tags=["portal"])


def _teacher_classes(db: DBSession, user: User) -> list[Class]:
    if user.role.name == "admin":
        return list(db.scalars(select(Class).where(Class.school_id == user.school_id)).all())
    ids = teacher_class_ids(db, user)
    if not ids:
        return []
    return list(db.scalars(select(Class).where(Class.id.in_(ids)).order_by(Class.name)).all())


@router.get("/context")
def context(user: User = Depends(require_roles("admin", "teacher", "student")), db: DBSession = Depends(get_db)):
    school = db.get(School, user.school_id)
    years = db.scalars(
        select(AcademicYear).where(AcademicYear.school_id == user.school_id).order_by(AcademicYear.start_date.desc())
    ).all()
    active_year = next((y for y in years if y.is_active), years[0] if years else None)
    semesters: list[Semester] = []
    if active_year:
        semesters = list(db.scalars(select(Semester).where(Semester.academic_year_id == active_year.id)).all())
    active_semester = next((s for s in semesters if s.is_active), semesters[0] if semesters else None)
    subjects = db.scalars(
        select(Subject).where(Subject.school_id == user.school_id, Subject.is_active.is_(True)).order_by(Subject.name)
    ).all()
    return {
        "school": {"id": school.id, "name": school.name} if school else None,
        "academic_year": {"id": active_year.id, "name": active_year.name} if active_year else None,
        "semester": {"id": active_semester.id, "name": active_semester.name} if active_semester else None,
        "subjects": [{"id": s.id, "name": s.name, "code": s.code, "color": s.color} for s in subjects],
        "role": user.role.name,
    }


@router.get("/teacher/classes")
def teacher_classes(
    user: User = Depends(require_roles("admin", "teacher")), db: DBSession = Depends(get_db)
):
    classes = _teacher_classes(db, user)
    result = []
    for klass in classes:
        count = db.scalar(select(func.count(ClassMember.id)).where(ClassMember.class_id == klass.id)) or 0
        result.append({
            "id": klass.id,
            "name": klass.name,
            "grade_level": klass.grade_level,
            "is_active": klass.is_active,
            "student_count": count,
        })
    return result


@router.get("/teacher/classes/{class_id}/students")
def teacher_students(
    class_id: str,
    user: User = Depends(require_roles("admin", "teacher")),
    db: DBSession = Depends(get_db),
):
    if class_id not in [c.id for c in _teacher_classes(db, user)]:
        raise HTTPException(status_code=403, detail="Anda tidak mengampu kelas ini")
    students = db.scalars(
        select(User)
        .join(ClassMember)
        .where(ClassMember.class_id == class_id, User.role_id.in_(select(Role.id).where(Role.name == "student")))
        .order_by(User.full_name)
    ).all()
    return [
        {
            "id": s.id,
            "full_name": s.full_name,
            "username": s.username,
            "student_number": s.student_number,
            "is_active": s.is_active,
        }
        for s in students
    ]


@router.get("/teacher/overview")
def teacher_overview(
    user: User = Depends(require_roles("admin", "teacher")), db: DBSession = Depends(get_db)
):
    classes = _teacher_classes(db, user)
    ids = [c.id for c in classes]
    students = 0
    if ids:
        students = db.scalar(
            select(func.count(func.distinct(ClassMember.user_id))).where(ClassMember.class_id.in_(ids))
        ) or 0
    return {"classes": len(classes), "students": students, "subjects": 0, "assessments": 0}


@router.get("/student/classes")
def student_classes(
    user: User = Depends(require_roles("student")), db: DBSession = Depends(get_db)
):
    rows = db.scalars(
        select(Class)
        .join(ClassMember)
        .where(ClassMember.user_id == user.id, Class.school_id == user.school_id)
        .order_by(Class.name)
    ).all()
    return [
        {"id": c.id, "name": c.name, "grade_level": c.grade_level, "is_active": c.is_active}
        for c in rows
    ]


@router.get("/student/overview")
def student_overview(
    user: User = Depends(require_roles("student")), db: DBSession = Depends(get_db)
):
    class_count = db.scalar(
        select(func.count(ClassMember.id)).where(ClassMember.user_id == user.id)
    ) or 0
    mastery_rows = db.scalars(
        select(StudentCompetencyMastery).where(StudentCompetencyMastery.student_id == user.id)
    ).all()
    return {
        "classes": class_count,
        "competencies_tracked": len(mastery_rows),
        "average_mastery": round(sum(m.mastery_probability for m in mastery_rows) / len(mastery_rows), 4)
        if mastery_rows
        else 0,
        "assessments": 0,
    }
