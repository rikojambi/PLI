"""Smoke test aplikasi yang sedang berjalan (backend harus aktif di :8000)."""
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
CRED = Path(__file__).resolve().parents[1] / "data" / "demo_credentials.txt"


def credentials() -> dict[str, str]:
    result = {}
    for line in CRED.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.startswith("AKUN"):
            username, password = line.split(":", 1)
            result[username.strip()] = password.strip()
    return result


def check(label: str, condition: bool, detail: str = "") -> None:
    print(f"[{'OK' if condition else 'GAGAL'}] {label}{(' - ' + detail) if detail else ''}")
    if not condition:
        raise SystemExit(1)


def main() -> None:
    creds = credentials()
    check("file kredensial demo terbaca", len(creds) >= 4)

    with httpx.Client(base_url=BASE, timeout=10) as client:
        health = client.get("/api/health")
        check("health check", health.status_code == 200 and health.json()["status"] == "ok")

        for username, role, forbidden in [
            ("admin", "admin", None),
            ("guru1", "teacher", "/api/v1/admin/users"),
            ("siswa1", "student", "/api/v1/portal/teacher/classes"),
        ]:
            response = client.post("/api/v1/auth/login", json={
                "username": username, "password": creds[username],
            })
            check(f"login {username}", response.status_code == 200, response.text[:120])
            body = response.json()
            check(f"peran {username}", body["user"]["role"]["name"] == role)
            headers = {"X-CSRF-Token": body["csrf_token"]}
            me = client.get("/api/v1/auth/me")
            check(f"me {username}", me.status_code == 200)

            if role == "admin":
                classes = client.get("/api/v1/admin/classes")
                check("admin melihat kelas", classes.status_code == 200 and len(classes.json()) >= 1)
                logs = client.get("/api/v1/admin/audit-logs")
                check("admin melihat log audit", logs.status_code == 200 and logs.json()["total"] >= 1)
            elif role == "teacher":
                classes = client.get("/api/v1/portal/teacher/classes")
                check("guru hanya kelas sendiri", [c["name"] for c in classes.json()] == ["XII RPL 1"])
            else:
                classes = client.get("/api/v1/portal/student/classes")
                check("siswa hanya kelas sendiri", [c["name"] for c in classes.json()] == ["XII RPL 1"])

            if forbidden:
                blocked = client.get(forbidden)
                check(f"{username} ditolak di {forbidden}", blocked.status_code == 403, str(blocked.status_code))

            no_csrf = client.post("/api/v1/admin/subjects", json={"code": "X", "name": "X"})
            check(f"CSRF wajib untuk {username}", no_csrf.status_code in (403, 401))

            logout = client.post("/api/v1/auth/logout", headers=headers)
            check(f"logout {username}", logout.status_code == 200)
            check(f"sesi {username} dicabut", client.get("/api/v1/auth/me").status_code == 401)

    print("\nSemua pemeriksaan smoke test lulus.")


if __name__ == "__main__":
    main()
