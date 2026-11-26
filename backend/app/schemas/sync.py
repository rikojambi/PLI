"""Fase 6 offline sync request/response schemas."""
from typing import Literal

from pydantic import BaseModel, Field


class ConflictResolutionIn(BaseModel):
    resolution: Literal["server", "client"] = Field(
        description="'server' mempertahankan versi server; 'client' menulis versi perangkat yang tersimpan."
    )
    note: str | None = Field(default=None, max_length=500)
