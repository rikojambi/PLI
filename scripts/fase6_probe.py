"""Live probe untuk endpoint Fase 6 pada backend yang sedang berjalan.

Probe ini hanya membaca status dan menguji penolakan tanpa konfirmasi, sehingga
tidak mengganti kunci, menghapus data, atau membersihkan log pada database nyata.
Jalankan setelah fase5_probe.py dengan jeda cukup agar pembatas laju login
(10 percobaan / 5 menit per IP) tidak aktif.
"""
from __future__ import annotations

import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000"


def credentials() -> dict[str, str]:
    text = (ROOT / "data" / "demo_credentials.txt").read_text(encoding="utf-8")
    return dict(re.findall(r"^(admin|guru1|siswa1|siswa2):\s*(.+)$", text, flags=re.MULTILINE))


def login(session: requests.Session, creds: dict[str, str], username: str) -> dict[str, str]:
    session.cookies.clear()
    response = session.post(
        f"{BASE}/api/v1/auth/login",
        json={"username": username, "password": creds[username]},
        timeout=10,
    )
    response.raise_for_status()
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def check(label: str, condition: bool, detail: object = "") -> None:
    status = "OK  " if condition else "GAGAL"
    print(f"[{status}] {label}" + (f" - {detail}" if detail and not condition else ""))
    if not condition:
        raise SystemExit(1)


def main() -> None:
    creds = credentials()
    check("Kredensial demo lengkap", not ({"admin", "guru1", "siswa1"} - set(creds)))

    paths = requests.get(f"{BASE}/openapi.json", timeout=10).json()["paths"]
    required = {
        "/api/health/live",
        "/api/health/ready",
        "/api/metrics",
        "/api/v1/sync/conflicts",
        "/api/v1/sync/conflicts/{conflict_id}/resolve",
        "/api/v1/sync/pull",
        "/api/v1/privacy/retention/preview",
        "/api/v1/privacy/retention/purge",
        "/api/v1/privacy/students/{student_id}/delete-request",
        "/api/v1/privacy/students/{student_id}/delete",
        "/api/v1/privacy/deletion-requests",
        "/api/v1/privacy/secret/rotate",
        "/api/v1/ops/status",
    }
    check("Endpoint Fase 6 terdaftar", required <= set(paths), sorted(required - set(paths)))

    live = requests.get(f"{BASE}/api/health/live", timeout=10)
    ready = requests.get(f"{BASE}/api/health/ready", timeout=10)
    metrics = requests.get(f"{BASE}/api/metrics", timeout=10)
    check("Health live aktif", live.status_code == 200 and live.json()["status"] == "alive", live.text)
    check("Health ready aktif", ready.status_code == 200 and ready.json()["status"] == "ready", ready.text)
    check("Metrik tanpa kunci API", metrics.status_code == 200 and "pli_requests_total" in metrics.text, metrics.text[:120])
    check("Request ID dikembalikan", bool(live.headers.get("X-Request-ID")), dict(live.headers))

    admin = requests.Session()
    admin_headers = login(admin, creds, "admin")
    status = admin.get(f"{BASE}/api/v1/ops/status", timeout=10)
    check("Admin membaca status operasional", status.status_code == 200, status.text[:160])
    body = status.json()
    check("Status memuat pemeriksaan migrasi", "migration_head" in body and "checks" in body, body)
    check("Status tidak membocorkan kunci", "secret_key" not in str(body).lower(), body)

    preview = admin.get(f"{BASE}/api/v1/privacy/retention/preview", timeout=10)
    check("Pratinjau retensi terbaca", preview.status_code == 200 and "policy" in preview.json(), preview.text[:160])
    refused = admin.post(
        f"{BASE}/api/v1/privacy/retention/purge",
        headers=admin_headers,
        json={"confirm": False},
        timeout=10,
    )
    check("Pembersihan tanpa konfirmasi ditolak", refused.status_code == 400, refused.text)
    rotation = admin.post(
        f"{BASE}/api/v1/privacy/secret/rotate",
        headers=admin_headers,
        json={"confirm": False},
        timeout=10,
    )
    check("Rotasi tanpa konfirmasi ditolak", rotation.status_code == 400, rotation.text)

    teacher = requests.Session()
    login(teacher, creds, "guru1")
    check(
        "Guru tidak melihat status operasional",
        teacher.get(f"{BASE}/api/v1/ops/status", timeout=10).status_code in (401, 403),
    )
    check(
        "Guru tidak melihat retensi",
        teacher.get(f"{BASE}/api/v1/privacy/retention/preview", timeout=10).status_code in (401, 403),
    )
    conflicts = teacher.get(f"{BASE}/api/v1/sync/conflicts", timeout=10)
    check("Guru melihat konflik dalam cakupan", conflicts.status_code == 200, conflicts.text[:160])
    check("Strategi konflik dinyatakan", "client_updated_at" in conflicts.json()["strategy"], conflicts.json()["strategy"])

    student = requests.Session()
    login(student, creds, "siswa1")
    pull = student.get(f"{BASE}/api/v1/sync/pull", timeout=10)
    check("Siswa menarik perubahan server", pull.status_code == 200 and "cursor" in pull.json(), pull.text[:160])
    check("Siswa melihat konfliknya sendiri", student.get(f"{BASE}/api/v1/sync/conflicts", timeout=10).status_code == 200)
    check(
        "Guru tidak bisa memakai pull siswa",
        teacher.get(f"{BASE}/api/v1/sync/pull", timeout=10).status_code in (401, 403),
    )

    print("\nSemua pemeriksaan Fase 6 lulus.")


if __name__ == "__main__":
    main()
