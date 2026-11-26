"""Low-level provider HTTP adapters for Fase 4.

Adapter names describe how to talk to a provider; they never imply that a model
exists or is available. Model ids are supplied only by discovery or by an
administrator after verification. API keys are read from server environment
variables named by the provider row and are never returned to callers.
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable

import httpx


class AIClientError(Exception):
    """A provider call failed. Messages are redacted before being stored."""


def get_ai_client():
    """Injectable HTTP transport. Tests replace this with a fake client."""
    return None


_KEY_QUERY = re.compile(r"(key|api_key|token)=[^&\s]+", re.IGNORECASE)


def _safe(text: str) -> str:
    return _KEY_QUERY.sub(r"\1=***", text)[:600]


def _url(provider: Any, path: str) -> str:
    return f"{(provider.base_url or '').rstrip('/')}{path}"


def _env_key(provider: Any) -> str | None:
    name = getattr(provider, "api_key_env", None)
    if not name:
        return None
    return os.environ.get(name) or None


def _key_required(provider: Any) -> bool:
    if provider.adapter == "ollama":
        return False
    if provider.adapter == "gemini":
        return True
    return bool(getattr(provider, "api_key_env", None))


def _headers(provider: Any) -> dict[str, str]:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if _key_required(provider):
        key = _env_key(provider)
        if not key:
            raise AIClientError(
                f"Kunci API belum tersedia di lingkungan server ({provider.api_key_env})."
            )
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _request(client: Any, method: str, url: str, **kwargs: Any) -> Any:
    try:
        response = client.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        raise AIClientError(f"Penyedia menolak permintaan ({exc.response.status_code}).") from None
    except (httpx.HTTPError, ValueError) as exc:
        raise AIClientError(_safe(str(exc))) from None


def _managed(provider: Any, fn: Callable[[Any], Any], client: Any | None) -> Any:
    if client is not None:
        return fn(client)
    with httpx.Client(timeout=provider.timeout_sec or 30) as http:
        return fn(http)


def _model_info(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("id") or raw.get("name") or "").strip()
    if name.startswith("models/"):
        name = name[7:]
    return {
        "model_id": name,
        "display_name": raw.get("display_name") or raw.get("name") or name,
        "capabilities_json": {
            "methods": raw.get("supportedGenerationMethods") or [],
            "owned_by": raw.get("owned_by"),
        },
        "context_window": raw.get("context_window"),
    }


def discover_openai(client: Any, provider: Any) -> list[dict[str, Any]]:
    payload = _request(client, "GET", _url(provider, "/models"), headers=_headers(provider))
    items = payload.get("data", payload) if isinstance(payload, dict) else payload
    return [_model_info(item) for item in items if isinstance(item, dict) and _model_info(item)["model_id"]]


def discover_gemini(client: Any, provider: Any) -> list[dict[str, Any]]:
    key = _env_key(provider)
    if not key:
        raise AIClientError(f"Kunci API belum tersedia di lingkungan server ({provider.api_key_env}).")
    payload = _request(client, "GET", _url(provider, f"/models?key={key}"))
    items = payload.get("models", []) if isinstance(payload, dict) else []
    return [_model_info(item) for item in items if isinstance(item, dict) and _model_info(item)["model_id"]]


def discover_ollama(client: Any, provider: Any) -> list[dict[str, Any]]:
    payload = _request(client, "GET", _url(provider, "/api/tags"))
    items = payload.get("models", []) if isinstance(payload, dict) else []
    return [_model_info(item) for item in items if isinstance(item, dict) and _model_info(item)["model_id"]]


DISCOVERERS = {
    "openai_compatible": discover_openai,
    "gemini": discover_gemini,
    "ollama": discover_ollama,
}


def discover_models(provider: Any, client: Any | None = None) -> list[dict[str, Any]]:
    fn = DISCOVERERS.get(provider.adapter)
    if fn is None:
        raise AIClientError("Adapter tidak mendukung penemuan model otomatis")
    return _managed(provider, lambda http: fn(http, provider), client)


def _openai_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"role": item["role"], "content": item["content"]} for item in messages]


def _chat_result(text: str, tokens_in: int, tokens_out: int, raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "text": text,
        "tokens_in": int(tokens_in or 0),
        "tokens_out": int(tokens_out or 0),
        "raw": raw,
    }


def chat_openai(client: Any, provider: Any, model: str, messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
    payload = _request(
        client,
        "POST",
        _url(provider, "/chat/completions"),
        headers=_headers(provider),
        json={
            "model": model,
            "messages": _openai_messages(messages),
            "max_tokens": max_tokens,
            "temperature": 0.2,
        },
    )
    choices = payload.get("choices", []) if isinstance(payload, dict) else []
    if not choices:
        raise AIClientError("Penyedia tidak mengembalikan jawaban")
    usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
    return _chat_result(
        str(choices[0].get("message", {}).get("content", "")).strip(),
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        payload,
    )


def chat_gemini(client: Any, provider: Any, model: str, messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
    key = _env_key(provider)
    if not key:
        raise AIClientError(f"Kunci API belum tersedia di lingkungan server ({provider.api_key_env}).")
    contents = [
        {"role": "user" if item["role"] != "assistant" else "model", "parts": [{"text": item["content"]}]}
        for item in messages
    ]
    payload = _request(
        client,
        "POST",
        _url(provider, f"/models/{model}:generateContent?key={key}"),
        json={
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2},
        },
    )
    candidates = payload.get("candidates", []) if isinstance(payload, dict) else []
    if not candidates:
        raise AIClientError("Penyedia tidak mengembalikan jawaban")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(str(part.get("text", "")) for part in parts).strip()
    usage = payload.get("usageMetadata", {}) if isinstance(payload, dict) else {}
    return _chat_result(text, usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0), payload)


def chat_ollama(
    client: Any,
    provider: Any,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    json_mode: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": _openai_messages(messages),
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": max_tokens},
    }
    if json_mode:
        body["format"] = "json"
    payload = _request(
        client,
        "POST",
        _url(provider, "/api/chat"),
        json=body,
    )
    if not isinstance(payload, dict):
        raise AIClientError("Respons penyedia tidak valid")
    return _chat_result(
        str(payload.get("message", {}).get("content", "")).strip(),
        payload.get("prompt_eval_count", 0),
        payload.get("eval_count", 0),
        payload,
    )


CHATTERS = {
    "openai_compatible": chat_openai,
    "gemini": chat_gemini,
    "ollama": chat_ollama,
}


def chat(
    provider: Any,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    client: Any | None = None,
    json_mode: bool = False,
) -> dict[str, Any]:
    fn = CHATTERS.get(provider.adapter)
    if fn is None:
        raise AIClientError("Adapter tidak mendukung percakapan")
    if provider.adapter == "ollama":
        return _managed(
            provider,
            lambda http: fn(http, provider, model, messages, max_tokens, json_mode),
            client,
        )
    return _managed(
        provider,
        lambda http: fn(http, provider, model, messages, max_tokens),
        client,
    )


def embed_openai(client: Any, provider: Any, model: str, texts: list[str]) -> list[list[float]]:
    payload = _request(
        client,
        "POST",
        _url(provider, "/embeddings"),
        headers=_headers(provider),
        json={"model": model, "input": texts},
    )
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    return [[float(value) for value in row.get("embedding", [])] for row in rows]


def embed_gemini(client: Any, provider: Any, model: str, texts: list[str]) -> list[list[float]]:
    key = _env_key(provider)
    if not key:
        raise AIClientError(f"Kunci API belum tersedia di lingkungan server ({provider.api_key_env}).")
    vectors: list[list[float]] = []
    for text in texts:
        payload = _request(
            client,
            "POST",
            _url(provider, f"/models/{model}:embedContent?key={key}"),
            json={"model": model, "content": {"parts": [{"text": text}]}},
        )
        values = payload.get("embedding", {}).get("values", [])
        vectors.append([float(value) for value in values])
    return vectors


def embed_ollama(client: Any, provider: Any, model: str, texts: list[str]) -> list[list[float]]:
    payload = _request(
        client, "POST", _url(provider, "/api/embed"),
        json={"model": model, "input": texts},
    )
    rows = payload.get("embeddings", []) if isinstance(payload, dict) else []
    return [[float(value) for value in row] for row in rows]


EMBEDDERS = {
    "openai_compatible": embed_openai,
    "gemini": embed_gemini,
    "ollama": embed_ollama,
}


def embed(
    provider: Any,
    model: str,
    texts: list[str],
    client: Any | None = None,
) -> list[list[float]]:
    fn = EMBEDDERS.get(provider.adapter)
    if fn is None:
        raise AIClientError("Adapter tidak mendukung embedding")
    return _managed(provider, lambda http: fn(http, provider, model, texts), client)
