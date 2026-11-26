"""Live probe untuk endpoint Fase 5 pada backend yang sedang berjalan.

Probe ini tidak mengubah data. Ia memastikan filter,grafik,profil,dan ekspor
benar-benar berasal dari API dan tunduk pada cakupan peran.
Jalankan setelah probe Fase 4 dengan jeda cukup agar pembatas laju login
(10 percobaan / 5 menit per IP) tidak aktif.
"""
from __future__ import annotations

import re
import uuid
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
    check("Kredensial demo lengkap", not ({"guru1", "siswa1"} - set(creds)))

    teacher = requests.Session()
    teacher_headers = login(teacher, creds, "guru1")

    paths = teacher.get(f"{BASE}/openapi.json", timeout=10).json()["paths"]
    required = {
        "/api/v1/dashboard/filters",
        "/api/v1/dashboard/overview",
        "/api/v1/dashboard/progress",
        "/api/v1/dashboard/students/{student_id}/profile",
        "/api/v1/dashboard/export",
    }
    check("Endpoint Fase 5 terdaftar", required <= set(paths), sorted(required - set(paths)))

    filters = teacher.get(f"{BASE}/api/v1/dashboard/filters", timeout=10).json()
    check("Filter berisi kelas", len(filters["classes"]) > 0, filters)
    check("Filter berisi mapel", len(filters["subjects"]) > 0, filters)
    check("Filter berisi kompetensi", len(filters["competencies"]) > 0, filters)
    check("Filter berisi siswa dalam cakupan", len(filters["students"]) > 0, filters)
    check("Periode tersedia", any(item["value"] == "30d" for item in filters["periods"]), filters["periods"])

    overview = teacher.get(f"{BASE}/api/v1/dashboard/overview?period=all", timeout=10).json()
    progress = teacher.get(f"{BASE}/api/v1/dashboard/progress?period=all", timeout=10).json()
    check("Ringkasan memakai data asesmen nyata", overview["evidence"]["source"].startswith("assessment_results"), overview)
    check("Jumlah hasil konsisten", overview["result_count"] == progress["result_count"], (overview["result_count"], progress["result_count"]))
    check("Grafik nilai tersedia dalam bentuk data", isinstance(overview["trend"], list), overview["trend"])
    check("Grafik penguasaan bersumber dari BKT", "bkt_history" in progress["evidence"]["source"], progress["evidence"])
    if overview["result_count"] > 0:
        scores = [row["score"] for row in overview["trend"]]
        check("Nilai grafik terbaca", all(isinstance(item, (int, float)) for item in scores), scores)

    custom = teacher.get(
        f"{BASE}/api/v1/dashboard/progress",
        params={"period": "custom", "date_from": "2001-01-01", "date_to": "2001-01-02"},
        timeout=10,
    ).json()
    check("Filter rentang tanggal benar-benar menyaring", custom["result_count"] == 0, custom)

    xlsx = teacher.get(f"{BASE}/api/v1/dashboard/export?format=xlsx&period=all", timeout=30)
    check("Ekspor Excel lewat API", xlsx.status_code == 200 and xlsx.content[:2] == b"PK", xlsx.text[:120])
    check("Excel dikirim sebagai lampiran", "attachment" in xlsx.headers.get("content-disposition", ""))
    pdf = teacher.get(f"{BASE}/api/v1/dashboard/export?format=pdf&period=all", timeout=30)
    check("Ekspor PDF lewat API", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", pdf.text[:120])

    student = requests.Session()
    student_headers = login(student, creds, "siswa1")
    own_filters = student.get(f"{BASE}/api/v1/dashboard/filters", timeout=10).json()
    check("Siswa hanya menerima dirinya dalam filter", len(own_filters["students"]) == 1, own_filters["students"])
    own_id = own_filters["students"][0]["id"]
    profile = student.get(
        f"{BASE}/api/v1/dashboard/students/{own_id}/profile?period=all", timeout=10
    )
    check("Siswa membaca profil sendiri", profile.status_code == 200, profile.text[:160])
    check(
        "Profil jujur bukan prediksi dropout",
        "bukan prediksi dropout" in profile.json()["evidence"]["note"].lower(),
        profile.json()["evidence"],
    )
    denied = student.get(
        f"{BASE}/api/v1/dashboard/students/{uuid.uuid4()}/profile",
        timeout=10,
    )
    check("Profil siswa lain ditolak", denied.status_code in (403, 404), denied.status_code)
    other_id = next((item["id"] for item in filters["students"] if item["id"] != own_id), str(uuid.uuid4()))
    foreign_export = student.get(
        f"{BASE}/api/v1/dashboard/export",
        params={"format": "xlsx", "period": "all", "student_id": other_id},
        timeout=10,
    )
    check("Ekspor lintas siswa ditolak", foreign_export.status_code in (403, 404), foreign_export.status_code)

    print("\nSemua pemeriksaan Fase 5 lulus.")


if __name__ == "__main__":
    main()
