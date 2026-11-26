"""Live probe untuk endpoint Fase 4 pada backend yang sedang berjalan.

Skrip ini memakai kredensial demo lokal dan memeriksa bukti bahwa konfigurasi AI,
tutor, RAG, dan generator berjalan nyata serta jujur bila penyedia belum siap.
Jalankan setelah fase3_probe.py dengan jeda cukup agar pembatas laju login
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
    return dict(re.findall(r"^(admin|guru1|siswa1):\s*(.+)$", text, flags=re.MULTILINE))


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

    admin = requests.Session()
    admin_headers = login(admin, creds, "admin")

    paths = admin.get(f"{BASE}/openapi.json", timeout=10).json()["paths"]
    fused = sorted(path for path in paths if "/ai/" in path)
    operations = sum(len(paths[path]) for path in fused)
    check("Endpoint Fase 4 terdaftar", len(fused) >= 18 and operations >= 20, (len(fused), operations))
    required = {
        "/api/v1/ai/catalog",
        "/api/v1/ai/status",
        "/api/v1/ai/budget",
        "/api/v1/ai/providers",
        "/api/v1/ai/usage",
        "/api/v1/ai/documents",
        "/api/v1/ai/rag/ask",
        "/api/v1/ai/tutor/conversations",
        "/api/v1/ai/tutor/chat",
        "/api/v1/ai/generate",
        "/api/v1/ai/generated",
    }
    check("Path inti AI tersedia", required <= set(fused), sorted(required - set(fused)))

    catalog = admin.get(f"{BASE}/api/v1/ai/catalog", timeout=10).json()
    check("Katalog 8 adapter", len(catalog["adapters"]) == 8, len(catalog["adapters"]))
    check(
        "Katalog tidak membocorkan kunci",
        all("api_key" not in item for item in catalog["adapters"]),
    )

    status = admin.get(f"{BASE}/api/v1/ai/status", timeout=10).json()
    model_ready = status["available"] is True and status["verified_models"] > 0
    check(
        "Status AI jujur sesuai inventaris",
        status["available"] is model_ready
        and (
            ("Belum ada penyedia aktif" in status["detail"])
            if not model_ready
            else ("Penyedia dan model terverifikasi siap digunakan" in status["detail"])
        ),
        status,
    )

    providers = admin.get(f"{BASE}/api/v1/ai/providers", timeout=10).json()
    check("Delapan penyedia hasil seed", len(providers) == 8, len(providers))
    model_rows = {}
    for item in providers:
        model_rows[item["id"]] = admin.get(
            f"{BASE}/api/v1/ai/providers/{item['id']}/models", timeout=10
        ).json()
    known_models = {
        provider_id: {row["model_id"] for row in rows}
        for provider_id, rows in model_rows.items()
    }
    check(
        "Model penyedia berasal dari inventaris",
        all(
            not item["model"] or item["model"] in known_models[item["id"]]
            for item in providers
        ),
        [(item["name"], item["model"]) for item in providers],
    )
    check(
        "Frontend hanya menerima referensi kunci",
        all(set(item).isdisjoint({"api_key", "api_key_value", "secret"}) for item in providers),
    )
    check(
        "Inventaris model memiliki jejak verifikasi/discovery",
        all(
            row.get("model_id")
            and (row.get("discovered") or "verified_by" in str(row.get("capabilities_json")))
            for rows in model_rows.values()
            for row in rows
        ),
        model_rows,
    )

    budget = admin.get(f"{BASE}/api/v1/ai/budget", timeout=10).json()
    check(
        "Anggaran terbaca dari server",
        {"daily_token_limit", "monthly_cost_limit_usd", "max_tokens_per_request"} <= set(budget["policy"]),
        budget,
    )
    check(
        "Catatan pemakaian terbaca",
        admin.get(f"{BASE}/api/v1/ai/usage", timeout=10).status_code == 200,
    )

    teacher = requests.Session()
    teacher_headers = login(teacher, creds, "guru1")
    check(
        "Guru membaca pustaka dokumen",
        teacher.get(f"{BASE}/api/v1/ai/documents", timeout=10).status_code == 200,
    )
    before = len(teacher.get(f"{BASE}/api/v1/ai/generated", timeout=10).json())
    competencies = teacher.get(f"{BASE}/api/v1/ai/competencies", timeout=10).json()
    check("Kompetensi untuk generator tersedia", len(competencies) > 0, competencies)
    if model_ready:
        # Jangan memanggil model lokal yang lambat di probe; uji penolakan data
        # lintas sekolah yang terjadi sebelum penyedia dipanggil.
        generate = teacher.post(
            f"{BASE}/api/v1/ai/generate",
            headers=teacher_headers,
            json={
                "kind": "material",
                "subject_id": str(uuid.uuid4()),
                "topic": "Perkalian dua angka",
                "client_id": uuid.uuid4().hex,
            },
            timeout=10,
        )
        check("Generator gagal jujur pada data invalid", generate.status_code == 400, generate.text)
        check("Draf palsu tidak dibuat", generate.status_code != 200, generate.text[:200])
    else:
        generate = teacher.post(
            f"{BASE}/api/v1/ai/generate",
            headers=teacher_headers,
            json={
                "kind": "material",
                "subject_id": competencies[0]["subject_id"],
                "topic": "Perkalian dua angka",
                "client_id": uuid.uuid4().hex,
            },
            timeout=10,
        )
        check("Generator menolak tanpa model terverifikasi", generate.status_code == 503, generate.text)
        check("Draf palsu tidak dibuat", "layanan AI tidak tersedia" in generate.json()["detail"])
    after = len(teacher.get(f"{BASE}/api/v1/ai/generated", timeout=10).json())
    check("Jumlah draf tidak berubah", before == after, (before, after))
    check(
        "CSRF wajib pada generator",
        teacher.post(
            f"{BASE}/api/v1/ai/generate",
            json={"kind": "question", "subject_id": competencies[0]["subject_id"], "topic": "Penjumlahan"},
            timeout=10,
        ).status_code == 403,
    )

    student = requests.Session()
    student_headers = login(student, creds, "siswa1")
    check(
        "Siswa hanya membaca tutor sendiri",
        student.get(f"{BASE}/api/v1/ai/tutor/conversations", timeout=10).status_code == 200,
    )
    check(
        "Guru tidak bisa masuk tutor siswa",
        teacher.get(f"{BASE}/api/v1/ai/tutor/conversations", timeout=10).status_code == 403,
    )
    check(
        "Siswa tidak bisa membaca dokumen guru",
        student.get(f"{BASE}/api/v1/ai/documents", timeout=10).status_code == 403,
    )
    check(
        "Siswa tidak bisa membaca draf guru",
        student.get(f"{BASE}/api/v1/ai/generated", timeout=10).status_code == 403,
    )
    check(
        "Percakapan siswa lain tidak dapat diakses",
        student.get(
            f"{BASE}/api/v1/ai/tutor/conversations/{uuid.uuid4()}", timeout=10
        ).status_code == 404,
    )

    rag_answer = student.post(
        f"{BASE}/api/v1/ai/rag/ask",
        headers=student_headers,
        json={
            "question": "Apa isi dokumen fotosintesis?",
            "document_id": str(uuid.uuid4()),
        },
        timeout=10,
    )
    check("RAG menjawab lewat API", rag_answer.status_code == 200, rag_answer.text)
    rag = rag_answer.json()
    check(
        "RAG mengakui data tidak tersedia",
        rag["available"] is False
        and rag["status"] == "data_tidak_tersedia"
        and "Data tidak tersedia" in rag["answer"],
        rag,
    )

    if model_ready:
        tutor_answer = student.post(
            f"{BASE}/api/v1/ai/tutor/chat",
            headers=student_headers,
            json={"message": "", "client_id": str(uuid.uuid4())},
            timeout=10,
        )
        check("Tutor menolak input kosong", tutor_answer.status_code == 422, tutor_answer.text)
        check("Tutor tidak mengarang jawaban", "message" not in tutor_answer.json(), tutor_answer.text[:200])
    else:
        tutor_answer = student.post(
            f"{BASE}/api/v1/ai/tutor/chat",
            headers=student_headers,
            json={"message": "Bantu jelaskan perkalian", "client_id": str(uuid.uuid4())},
            timeout=10,
        )
        check("Tutor menjawab lewat API", tutor_answer.status_code == 200, tutor_answer.text)
        tutor = tutor_answer.json()
        check(
            "Tutor mengakui layanan belum tersedia",
            tutor["available"] is False and "belum tersedia" in tutor["message"]["content"],
            tutor,
        )
    check(
        "CSRF wajib pada tutor",
        student.post(
            f"{BASE}/api/v1/ai/tutor/chat", json={"message": "Halo"}, timeout=10
        ).status_code == 403,
    )
    print("\nSemua pemeriksaan Fase 4 lulus.")


if __name__ == "__main__":
    main()
