"""Fase 4 tests: honest AI availability, provider manager, RAG, tutor and drafts.

All provider HTTP traffic is replaced by a fake transport; no network or real
API key is ever needed. The tests intentionally verify that unavailable AI is
reported honestly rather than answered with fabricated content.
"""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.core.security import hash_password
from app.db.base import utcnow
from app.main import app
from app.models.academic import Competency, Subject
from app.models.ai import AIProvider, AIModel, AIUsageLog, GeneratedContent
from app.models.assessment import Question
from app.models.core import Role, User
from app.services.ai_client import get_ai_client
from app.services import ai_client

from tests.conftest import TEST_PASSWORD, login

SECRET = "pli-secret-value-123456"


def _auth(client: TestClient, username: str) -> dict[str, str]:
    data = login(client, username)
    return {"X-CSRF-Token": data["csrf_token"]}


class FakeResponse:
    def __init__(self, method: str, url: str, status: int, payload):
        self._method = method
        self._url = url
        self.status_code = status
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "penyedia menolak",
                request=httpx.Request(self._method, self._url),
                response=httpx.Response(self.status_code, request=httpx.Request(self._method, self._url)),
            )

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, responder):
        self.responder = responder
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responder(method, url, kwargs)


def chat_responder(answer: str = "Jawaban uji dari model.", draft: str | None = None):
    def responder(method: str, url: str, kwargs: dict):
        if url.endswith("/models") or "/models?" in url or "/api/tags" in url:
            return FakeResponse(method, url, 200, {"data": [{"id": "model-satu"}]})
        if "/chat/completions" in url or "/api/chat" in url or ":generateContent" in url:
            payload = json.dumps(kwargs, ensure_ascii=False)
            if "GAGAL" in payload:
                return FakeResponse(method, url, 500, {"error": "server error"})
            text = draft if draft and "objek JSON valid" in payload else answer
            if ":generateContent" in url:
                return FakeResponse(method, url, 200, {
                    "candidates": [{"content": {"parts": [{"text": text}]}}],
                    "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 8},
                })
            if "/api/chat" in url:
                return FakeResponse(method, url, 200, {
                    "message": {"content": text}, "prompt_eval_count": 12, "eval_count": 8,
                })
            return FakeResponse(method, url, 200, {
                "choices": [{"message": {"content": text}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            })
        if "/embeddings" in url or "/api/embed" in url:
            return FakeResponse(method, url, 200, {"data": [{"embedding": [1.0, 0.0]}]})
        return FakeResponse(method, url, 404, {"error": "not found"})

    return responder


def _provider(db, fixtures, *, name="utama", base="http://fake-primary", model="model-satu", active=True):
    row = AIProvider(
        school_id=fixtures["school"].id,
        name=name,
        display_name=name.title(),
        adapter="openai_compatible",
        base_url=base,
        model=model,
        api_key_env="PLI_TEST_API_KEY",
        is_active=active,
        is_primary=True,
        input_cost_per_million=1.0,
        output_cost_per_million=2.0,
        config_json={},
    )
    db.add(row)
    db.flush()
    verified = AIModel(
        school_id=fixtures["school"].id,
        provider_id=row.id,
        model_id=model,
        discovered=True,
        is_enabled=True,
        capabilities_json={"methods": ["generateContent"]},  # chat only, no embeddings
    )
    db.add(verified)
    db.flush()
    return row, verified


def _subject(db, fixtures, name="Matematika"):
    subject = Subject(
        school_id=fixtures["school"].id, code=name[:3].upper() + "4", name=name, is_active=True
    )
    db.add(subject)
    db.flush()
    competency = Competency(subject_id=subject.id, code="K1", name="Operasi bilangan")
    db.add(competency)
    db.flush()
    return subject, competency


def _install_fake(client, responder):
    fake = FakeClient(responder)
    app.dependency_overrides[get_ai_client] = lambda: fake
    return fake


def _cleanup_fake():
    app.dependency_overrides.pop(get_ai_client, None)


# ---------------------------------------------------------------- honesty

def test_ai_is_honestly_unavailable_without_verified_models(client, db, fixtures):
    admin = _auth(client, "admin")
    status = client.get("/api/v1/ai/status", headers=admin)
    assert status.status_code == 200, status.text
    assert status.json()["available"] is False

    teacher = _auth(client, "guru")
    response = client.post("/api/v1/ai/generate", headers=teacher, json={
        "kind": "material", "subject_id": "missing", "topic": "Perkalian",
    })
    assert response.status_code in (400, 503)  # no subject / no provider; never a fake draft

    student = _auth(client, "siswa")
    rag = client.post("/api/v1/ai/rag/ask", headers=student, json={"question": "Apa saja isi modul?"})
    assert rag.status_code == 200, rag.text
    assert rag.json()["status"] == "data_tidak_tersedia"

    tutor = client.post("/api/v1/ai/tutor/chat", headers=student, json={"message": "Bantu saya"})
    assert tutor.status_code == 200, tutor.text
    body = tutor.json()
    assert body["available"] is False
    assert "belum tersedia" in body["message"]["content"]


# ---------------------------------------------------------------- provider manager

def test_provider_manager_masks_key_and_manages_models(client, db, fixtures, monkeypatch):
    monkeypatch.setenv("PLI_TEST_API_KEY", SECRET)
    admin = _auth(client, "admin")
    catalog = client.get("/api/v1/ai/catalog", headers=admin)
    assert catalog.status_code == 200, catalog.text
    names = {item["name"] for item in catalog.json()["adapters"]}
    assert {"gemini", "groq", "openrouter", "huggingface", "cerebras", "mistral", "ollama", "openai_compatible"} <= names

    created = client.post("/api/v1/ai/providers", headers=admin, json={
        "name": "utama", "display_name": "Penyedia Utama", "adapter": "openai_compatible",
        "base_url": "http://fake-primary", "model": "", "api_key_env": "PLI_TEST_API_KEY",
        "is_active": True, "is_primary": True,
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["has_key"] is True
    assert SECRET not in json.dumps(body)
    assert "PLI_TEST_API_KEY" in body["key_hint"]
    provider_id = body["id"]

    duplicate = client.post("/api/v1/ai/providers", headers=admin, json={
        "name": "utama", "display_name": "Duplikat", "adapter": "openai_compatible",
    })
    assert duplicate.status_code == 400

    fake = _install_fake(client, chat_responder())
    try:
        discovered = client.post(f"/api/v1/ai/providers/{provider_id}/discover", headers=admin)
        assert discovered.status_code == 200, discovered.text
        assert discovered.json()[0]["model_id"] == "model-satu"
        assert discovered.json()[0]["discovered"] is True

        manual = client.post(f"/api/v1/ai/providers/{provider_id}/models", headers=admin, json={
            "model_id": "model-verified", "display_name": "Model Verified",
        })
        assert manual.status_code == 201, manual.text
        assert manual.json()["discovered"] is False

        tested = client.post(f"/api/v1/ai/providers/{provider_id}/test", headers=admin)
        assert tested.status_code == 200, tested.text
        assert tested.json()["ok"] is True
        assert tested.json()["model"] in ("model-satu", "model-verified")
    finally:
        _cleanup_fake()

    disabled = client.patch(f"/api/v1/ai/providers/{provider_id}", headers=admin, json={"is_active": False})
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["is_active"] is False

    logs = client.get("/api/v1/ai/usage", headers=admin)
    assert logs.status_code == 200, logs.text
    assert logs.json()["total"] >= 1
    assert all(item["cost_source"] in {"unknown", "configured", "not_configured"} for item in logs.json()["items"])


def test_teacher_cannot_manage_providers(client, db, fixtures):
    teacher = _auth(client, "guru")
    for method, path in (("get", "/api/v1/ai/providers"), ("get", "/api/v1/ai/catalog")):
        response = getattr(client, method)(path, headers=teacher)
        assert response.status_code == 403


# ---------------------------------------------------------------- router + budget

def test_router_falls_back_and_logs_both_attempts(client, db, fixtures, monkeypatch):
    monkeypatch.setenv("PLI_TEST_API_KEY", SECRET)
    primary, _ = _provider(db, fixtures, name="utama", base="http://fake-primary")
    fallback, _ = _provider(db, fixtures, name="cadangan", base="http://fake-fallback")
    primary.is_primary = True
    fallback.is_primary = False
    fallback.priority = 200
    db.flush()
    subject, _competency = _subject(db, fixtures)

    def responder(method: str, url: str, kwargs: dict):
        if url.startswith("http://fake-primary"):
            return FakeResponse(method, url, 500, {"error": "down"})
        return chat_responder(
            "Jawaban dari cadangan.",
            draft=json.dumps({"title": "Materi uji", "material_type": "text", "content": "Isi materi uji."}),
        )(method, url, kwargs)

    fake = _install_fake(client, responder)
    try:
        admin = _auth(client, "admin")
        response = client.post("/api/v1/ai/rag/ask", headers=admin, json={
            "question": "Jelaskan materi", "subject_id": subject.id,
        })
        assert response.status_code == 200, response.text
        # No documents -> honest answer before any model is called.
        assert response.json()["status"] == "data_tidak_tersedia"

        draft = client.post("/api/v1/ai/generate", headers=_auth(client, "guru"), json={
            "kind": "material", "subject_id": subject.id, "topic": "Perkalian",
            "client_id": "fallback-request-1",
        })
        assert draft.status_code == 200, draft.text
        assert draft.json()["content_json"]["title"]
        assert draft.json()["model_info_json"]["provider"] == "Cadangan"
        assert draft.json()["model_info_json"]["attempts"][0]["provider"] == "utama"
    finally:
        _cleanup_fake()

    logs = db.scalars(select_logs()).all()
    assert len([row for row in logs if row.purpose == "generate_material"]) == 2
    assert any(not row.success for row in logs)
    assert any(row.success for row in logs)
    assert len({row.request_id for row in logs if row.purpose == "generate_material"}) == 1

    admin = _auth(client, "admin")
    budget = client.put("/api/v1/ai/budget", headers=admin, json={
        "daily_token_limit": 0, "monthly_cost_limit_usd": 0,
        "max_tokens_per_request": 1024, "allow_unknown_cost": False,
    })
    assert budget.status_code == 200, budget.text
    fake = _install_fake(client, chat_responder())
    try:
        blocked = client.post("/api/v1/ai/generate", headers=_auth(client, "guru"), json={
            "kind": "material", "subject_id": subject.id, "topic": "Perkalian",
            "client_id": "budget-blocked-1",
        })
        assert blocked.status_code == 503
        assert "Batas token harian" in blocked.json()["detail"]
    finally:
        _cleanup_fake()


def select_logs():
    from sqlalchemy import select
    return select(AIUsageLog)


# ---------------------------------------------------------------- RAG

def test_rag_ingest_citation_and_honest_no_match(client, db, fixtures, monkeypatch):
    monkeypatch.setenv("PLI_TEST_API_KEY", SECRET)
    _provider(db, fixtures)
    subject, _ = _subject(db, fixtures)
    teacher = _auth(client, "guru")
    upload = client.post(
        "/api/v1/ai/documents", headers=teacher,
        data={"title": "Modul Fotosintesis", "subject_id": subject.id},
        files={"file": ("modul.txt", b"Fotosintesis adalah proses tumbuhan mengubah cahaya menjadi energi. "
                                    b"Proses ini terjadi di daun dan memerlukan klorofil serta air.", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    document_id = upload.json()["id"]

    indexed = client.post(f"/api/v1/ai/documents/{document_id}/index", headers=teacher)
    assert indexed.status_code == 200, indexed.text
    assert indexed.json()["chunks"] >= 1
    assert indexed.json()["method"] == "lexical"  # no embedding model configured

    fake = _install_fake(client, chat_responder("Fotosintesis terjadi di daun [1]."))
    try:
        answer = client.post("/api/v1/ai/rag/ask", headers=teacher, json={
            "question": "Di mana fotosintesis terjadi?", "document_id": document_id,
        })
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["available"] is True
        assert body["citations"][0]["document_id"] == document_id
        assert body["evidence"]["provider"] == "Utama"

        missing = client.post("/api/v1/ai/rag/ask", headers=teacher, json={
            "question": "Siapa presiden Republik Indonesia tahun 1945?", "document_id": document_id,
        })
        assert missing.json()["status"] == "data_tidak_tersedia"
        assert missing.json()["citations"] == []
    finally:
        _cleanup_fake()

    student = _auth(client, "siswa")
    assert client.post("/api/v1/ai/documents", headers=student, files={"file": ("x.txt", b"abc", "text/plain")}, data={"title": "X"}).status_code == 403
    blocked = client.delete(f"/api/v1/ai/documents/{document_id}", headers=student)
    assert blocked.status_code == 403


# ---------------------------------------------------------------- tutor

def test_tutor_is_student_only_idempotent_and_uses_mastery_profile(client, db, fixtures, monkeypatch):
    monkeypatch.setenv("PLI_TEST_API_KEY", SECRET)
    _provider(db, fixtures)
    assert client.get("/api/v1/ai/tutor/conversations", headers=_auth(client, "guru")).status_code == 403
    student = _auth(client, "siswa")

    fake = _install_fake(client, chat_responder("Coba lagi langkah kedua ya."))
    try:
        first = client.post("/api/v1/ai/tutor/chat", headers=student, json={
            "message": "Saya belum paham perkalian", "client_id": "tutor-client-001",
        })
        assert first.status_code == 200, first.text
        assert first.json()["available"] is True
        conversation_id = first.json()["conversation_id"]
        system_prompt = json.dumps(fake.calls[-1][2], ensure_ascii=False)
        assert "PROFIL SISWA" in system_prompt
        assert "tutor pedagogis" in system_prompt.lower() or "tutor pedagogis" in system_prompt

        replay = client.post("/api/v1/ai/tutor/chat", headers=student, json={
            "message": "Saya belum paham perkalian", "client_id": "tutor-client-001",
        })
        assert replay.status_code == 200, replay.text
        assert replay.json()["idempotent"] is True
        assert replay.json()["message"]["id"] == first.json()["message"]["id"]

        history = client.get(f"/api/v1/ai/tutor/conversations/{conversation_id}", headers=student)
        assert history.status_code == 200, history.text
        assert len(history.json()["messages"]) == 2
    finally:
        _cleanup_fake()

    other = User(
        school_id=fixtures["school"].id, role_id=fixtures["roles"]["student"].id,
        username="siswa2", full_name="Siswa Dua", password_hash=hash_password(TEST_PASSWORD),
    )
    db.add(other)
    db.flush()
    other_auth = _auth(client, "siswa2")
    assert client.get("/api/v1/ai/tutor/conversations", headers=other_auth).json() == []


# ---------------------------------------------------------------- generator

def test_generated_drafts_stay_private_until_teacher_approves(client, db, fixtures, monkeypatch):
    monkeypatch.setenv("PLI_TEST_API_KEY", SECRET)
    _provider(db, fixtures)
    subject, competency = _subject(db, fixtures)
    draft_payload = json.dumps({
        "title": "Soal perkalian", "question_type": "multiple_choice", "difficulty": "easy",
        "content": "Berapa hasil 3 × 4?", "explanation": "3 × 4 = 12",
        "options": [
            {"label": "A", "content": "7", "is_correct": False},
            {"label": "B", "content": "12", "is_correct": True},
        ],
    })

    fake = _install_fake(client, chat_responder(draft_payload))
    try:
        created = client.post("/api/v1/ai/generate", headers=_auth(client, "guru"), json={
            "kind": "question", "subject_id": subject.id, "competency_id": competency.id,
            "topic": "Perkalian", "client_id": "generate-client-001",
        })
        assert created.status_code == 200, created.text
        draft = created.json()
        assert draft["status"] == "draft"
        draft_id = draft["id"]
    finally:
        _cleanup_fake()

    assert db.get(GeneratedContent, draft_id).status == "draft"
    assert db.scalar(select_questions()) is None
    assert client.get("/api/v1/ai/generated", headers=_auth(client, "siswa")).status_code == 403

    approved = client.post(
        f"/api/v1/ai/generated/{draft_id}/approve", headers=_auth(client, "guru"),
        json={"publish": True, "review_note": "Sudah diperiksa"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["published_ref_id"]
    question = db.get(Question, approved.json()["published_ref_id"])
    assert question is not None and question.is_published is True
    assert db.get(GeneratedContent, draft_id).status == "published"

    blocked = client.put("/api/v1/ai/budget", headers=_auth(client, "admin"), json={
        "daily_token_limit": 0, "monthly_cost_limit_usd": 0,
        "max_tokens_per_request": 1024, "allow_unknown_cost": False,
    })
    assert blocked.status_code == 200, blocked.text
    another = client.post("/api/v1/ai/generate", headers=_auth(client, "guru"), json={
        "kind": "material", "subject_id": subject.id, "topic": "Perkalian",
    })
    assert another.status_code == 503  # budget blocks before any model call

    rejected = client.post(
        f"/api/v1/ai/generated/{draft_id}/reject", headers=_auth(client, "guru"),
        json={"review_note": "Tidak dipakai"},
    )
    assert rejected.status_code == 400  # already published cannot be rejected


def test_fresh_draft_can_be_rejected_and_empty_draft_is_refused(client, db, fixtures, monkeypatch):
    monkeypatch.setenv("PLI_TEST_API_KEY", SECRET)
    _provider(db, fixtures)
    subject, _ = _subject(db, fixtures)
    valid = json.dumps({
        "title": "Soal penjumlahan", "question_type": "multiple_choice", "difficulty": "easy",
        "content": "Berapa hasil 2 + 2?", "explanation": "2 + 2 = 4",
        "options": [
            {"label": "A", "content": "3", "is_correct": False},
            {"label": "B", "content": "4", "is_correct": True},
        ],
    })
    fake = _install_fake(client, chat_responder(draft=valid))
    try:
        created = client.post("/api/v1/ai/generate", headers=_auth(client, "guru"), json={
            "kind": "question", "subject_id": subject.id, "topic": "Penjumlahan",
            "client_id": "reject-client-001",
        })
        assert created.status_code == 200, created.text
        draft_id = created.json()["id"]
    finally:
        _cleanup_fake()

    rejected = client.post(
        f"/api/v1/ai/generated/{draft_id}/reject", headers=_auth(client, "guru"),
        json={"review_note": "Tidak dipakai"},
    )
    assert rejected.status_code == 200, rejected.text
    assert db.get(GeneratedContent, draft_id).status == "rejected"

    empty = _install_fake(client, chat_responder(draft="{}"))
    try:
        refused = client.post("/api/v1/ai/generate", headers=_auth(client, "guru"), json={
            "kind": "question", "subject_id": subject.id, "topic": "Penjumlahan",
            "client_id": "empty-client-001",
        })
        assert refused.status_code == 400, refused.text
        assert "tidak memiliki" in refused.json()["detail"]
    finally:
        _cleanup_fake()


def select_questions():
    from sqlalchemy import select
    return select(Question)


def test_ollama_json_mode_only_when_requested():
    provider = AIProvider(
        adapter="ollama", base_url="http://fake-ollama", model="model-satu",
        api_key_env="", timeout_sec=30,
    )
    calls = []

    def responder(method, url, kwargs):
        calls.append(kwargs["json"])
        return FakeResponse(method, url, 200, {
            "message": {"content": "{}"}, "prompt_eval_count": 1, "eval_count": 1,
        })

    client = FakeClient(responder)
    messages = [{"role": "user", "content": "halo"}]
    ai_client.chat(provider, "model-satu", messages, 10, client, json_mode=True)
    ai_client.chat(provider, "model-satu", messages, 10, client)
    assert calls[0]["format"] == "json"
    assert "format" not in calls[1]


def test_fase4_uses_no_secret_in_frontend_payload(client, db, fixtures, monkeypatch):
    monkeypatch.setenv("PLI_TEST_API_KEY", SECRET)
    admin = _auth(client, "admin")
    created = client.post("/api/v1/ai/providers", headers=admin, json={
        "name": "rahasia", "display_name": "Rahasia", "adapter": "openai_compatible",
        "base_url": "http://fake-primary", "api_key_env": "PLI_TEST_API_KEY",
    })
    assert created.status_code == 201, created.text
    assert SECRET not in created.text
    listed = client.get("/api/v1/ai/providers", headers=admin)
    assert listed.status_code == 200
    assert SECRET not in listed.text
    assert "••" in listed.text or "…" in listed.text  # masked hint only
