"""Fase 6 tests: durable conflicts, pull, retention, backup crypto, health."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

from app.core.config import settings
from tests.conftest import login

_SESSION_CACHE: dict[tuple[object, str], tuple[str, str]] = {}


def _auth(client, username):
    """Login once per role and restore that session cookie for later calls."""
    key = (client, username)
    if key not in _SESSION_CACHE:
        data = login(client, username)
        cookie = next(
            (item.value for item in client.cookies.jar if item.name == settings.cookie_name),
            None,
        )
        assert cookie, "Login harus menetapkan cookie sesi"
        _SESSION_CACHE[key] = (data["csrf_token"], cookie)
    csrf, cookie = _SESSION_CACHE[key]
    client.cookies.jar.clear()
    client.cookies.set(settings.cookie_name, cookie, domain="testserver.local", path="/")
    return {"X-CSRF-Token": csrf}


def _seed_attempt(client, fixtures):
    admin = _auth(client, "admin")
    subject = client.post(
        "/api/v1/admin/subjects",
        headers=admin,
        json={"code": "MTK6", "name": "Matematika Fase 6"},
    )
    assert subject.status_code == 201, subject.text
    competency = client.post(
        "/api/v1/admin/competencies",
        headers=admin,
        json={
            "subject_id": subject.json()["id"],
            "code": "MTK6-1",
            "name": "Penjumlahan",
        },
    )
    assert competency.status_code == 201, competency.text

    teacher = _auth(client, "guru")
    question = client.post(
        "/api/v1/learning/questions",
        headers=teacher,
        json={
            "subject_id": subject.json()["id"],
            "competency_id": competency.json()["id"],
            "question_type": "multiple_choice",
            "content": "Berapakah 4 + 5?",
            "points": 10,
            "options": [
                {"label": "A", "content": "8", "is_correct": False, "position": 0},
                {"label": "B", "content": "9", "is_correct": True, "position": 1},
            ],
        },
    )
    assert question.status_code == 201, question.text
    assessment = client.post(
        "/api/v1/learning/assessments",
        headers=teacher,
        json={
            "subject_id": subject.json()["id"],
            "class_id": fixtures["class1"].id,
            "title": "Asesmen Fase 6",
            "duration_min": 30,
            "is_published": True,
            "allow_offline": True,
            "question_ids": [question.json()["id"]],
        },
    )
    assert assessment.status_code == 201, assessment.text
    student = _auth(client, "siswa")
    attempt = client.post(
        f"/api/v1/learning/assessments/{assessment.json()['id']}/start", headers=student
    ).json()
    return question.json(), attempt["id"]


def _sync(client, attempt_id, question_id, client_id, answer, stamp):
    return client.put(
        f"/api/v1/learning/attempts/{attempt_id}/sync",
        headers=_auth(client, "siswa"),
        json={
            "answers": [{
                "question_id": question_id,
                "client_id": client_id,
                "answer": answer,
                "time_spent_sec": 5,
                "changed_count": 1,
                "client_updated_at": stamp.isoformat(),
            }],
            "focus_loss_count": 0,
            "page_hidden_count": 0,
        },
    )


def test_sync_conflicts_are_durable_and_resolvable(client, fixtures):
    question, attempt_id = _seed_attempt(client, fixtures)
    now = datetime.now(timezone.utc)
    newer = now
    older = now - timedelta(minutes=5)

    fresh = _sync(client, attempt_id, question["id"], "fase6-client-a", {"selected": question["options"][0]["id"]}, newer)
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["conflicts"] == []

    stale = _sync(client, attempt_id, question["id"], "fase6-client-b", {"selected": question["options"][1]["id"]}, older)
    assert stale.status_code == 200, stale.text
    assert len(stale.json()["conflicts"]) == 1

    student_conflicts = client.get("/api/v1/sync/conflicts", headers=_auth(client, "siswa")).json()
    assert student_conflicts["total"] == 1
    conflict_id = student_conflicts["items"][0]["id"]
    assert student_conflicts["items"][0]["resolution"] is None
    assert "client_updated_at" in student_conflicts["strategy"]

    teacher_conflicts = client.get(
        "/api/v1/sync/conflicts",
        headers=_auth(client, "guru"),
        params={"class_id": fixtures["class1"].id},
    ).json()
    assert teacher_conflicts["total"] == 1

    denied = client.post(
        f"/api/v1/sync/conflicts/{conflict_id}/resolve",
        headers=_auth(client, "siswa"),
        json={"resolution": "client"},
    )
    assert denied.status_code in (403, 401)

    resolved = client.post(
        f"/api/v1/sync/conflicts/{conflict_id}/resolve",
        headers=_auth(client, "guru"),
        json={"resolution": "client", "note": "Jawaban siswa yang lebih baru dipilih guru"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["client_applied"] is True

    done = client.get(
        "/api/v1/sync/conflicts",
        headers=_auth(client, "guru"),
        params={"resolved": True},
    ).json()
    assert done["total"] == 1
    assert done["items"][0]["resolution"] == "client"

    replay = _sync(client, attempt_id, question["id"], "fase6-client-b", {"selected": question["options"][1]["id"]}, older)
    assert replay.json()["conflicts"] == []

    submitted = client.post(
        f"/api/v1/learning/attempts/{attempt_id}/submit", headers=_auth(client, "siswa")
    )
    assert submitted.status_code == 200, submitted.text

    pull = client.get("/api/v1/sync/pull", headers=_auth(client, "siswa")).json()
    assert any(item["client_id"] == "fase6-client-b" for item in pull["answers"])
    assert pull["cursor"]
    again = client.get(
        "/api/v1/sync/pull",
        headers=_auth(client, "siswa"),
        params={"since": pull["cursor"]},
    ).json()
    assert again["answers"] == []


def test_retention_and_student_erasure_require_confirmation(client, fixtures):
    admin = _auth(client, "admin")
    preview = client.get("/api/v1/privacy/retention/preview", headers=admin)
    assert preview.status_code == 200, preview.text
    assert preview.json()["policy"]["student_data_retention_days"] == 365

    no_confirm = client.post(
        "/api/v1/privacy/retention/purge", headers=admin, json={"confirm": False}
    )
    assert no_confirm.status_code == 400
    purged = client.post(
        "/api/v1/privacy/retention/purge", headers=admin, json={"confirm": True}
    )
    assert purged.status_code == 200, purged.text

    student_id = fixtures["users"]["siswa"].id
    teacher = client.post(
        f"/api/v1/privacy/students/{student_id}/delete",
        headers=_auth(client, "guru"),
        json={"confirm": True},
    )
    assert teacher.status_code in (401, 403)

    request = client.post(
        f"/api/v1/privacy/students/{student_id}/delete-request",
        headers=_auth(client, "admin"),
        json={"confirm": True, "reason": "Orang tua mencabut persetujuan"},
    )
    assert request.status_code == 200, request.text
    assert request.json()["status"] == "pending"

    refused = client.post(
        f"/api/v1/privacy/students/{student_id}/delete",
        headers=_auth(client, "admin"),
        json={"confirm": False},
    )
    assert refused.status_code == 400

    erased = client.post(
        f"/api/v1/privacy/students/{student_id}/delete",
        headers=_auth(client, "admin"),
        json={"confirm": True, "reason": "Orang tua mencabut persetujuan"},
    )
    assert erased.status_code == 200, erased.text
    certificate = erased.json()
    assert certificate["method"] == "hard_delete_with_audit"
    assert "answers" in certificate["counts"]
    assert certificate["student_ref"]

    records = client.get("/api/v1/privacy/deletion-requests", headers=_auth(client, "admin")).json()
    assert any(item["status"] == "completed" and item["certificate"] for item in records["items"])

    gone = client.post(
        "/api/v1/auth/login",
        json={"username": "siswa", "password": "Testing12345!"},
    )
    assert gone.status_code in (401, 404)


def test_secret_rotation_keeps_one_cycle_and_never_returns_raw_key(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.core.security import candidate_token_hashes, token_hash
    from app.services.secrets import rotate_secret

    monkeypatch.setattr(settings, "secret_key", "old-test-key-value")
    monkeypatch.setattr(settings, "secret_key_previous", None)
    token = "session-token-for-rotation"
    old_hash = token_hash(token)
    env_path = tmp_path / ".env"

    result = rotate_secret(None, "actor-1", env_path=env_path)
    assert result["previous_key_hint"].startswith("18:")
    assert settings.secret_key not in str(result)
    assert old_hash in candidate_token_hashes(token)
    content = env_path.read_text(encoding="utf-8")
    assert "PLI_SECRET_KEY=" in content and "PLI_SECRET_KEY_PREVIOUS=old-test-key-value" in content

    second = rotate_secret(None, "actor-1", env_path=env_path)
    assert second["superseded_key_hint"]
    assert old_hash not in candidate_token_hashes(token)


def test_rotation_endpoint_is_admin_only_and_patchable(client, fixtures, monkeypatch):
    import app.api.v1.endpoints.privacy as privacy

    calls = []

    def fake_rotate(db, actor_id, *, note=None):
        calls.append((actor_id, note))
        return {
            "rotated_at": "2026-11-26T00:00:00Z",
            "key_hint": "48:abcdef123456",
            "previous_key_hint": "48:999999999999",
            "superseded_key_hint": None,
            "env_file": "server/.env",
            "note": "kunci baru hanya di server",
        }

    monkeypatch.setattr(privacy, "rotate_secret", fake_rotate)
    no_confirm = client.post(
        "/api/v1/privacy/secret/rotate",
        headers=_auth(client, "admin"),
        json={"confirm": False},
    )
    assert no_confirm.status_code == 400
    denied = client.post(
        "/api/v1/privacy/secret/rotate",
        headers=_auth(client, "guru"),
        json={"confirm": True},
    )
    assert denied.status_code in (401, 403)
    ok = client.post(
        "/api/v1/privacy/secret/rotate",
        headers=_auth(client, "admin"),
        json={"confirm": True, "note": "rotasi berkala"},
    )
    assert ok.status_code == 200, ok.text
    assert calls and calls[0][1] == "rotasi berkala"
    assert ok.json()["key_hint"] == "48:abcdef123456"
    assert "raw" not in ok.text.lower()


def test_encrypted_backup_roundtrip_and_tamper_detection(tmp_path):
    from app.services.backup_crypto import create_backup, restore_backup

    source = tmp_path / "source.db"
    with closing(sqlite3.connect(source)) as conn:
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('rahasia-siswa')")
        conn.commit()
    key = Fernet.generate_key().decode()
    folder = tmp_path / "backups"

    result = create_backup(source, folder, key)
    assert result["encrypted"] is True
    assert result["path"].suffix == ".enc"
    meta_files = list(folder.glob("*.meta.json"))
    assert len(meta_files) == 1

    target = tmp_path / "restored.db"
    restored = restore_backup(result["path"], target, key)
    assert restored["encrypted"] is True
    with closing(sqlite3.connect(target)) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == "rahasia-siswa"

    wrong = tmp_path / "wrong-key.db"
    try:
        restore_backup(result["path"], wrong, Fernet.generate_key().decode())
    except RuntimeError as error:
        assert "Kunci backup salah" in str(error)
    else:
        raise AssertionError("Salah kunci seharusnya ditolak")

    tampered = folder / "tampered.db.enc"
    data = result["path"].read_bytes()
    tampered.write_bytes(data[:-8] + b"XXXXXXXX")
    metadata = json.loads(result["metadata_path"].read_text(encoding="utf-8"))
    metadata["checksum_sha256"] = "0" * 64
    (folder / "tampered.db.meta.json").write_text(json.dumps(metadata), encoding="utf-8")
    try:
        restore_backup(tampered, tmp_path / "tampered-restored.db", key)
    except RuntimeError as error:
        assert "Checksum backup tidak cocok" in str(error)
    else:
        raise AssertionError("Backup yang diubah seharusnya ditolak")


def test_health_ready_metrics_and_ops_scope(client, fixtures):
    for path in ("/api/health", "/api/health/live", "/api/health/ready"):
        response = client.get(path)
        assert response.status_code == 200, response.text
    assert client.get("/health").status_code == 404

    metrics = client.get("/api/metrics")
    assert metrics.status_code == 200
    assert "pli_requests_total" in metrics.text

    denied = client.get("/api/v1/ops/status", headers=_auth(client, "guru"))
    assert denied.status_code in (401, 403)
    status = client.get("/api/v1/ops/status", headers=_auth(client, "admin"))
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["version"] == "6.0.0-fase6"
    assert "checks" in body and "migration_head" in body
    assert "secret" not in str(body["checks"]).lower()
