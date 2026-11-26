"""Fase 6 privacy operation requests."""
from pydantic import BaseModel, Field


class ConfirmIn(BaseModel):
    confirm: bool = Field(description="Harus true untuk menjalankan penghapusan/pembersihan")
    reason: str | None = Field(default=None, max_length=500)


class RotateSecretIn(BaseModel):
    confirm: bool = Field(description="Harus true untuk mengganti kunci sesi server")
    note: str | None = Field(default=None, max_length=300)
