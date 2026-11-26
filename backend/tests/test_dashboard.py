"""Fase 5 tests: scoped filters, progress series, profiles and exports."""
from datetime import datetime, timedelta, timezone

from tests.conftest import login


def _auth(client, username):
    return {"X-CSRF-Token": login(client, username)["csrf_token"]}


def _seed_result(client, fixtures):
    admin = _auth(client, "admin")
    subject = client.post(
        "/api/v1/admin/subjects",
        headers=admin,
        json={"code": "MTK5", "name": "Matematika Fase 5"},
    )
    assert subject.status_code == 201, subject.text
    competency = client.post(
        "/api/v1/admin/competencies",
        headers=admin,
        json={
            "subject_id": subject.json()["id"],
            "code": "MTK5-1",
            "name": "Perkalian",
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
            "content": "Berapakah 3 × 4?",
            "points": 10,
            "options": [
                {"label": "A", "content": "7", "is_correct": False, "position": 0},
                {"label": "B", "content": "12", "is_correct": True, "position": 1},
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
            "title": "Asesmen Fase 5",
            "duration_min": 30,
            "is_published": True,
            "question_ids": [question.json()["id"]],
        },
    )
    assert assessment.status_code == 201, assessment.text
    student = _auth(client, "siswa")
    attempt = client.post(
        f"/api/v1/learning/assessments/{assessment.json()['id']}/start", headers=student
    ).json()
    synced = client.put(
        f"/api/v1/learning/attempts/{attempt['id']}/sync",
        headers=student,
        json={
            "answers": [{
                "question_id": question.json()["id"],
                "client_id": "fase5-answer-0001",
                "answer": {"selected": question.json()["options"][1]["id"]},
                "time_spent_sec": 6,
                "changed_count": 1,
                "client_updated_at": datetime.now(timezone.utc).isoformat(),
            }],
            "focus_loss_count": 0,
            "page_hidden_count": 0,
        },
    )
    assert synced.status_code == 200, synced.text
    submitted = client.post(
        f"/api/v1/learning/attempts/{attempt['id']}/submit", headers=student
    )
    assert submitted.status_code == 200, submitted.text
    return student, subject.json()["id"], competency.json()["id"]


def test_filters_overview_and_progress_use_real_data(client, fixtures):
    student_headers, subject_id, competency_id = _seed_result(client, fixtures)
    teacher = _auth(client, "guru")

    filters = client.get("/api/v1/dashboard/filters", headers=teacher).json()
    assert fixtures["class1"].id in [item["id"] for item in filters["classes"]]
    assert subject_id in [item["id"] for item in filters["subjects"]]
    assert competency_id in [item["id"] for item in filters["competencies"]]
    assert any(item["value"] == "30d" for item in filters["periods"])
    assert fixtures["users"]["siswa"].id in [item["id"] for item in filters["students"]]

    overview = client.get(
        "/api/v1/dashboard/overview",
        headers=teacher,
        params={"class_id": fixtures["class1"].id, "subject_id": subject_id, "period": "all"},
    ).json()
    assert overview["result_count"] == 1
    assert overview["average_score"] == 100.0
    assert overview["trend"][0]["score"] == 100.0

    progress = client.get(
        "/api/v1/dashboard/progress",
        headers=teacher,
        params={"competency_id": competency_id, "period": "all"},
    ).json()
    assert progress["result_count"] == 1
    assert progress["observation_count"] >= 1
    assert progress["mastery"][0]["mastery_percent"] > 0

    filtered = client.get(
        "/api/v1/dashboard/progress",
        headers=teacher,
        params={"date_from": "2001-01-01", "date_to": "2001-01-02", "period": "custom"},
    ).json()
    assert filtered["result_count"] == 0

    own = client.get("/api/v1/dashboard/overview", headers=student_headers, params={"period": "all"}).json()
    assert own["student_count"] == 1
    assert own["result_count"] == 1


def test_profile_and_export_are_scoped(client, fixtures):
    student_headers, subject_id, competency_id = _seed_result(client, fixtures)
    teacher = _auth(client, "guru")
    student_id = fixtures["users"]["siswa"].id

    profile = client.get(
        f"/api/v1/dashboard/students/{student_id}/profile",
        headers=teacher,
        params={"subject_id": subject_id, "competency_id": competency_id, "period": "all"},
    )
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["student"]["id"] == student_id
    assert body["results"][0]["score"] == 100.0
    assert body["mastery"]
    assert "bukan prediksi dropout" in body["evidence"]["note"].lower()

    # Students may see themselves but never another student.
    own = client.get(
        f"/api/v1/dashboard/students/{student_id}/profile",
        headers=student_headers,
        params={"period": "all"},
    )
    assert own.status_code == 200
    denied = client.get(
        f"/api/v1/dashboard/students/{fixtures['users']['admin'].id}/profile",
        headers=student_headers,
    )
    assert denied.status_code in (403, 404)

    xlsx = client.get("/api/v1/dashboard/export", headers=teacher, params={"format": "xlsx", "period": "all"})
    assert xlsx.status_code == 200
    assert xlsx.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert xlsx.content[:2] == b"PK"
    assert "attachment" in xlsx.headers["content-disposition"]

    pdf = client.get("/api/v1/dashboard/export", headers=teacher, params={"format": "pdf", "period": "all"})
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    own_xlsx = client.get(
        "/api/v1/dashboard/export",
        headers=student_headers,
        params={"format": "xlsx", "period": "all", "student_id": fixtures["users"]["guru"].id},
    )
    assert own_xlsx.status_code in (403, 404)
