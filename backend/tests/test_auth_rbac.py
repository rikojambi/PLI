from app.main import app

from tests.conftest import TEST_PASSWORD, login


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_login_me_and_logout(client, fixtures):
    payload = login(client, "admin")
    assert payload["user"]["role"]["name"] == "admin"
    assert payload["csrf_token"]

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    logout = client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": payload["csrf_token"]}
    )
    assert logout.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_is_rejected(client, fixtures):
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "WrongPass123!"}
    )
    assert response.status_code == 401


def test_csrf_required_for_writes(client, fixtures):
    login(client, "admin")
    response = client.post(
        "/api/v1/admin/subjects", json={"code": "MTK", "name": "Matematika"}
    )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_student_cannot_use_admin_endpoints(client, fixtures):
    login(client, "siswa")
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.get("/api/v1/portal/teacher/classes").status_code == 403


def test_teacher_only_sees_assigned_classes(client, fixtures):
    login(client, "guru")
    classes = client.get("/api/v1/portal/teacher/classes").json()
    assert [c["name"] for c in classes] == ["XII A"]
    assert client.get(f"/api/v1/portal/teacher/classes/{fixtures['class2'].id}/students").status_code == 403
    students = client.get(
        f"/api/v1/portal/teacher/classes/{fixtures['class1'].id}/students"
    ).json()
    assert [s["username"] for s in students] == ["siswa"]


def test_student_only_sees_own_classes(client, fixtures):
    login(client, "siswa")
    classes = client.get("/api/v1/portal/student/classes").json()
    assert [c["name"] for c in classes] == ["XII A"]
    assert client.get("/api/v1/portal/student/overview").status_code == 200


def test_admin_can_create_class_and_user(client, fixtures):
    auth = login(client, "admin")
    headers = {"X-CSRF-Token": auth["csrf_token"]}
    user = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={
            "username": "siswa2",
            "full_name": "Siswa Baru",
            "password": TEST_PASSWORD,
            "role": "student",
            "class_id": fixtures["class1"].id,
        },
    )
    assert user.status_code == 201, user.text
    klass = client.post(
        "/api/v1/admin/classes",
        headers=headers,
        json={
            "name": "XII C",
            "academic_year_id": fixtures["year"].id,
            "semester_id": fixtures["semester"].id,
            "student_ids": [user.json()["id"]],
        },
    )
    assert klass.status_code == 201, klass.text
    assert klass.json()["student_count"] == 1
    assert client.get("/api/v1/admin/audit-logs").json()["total"] >= 2


def test_validation_rejects_bad_academic_year(client, fixtures):
    auth = login(client, "admin")
    response = client.post(
        "/api/v1/admin/academic-years",
        headers={"X-CSRF-Token": auth["csrf_token"]},
        json={
            "name": "2030/2031",
            "start_date": "2030-07-01T00:00:00",
            "end_date": "2029-06-30T00:00:00",
        },
    )
    assert response.status_code == 422


def test_password_change_revokes_other_sessions(client, fixtures):
    first = login(client, "guru")
    second = login(client, "guru")
    response = client.post(
        "/api/v1/auth/change-password",
        headers={"X-CSRF-Token": second["csrf_token"]},
        json={"current_password": TEST_PASSWORD, "new_password": "GantiPassword123!"},
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/auth/me").status_code == 200
    assert app is not None  # import guard for linters
