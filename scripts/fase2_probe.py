"""Live probe untuk endpoint Fase 2 pada backend yang sedang berjalan.

Skrip ini hanya melakukan login dan permintaan baca (GET) serta satu pengecekan
CSRF tanpa penulisan data. Kredensial dibaca dari data/demo_credentials.txt.
"""
from __future__ import annotations

import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"


def credentials() -> dict[str, str]:
    text = (ROOT / "data" / "demo_credentials.txt").read_text(encoding="utf-8")
    return dict(re.findall(r"^(admin|guru1|siswa1):\s*(.+)$", text, flags=re.MULTILINE))


def login(session: requests.Session, creds: dict[str, str], username: str) -> str:
    session.cookies.clear()
    response = session.post(
        f"{BASE}/api/v1/auth/login",
        json={"username": username, "password": creds[username]},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["csrf_token"]


def main() -> None:
    creds = credentials()
    required = {"admin", "guru1", "siswa1"}
    missing = required - creds.keys()
    if missing:
        raise SystemExit(f"Kredensial demo tidak lengkap: {sorted(missing)}")

    spec = requests.get(f"{BASE}/openapi.json", timeout=10)
    spec.raise_for_status()
    body = spec.json()
    paths = body["paths"]
    learning = [path for path in paths if path.startswith("/api/v1/learning/")]
    assert any(path.endswith("/attempts/{attempt_id}/sync") for path in learning), "route sync tidak terdaftar"
    assert any(path.endswith("/answers/{answer_id}/grade") for path in learning), "route grade tidak terdaftar"
    assessment_schema = body["components"]["schemas"]["AssessmentOut"]["properties"]
    assert "question_ids" in assessment_schema, "AssessmentOut belum mengembalikan question_ids"
    print(f"OK  OpenAPI: {len(learning)} jalur /api/v1/learning/* terdaftar")

    admin = requests.Session()
    admin_csrf = login(admin, creds, "admin")
    for path in ("/materials", "/questions", "/assessments", "/results", "/notes", "/analytics"):
        response = admin.get(f"{BASE}/api/v1/learning{path}", timeout=10)
        assert response.status_code == 200, (path, response.status_code, response.text)
        if path == "/assessments":
            for row in response.json():
                assert "question_ids" in row, " respons asesmen tanpa question_ids"
    print("OK  Admin: semua endpoint baca Fase 2 merespons 200")

    unauthenticated = requests.post(
        f"{BASE}/api/v1/learning/materials", json={"subject_id": "x", "title": "Uji CSRF"}, timeout=10
    )
    assert unauthenticated.status_code in (401, 403), unauthenticated.status_code
    print(f"OK  Tulis tanpa CSRF/sesi ditolak ({unauthenticated.status_code})")

    teacher = requests.Session()
    login(teacher, creds, "guru1")
    for path in ("/materials", "/questions", "/assessments", "/results", "/notes", "/analytics"):
        response = teacher.get(f"{BASE}/api/v1/learning{path}", timeout=10)
        assert response.status_code == 200, (path, response.status_code, response.text)
    print("OK  Guru: semua endpoint baca Fase 2 merespons 200")

    student = requests.Session()
    login(student, creds, "siswa1")
    for path in ("/materials", "/assessments", "/results", "/notes"):
        response = student.get(f"{BASE}/api/v1/learning{path}", timeout=10)
        assert response.status_code == 200, (path, response.status_code, response.text)
    blocked = student.get(f"{BASE}/api/v1/learning/questions", timeout=10)
    assert blocked.status_code == 403, blocked.status_code
    print("OK  Siswa: endpoint siswa 200, bank soal guru ditolak (403)")
    print(f"CSRF admin: {admin_csrf[:8]}… (hanya untuk diagnosa, bukan rahasia)")


if __name__ == "__main__":
    main()
