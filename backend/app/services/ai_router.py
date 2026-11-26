"""Intelligent model router with honest availability, fallback and usage evidence."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.db.base import utcnow
from app.models.ai import AIProvider, AIUsageLog, AIModel
from app.models.core import User
from app.services import ai_client
from app.services.ai_client import AIClientError
from app.services.provider_manager import ADAPTER_INFO, effective_budget


class AIUnavailable(Exception):
    """No verified provider/model can serve the request."""


@dataclass
class ChatResult:
    text: str
    provider_id: str
    provider_name: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    cost_source: str
    latency_ms: int
    request_id: str
    attempts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    provider_id: str
    model: str
    cost_usd: float
    cost_source: str


def _providers(db: DBSession, school_id: str) -> list[AIProvider]:
    return list(
        db.scalars(
            select(AIProvider)
            .where(AIProvider.school_id == school_id, AIProvider.is_active.is_(True))
            .order_by(AIProvider.is_primary.desc(), AIProvider.priority, AIProvider.created_at)
        ).all()
    )


def _cost_known(provider: AIProvider) -> bool:
    info = ADAPTER_INFO.get(provider.adapter, {})
    if info.get("requires_key") is False:
        return True
    return (provider.input_cost_per_million or 0) > 0 or (provider.output_cost_per_million or 0) > 0


def _cost(provider: AIProvider, tokens_in: int, tokens_out: int) -> tuple[float, str]:
    if not _cost_known(provider):
        return 0.0, "unknown"
    cost = (
        tokens_in / 1_000_000 * float(provider.input_cost_per_million or 0)
        + tokens_out / 1_000_000 * float(provider.output_cost_per_million or 0)
    )
    return round(cost, 6), "configured"


def _usage_totals(db: DBSession, school_id: str) -> tuple[int, float]:
    since_day = utcnow() - timedelta(days=1)
    since_month = utcnow() - timedelta(days=30)
    day_tokens = db.scalar(
        select(func.coalesce(func.sum(AIUsageLog.tokens_in + AIUsageLog.tokens_out), 0)).where(
            AIUsageLog.school_id == school_id, AIUsageLog.created_at >= since_day
        )
    ) or 0
    month_cost = db.scalar(
        select(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).where(
            AIUsageLog.school_id == school_id, AIUsageLog.created_at >= since_month
        )
    ) or 0.0
    return int(day_tokens), float(month_cost)


def budget_status(db: DBSession, school_id: str) -> dict[str, Any]:
    budget = effective_budget(db)
    tokens, cost = _usage_totals(db, school_id)
    return {
        "policy": budget,
        "used_today_tokens": tokens,
        "used_30d_cost_usd": round(cost, 6),
        "daily_remaining_tokens": max(0, int(budget["daily_token_limit"]) - tokens),
        "cost_remaining_usd": round(
            max(0.0, float(budget["monthly_cost_limit_usd"]) - cost), 6
        ),
    }


def _within_budget(db: DBSession, school_id: str, needed_tokens: int) -> str | None:
    budget = effective_budget(db)
    used_tokens, used_cost = _usage_totals(db, school_id)
    if used_tokens + needed_tokens > int(budget["daily_token_limit"]):
        return "Batas token harian sekolah tercapai"
    limit = float(budget["monthly_cost_limit_usd"])
    if limit > 0 and used_cost >= limit:
        return "Batas biaya 30 hari sekolah tercapai"
    return None


def _models(db: DBSession, provider: AIProvider) -> list[AIModel]:
    return list(
        db.scalars(
            select(AIModel).where(
                AIModel.provider_id == provider.id,
                AIModel.school_id == provider.school_id,
                AIModel.is_enabled.is_(True),
            ).order_by(AIModel.model_id)
        ).all()
    )


def _capability_ok(row: AIModel, kind: str) -> bool:
    methods = (row.capabilities_json or {}).get("methods") or []
    if not methods:
        return True
    text = " ".join(str(item).lower() for item in methods)
    if kind == "embedding":
        return "embed" in text
    return any(word in text for word in ("generatecontent", "chat", "completion", "generate"))


def _pick_model(
    provider: AIProvider, models: list[AIModel], preferred: str | None, kind: str
) -> AIModel | None:
    allowed = [row for row in models if _capability_ok(row, kind)]
    for candidate in (preferred, provider.model, provider.embedding_model if kind == "embedding" else None):
        if candidate:
            match = next((row for row in allowed if row.model_id == candidate), None)
            if match:
                return match
    return allowed[0] if allowed else None


def _log(
    db: DBSession,
    user: User | None,
    provider: AIProvider | None,
    purpose: str,
    model: str | None,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    success: bool,
    error: str | None,
    request_id: str,
    cost_usd: float = 0.0,
    cost_source: str = "not_configured",
) -> None:
    db.add(
        AIUsageLog(
            school_id=user.school_id if user else (provider.school_id if provider else None),
            provider_id=provider.id if provider else None,
            user_id=user.id if user else None,
            purpose=purpose,
            model=model,
            tokens_in=max(0, int(tokens_in or 0)),
            tokens_out=max(0, int(tokens_out or 0)),
            cost_usd=max(0.0, float(cost_usd or 0)),
            cost_source=cost_source,
            request_id=request_id,
            latency_ms=max(0, int(latency_ms or 0)),
            success=success,
            error=error[:500] if error else None,
        )
    )
    db.flush()


def chat(
    db: DBSession,
    user: User,
    purpose: str,
    messages: list[dict[str, str]],
    preferred_model: str | None = None,
    max_tokens: int | None = None,
    client: Any | None = None,
    json_mode: bool = False,
) -> ChatResult:
    budget = effective_budget(db)
    wanted = min(int(max_tokens or budget["max_tokens_per_request"]), int(budget["max_tokens_per_request"]))
    blocked = _within_budget(db, user.school_id, wanted)
    if blocked:
        raise AIUnavailable(blocked)

    request_id = uuid4().hex[:24]
    attempts: list[dict[str, Any]] = []
    for provider in _providers(db, user.school_id):
        models = _models(db, provider)
        row = _pick_model(provider, models, preferred_model, "chat")
        if row is None:
            attempts.append({"provider": provider.name, "reason": "Belum ada model terverifikasi"})
            continue
        budget = effective_budget(db)
        if not budget["allow_unknown_cost"] and not _cost_known(provider) and float(budget["monthly_cost_limit_usd"]) > 0:
            attempts.append({"provider": provider.name, "reason": "Biaya penyedia belum dikonfigurasi"})
            continue
        hour_ago = utcnow() - timedelta(hours=1)
        hour_count = db.scalar(
            select(func.count(AIUsageLog.id)).where(
                AIUsageLog.provider_id == provider.id,
                AIUsageLog.created_at >= hour_ago,
                AIUsageLog.success.is_(True),
            )
        ) or 0
        if hour_count >= provider.requests_per_hour:
            attempts.append({"provider": provider.name, "reason": "Batas permintaan per jam tercapai"})
            continue

        started = perf_counter()
        try:
            result = ai_client.chat(
                provider,
                row.model_id,
                messages,
                min(wanted, provider.max_tokens),
                client,
                json_mode=json_mode,
            )
        except AIClientError as exc:
            latency = int((perf_counter() - started) * 1000)
            _log(db, user, provider, purpose, row.model_id, 0, 0, latency, False, str(exc), request_id)
            attempts.append({"provider": provider.name, "reason": str(exc)})
            continue
        latency = int((perf_counter() - started) * 1000)
        if not result["text"]:
            _log(db, user, provider, purpose, row.model_id, result["tokens_in"], result["tokens_out"], latency, False, "Jawaban kosong", request_id)
            attempts.append({"provider": provider.name, "reason": "Jawaban kosong"})
            continue
        cost, source = _cost(provider, result["tokens_in"], result["tokens_out"])
        _log(db, user, provider, purpose, row.model_id, result["tokens_in"], result["tokens_out"], latency, True, None, request_id, cost, source)
        return ChatResult(
            text=result["text"],
            provider_id=provider.id,
            provider_name=provider.display_name,
            model=row.model_id,
            tokens_in=result["tokens_in"],
            tokens_out=result["tokens_out"],
            cost_usd=cost,
            cost_source=source,
            latency_ms=latency,
            request_id=request_id,
            attempts=attempts,
        )

    reason = "Tidak ada penyedia AI terverifikasi yang dapat dipakai"
    if attempts:
        reason += "; " + "; ".join(f"{a['provider']}: {a['reason']}" for a in attempts[:3])
    raise AIUnavailable(reason)


def embeddings(
    db: DBSession,
    user: User,
    texts: list[str],
    client: Any | None = None,
) -> EmbeddingResult | None:
    request_id = uuid4().hex[:24]
    for provider in _providers(db, user.school_id):
        info = ADAPTER_INFO.get(provider.adapter, {})
        if not info.get("supports_embedding"):
            continue
        row = _pick_model(provider, _models(db, provider), provider.embedding_model, "embedding")
        if row is None:
            continue
        started = perf_counter()
        try:
            vectors = ai_client.embed(provider, row.model_id, texts, client)
        except AIClientError as exc:
            latency = int((perf_counter() - started) * 1000)
            _log(db, user, provider, "embedding", row.model_id, 0, 0, latency, False, str(exc), request_id)
            continue
        if len(vectors) != len(texts) or any(not vector for vector in vectors):
            continue
        latency = int((perf_counter() - started) * 1000)
        cost, source = _cost(provider, sum(len(text.split()) for text in texts), 0)
        _log(db, user, provider, "embedding", row.model_id, 0, 0, latency, True, None, request_id, cost, source)
        return EmbeddingResult(vectors, provider.id, row.model_id, cost, source)
    return None
