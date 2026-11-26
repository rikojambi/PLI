"""Server-side AI provider catalogue, secret references and runtime policy."""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.models.ai import AIProvider, AIModel
from app.models.core import User
from app.models.intelligence import EngineConfig
from app.services.ai_client import AIClientError, discover_models


ADAPTER_INFO = {
    "openai_compatible": {
        "label": "OpenAI-compatible",
        "requires_key": True,
        "default_base_url": "",
        "supports_chat": True,
        "supports_embedding": True,
        "discovery": "GET /models",
        "note": "Pakai untuk penyedia dengan API OpenAI-compatible. Base URL wajib diisi administrator.",
    },
    "gemini": {
        "label": "Google Gemini",
        "requires_key": True,
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "supports_chat": True,
        "supports_embedding": True,
        "discovery": "GET /models?key=...",
        "note": "Kunci dibaca dari environment variable server, bukan dari browser.",
    },
    "groq": {
        "label": "Groq",
        "requires_key": True,
        "default_base_url": "https://api.groq.com/openai/v1",
        "supports_chat": True,
        "supports_embedding": False,
        "discovery": "GET /models",
        "note": "Menggunakan adapter OpenAI-compatible dengan endpoint resmi Groq.",
    },
    "openrouter": {
        "label": "OpenRouter",
        "requires_key": True,
        "default_base_url": "https://openrouter.ai/api/v1",
        "supports_chat": True,
        "supports_embedding": False,
        "discovery": "GET /models",
        "note": "Model mengikuti daftar yang tersedia di akun OpenRouter administrator.",
    },
    "huggingface": {
        "label": "Hugging Face Router",
        "requires_key": True,
        "default_base_url": "https://router.huggingface.co/v1",
        "supports_chat": True,
        "supports_embedding": False,
        "discovery": "GET /models",
        "note": "Hanya model yang mendukung chat/completions yang akan dipakai.",
    },
    "cerebras": {
        "label": "Cerebras",
        "requires_key": True,
        "default_base_url": "https://api.cerebras.ai/v1",
        "supports_chat": True,
        "supports_embedding": False,
        "discovery": "GET /models",
        "note": "Model harus ditemukan dari akun Cerebras sebelum dipilih.",
    },
    "mistral": {
        "label": "Mistral",
        "requires_key": True,
        "default_base_url": "https://api.mistral.ai/v1",
        "supports_chat": True,
        "supports_embedding": True,
        "discovery": "GET /models",
        "note": "Model embedding harus diverifikasi terpisah dari model chat.",
    },
    "ollama": {
        "label": "Ollama (lokal)",
        "requires_key": False,
        "default_base_url": "http://127.0.0.1:11434",
        "supports_chat": True,
        "supports_embedding": True,
        "discovery": "GET /api/tags",
        "note": "Tidak mengirim data ke luar komputer bila memakai model lokal.",
    },
}

# Provider seed rows use the concrete adapter that implements the protocol.
SEED_ADAPTER_MAP = {
    "groq": "openai_compatible",
    "openrouter": "openai_compatible",
    "huggingface": "openai_compatible",
    "cerebras": "openai_compatible",
    "mistral": "openai_compatible",
}

BUDGET_KEY = "ai_budget"


def default_budget() -> dict[str, Any]:
    return {
        "daily_token_limit": settings.ai_daily_token_limit,
        "monthly_cost_limit_usd": settings.ai_monthly_cost_limit_usd,
        "max_tokens_per_request": settings.ai_max_tokens_per_request,
        "allow_unknown_cost": False,
    }


def effective_budget(db: DBSession) -> dict[str, Any]:
    row = db.scalar(select(EngineConfig).where(EngineConfig.key == BUDGET_KEY))
    result = default_budget()
    if row is not None:
        result.update(row.value_json or {})
    return result


def save_budget(db: DBSession, values: dict[str, Any], actor: User) -> dict[str, Any]:
    merged = effective_budget(db)
    merged.update(values)
    row = db.scalar(select(EngineConfig).where(EngineConfig.key == BUDGET_KEY))
    if row is None:
        row = EngineConfig(key=BUDGET_KEY, value_json=merged, updated_by=actor.id)
        db.add(row)
    else:
        row.value_json = merged
        row.updated_by = actor.id
    db.flush()
    return merged


def key_info(provider: AIProvider) -> dict[str, Any]:
    """Return only a masked hint and presence flag. Never return the key itself."""
    name = provider.api_key_env
    if not name:
        return {"has_key": True, "key_hint": None, "key_required": False}
    value = os.environ.get(name)
    if not value:
        return {"has_key": False, "key_hint": None, "key_required": True}
    visible = value[:3] + "…" + value[-3:] if len(value) >= 8 else "••••"
    return {"has_key": True, "key_hint": f"{name} · {visible}", "key_required": True}


def catalog() -> list[dict[str, Any]]:
    return [
        {"name": name, **info, "seed_adapter": SEED_ADAPTER_MAP.get(name, name)}
        for name, info in ADAPTER_INFO.items()
    ]


def model_rows(db: DBSession, school_id: str, provider_id: str | None = None) -> list[AIModel]:
    query = select(AIModel).where(AIModel.school_id == school_id)
    if provider_id:
        query = query.where(AIModel.provider_id == provider_id)
    return list(db.scalars(query.order_by(AIModel.model_id)).all())


def sync_models(
    db: DBSession, provider: AIProvider, records: list[dict[str, Any]], client: Any | None = None
) -> tuple[list[AIModel], str | None]:
    """Upsert discovered models. Returns rows and an optional redacted error."""
    if client is None:
        try:
            records = discover_models(provider)
        except AIClientError as exc:
            return [], str(exc)
    existing = {
        row.model_id: row
        for row in db.scalars(
            select(AIModel).where(
                AIModel.provider_id == provider.id, AIModel.school_id == provider.school_id
            )
        ).all()
    }
    for record in records:
        model_id = str(record.get("model_id") or "").strip()
        if not model_id:
            continue
        row = existing.get(model_id)
        if row is None:
            row = AIModel(
                school_id=provider.school_id,
                provider_id=provider.id,
                model_id=model_id,
                discovered=True,
                is_enabled=True,
            )
            db.add(row)
            existing[model_id] = row
        row.display_name = record.get("display_name") or model_id
        caps = dict(record.get("capabilities_json") or {})
        caps["discovered_via"] = "provider_api"
        row.capabilities_json = caps
        row.context_window = record.get("context_window")
        row.discovered = True
    db.flush()
    return list(existing.values()), None
