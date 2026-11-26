from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("username")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.strip().lower()


class LoginResponse(BaseModel):
    csrf_token: str
    user: "UserOut"


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8)
    new_password: str = Field(min_length=10, max_length=200)

    @field_validator("new_password")
    @classmethod
    def strong(cls, v: str) -> str:
        if v.isalpha() or v.isdigit():
            raise ValueError("Password harus memuat huruf dan angka")
        if " " in v:
            raise ValueError("Password tidak boleh mengandung spasi")
        return v


class RoleOut(ORMModel):
    id: str
    name: str
    description: str | None = None


class UserOut(ORMModel):
    id: str
    school_id: str
    role_id: str
    username: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    student_number: str | None = None
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None = None
    role: RoleOut


LoginResponse.model_rebuild()
