from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.common import ORMModel


class SchoolOut(ORMModel):
    id: str
    name: str
    npsn: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None


class SchoolUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    npsn: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None
    password: str = Field(min_length=10, max_length=200)
    role: str = Field(pattern="^(admin|teacher|student)$")
    phone: str | None = Field(default=None, max_length=30)
    student_number: str | None = Field(default=None, max_length=40)
    class_id: str | None = None

    @field_validator("username")
    @classmethod
    def normalize_username(cls, v: str) -> str:
        value = v.strip().lower()
        if not value.replace("_", "").replace(".", "").isalnum():
            raise ValueError("Username hanya boleh huruf, angka, titik, dan garis bawah")
        return value


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    student_number: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None
    role: str | None = Field(default=None, pattern="^(admin|teacher|student)$")


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=10, max_length=200)


class AcademicYearCreate(BaseModel):
    name: str = Field(min_length=4, max_length=50)
    start_date: datetime
    end_date: datetime
    is_active: bool = False

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("Tanggal akhir harus setelah tanggal mulai")
        return self


class SemesterCreate(BaseModel):
    academic_year_id: str
    name: str = Field(min_length=3, max_length=50)
    start_date: datetime
    end_date: datetime
    is_active: bool = False

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date <= self.start_date:
            raise ValueError("Tanggal akhir harus setelah tanggal mulai")
        return self


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    academic_year_id: str
    semester_id: str
    grade_level: str | None = Field(default=None, max_length=30)
    homeroom_teacher_id: str | None = None
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool = True
    student_ids: list[str] = Field(default_factory=list)
    teacher_ids: list[str] = Field(default_factory=list)


class ClassMemberUpdate(BaseModel):
    student_ids: list[str]


class TeacherAssign(BaseModel):
    teacher_id: str
    subject_id: str | None = None


class SubjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    color: str | None = Field(default=None, max_length=20)
    is_active: bool = True


class CompetencyCreate(BaseModel):
    subject_id: str
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=2, max_length=250)
    description: str | None = None
    grade_level: str | None = Field(default=None, max_length=30)
    parent_id: str | None = None
    prerequisite_codes: list[str] = Field(default_factory=list)
    order_index: int = Field(default=0, ge=0)
