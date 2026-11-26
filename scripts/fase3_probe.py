"""Live probe untuk endpoint Fase 3 pada backend yang sedang berjalan.

Skrip ini melakukan login dan permintaan baca serta satu latihan adaptif
yang benar-benar menulis data. Kredensial dibaca dari data/demo_credentials.txt.
Jalankan setelah smoke_test.py dan fase2_probe.py (urutan penting karena
pembatas laju login bersifat global per IP).
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


def check(label: str, condition: bool, detail: object = "") -> None:
    status = "OK  " if condition else "GAGAL"
    print(f"[{status}] {label}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        raise SystemExit(1)


def main() -> None:
    creds = credentials()
    missing = {"admin", "guru1", "siswa1"} - set(creds)
    check("Kredensial demo lengkap", not missing, sorted(missing))

    admin = requests.Session()
    admin_token = login(admin, creds, "admin")
    admin_headers = {"X-CSRF-Token": admin_token}
    paths = admin.get(f"{BASE}/openapi.json", timeout=10).json()["paths"]
    fused = sorted(path for path in paths if "/intelligence/" in path)
    operations = sum(len(paths[path]) for path in fused)
    check("Endpoint Fase 3 terdaftar", len(fused) >= 8 and operations >= 9, (len(fused), operations))
    required = {
        "/api/v1/intelligence/mastery",
        "/api/v1/intelligence/gaps",
        "/api/v1/intelligence/adaptive/next-question",
        "/api/v1/intelligence/adaptive/answer",
        "/api/v1/intelligence/recommendations",
        "/api/v1/intelligence/dropout-evaluation",
        "/api/v1/intelligence/bkt-params",
    }
    check("Path inti tersedia", required <= set(fused), sorted(required - set(fused)))

    params = admin.get(f"{BASE}/api/v1/intelligence/bkt-params", timeout=10).json()
    check("Parameter BKT terbaca", set(params["params"]) == {
        "p_init", "p_transit", "p_slip", "p_guess", "mastery_threshold"
    }, params)

    teacher = requests.Session()
    login(teacher, creds, "guru1")
    mastery = teacher.get(f"{BASE}/api/v1/intelligence/mastery", timeout=10)
    check("Guru membaca profil penguasaan", mastery.status_code == 200, mastery.text)
    gaps = teacher.get(f"{BASE}/api/v1/intelligence/gaps", timeout=10)
    check("Guru membaca celah belajar", gaps.status_code == 200, gaps.text)
    evaluation = teacher.get(f"{BASE}/api/v1/intelligence/dropout-evaluation", timeout=10).json()
    check(
        "Evaluasi dropout jujur (belum tersedia)",
        evaluation["available"] is False and evaluation["status"] == "evaluasi_tidak_tersedia",
        evaluation.get("status"),
    )

    student = requests.Session()
    student_token = login(student, creds, "siswa1")
    student_headers = {"X-CSRF-Token": student_token}
    own = student.get(f"{BASE}/api/v1/intelligence/mastery", timeout=10).json()
    check("Siswa hanya melihat mode sendiri", own["mode"] == "student", own.get("mode"))
    blocked = student.get(
        f"{BASE}/api/v1/intelligence/mastery?student_id=00000000-0000-0000-0000-000000000000",
        timeout=10,
    )
    check("Siswa ditolak mengakses siswa lain", blocked.status_code == 403, blocked.status_code)
    next_question = student.post(
        f"{BASE}/api/v1/intelligence/adaptive/next-question",
        headers=student_headers,
        json=None,
        timeout=10,
    )
    check("Latihan adaptif memilih soal", next_question.status_code == 200, next_question.text)
    payload = next_question.json()
    if payload["question"] is not None:
        question = payload["question"]
        check("Kunci jawaban tidak bocor", all(
            option.get("is_correct") is None for option in question["options"]
        ), question["options"])
        check("Rubrik tidak bocor", question["rubric_json"] == {}, question["rubric_json"])

    # Tulisan tanpa CSRF harus ditolak.
    no_csrf = student.post(f"{BASE}/api/v1/intelligence/adaptive/next-question", timeout=10)
    check("CSRF wajib untuk penulisan", no_csrf.status_code == 403, no_csrf.status_code)
    print("\nSemua pemeriksaan Fase 3 lulus.")


if __name__ == "__main__":
    main()
