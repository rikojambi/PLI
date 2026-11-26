"""Fase 2 tests: materials, question bank, assessments, grading and scoping."""
from datetime import datetime, timedelta, timezone

from tests.conftest import TEST_PASSWORD, login


def _auth(client, username):
    data = login(client, username)
    return {"X-CSRF-Token": data["csrf_token"]}


def _subject_and_competency(client, headers):
    subject = client.post(
        "/api/v1/admin/subjects",
        headers=headers,
        json={"code": "MTK2", "name": "Matematika Uji"},
    )
    assert subject.status_code == 201, subject.text
    competency = client.post(
        "/api/v1/admin/competencies",
        headers=headers,
        json={"subject_id": subject.json()["id"], "code": "MTK2-1", "name": "Operasi hitung"},
    )
    assert competency.status_code == 201, competency.text
    return subject.json()["id"], competency.json()["id"]


def _make_question(client, headers, subject_id, competency_id, question_type="multiple_choice", **extra):
    body = {
        "subject_id": subject_id,
        "competency_id": competency_id,
        "question_type": question_type,
        "content": "Berapakah 2 + 2?",
        "points": 10,
        "difficulty": "easy",
        "options": [
            {"label": "A", "content": "3", "is_correct": False, "position": 0},
            {"label": "B", "content": "4", "is_correct": True, "position": 1},
        ],
    }
    body.update(extra)
    response = client.post("/api/v1/learning/questions", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _make_assessment(client, headers, class_id, subject_id, question_ids, **extra):
    body = {
        "subject_id": subject_id,
        "class_id": class_id,
        "title": "Asesmen Uji Fase 2",
        "duration_min": 30,
        "is_published": True,
        "question_ids": question_ids,
    }
    body.update(extra)
    response = client.post("/api/v1/learning/assessments", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_question_validation_requires_single_correct_answer(client, fixtures):
    headers = _auth(client, "admin")
    subject_id, competency_id = _subject_and_competency(client, headers)
    bad = client.post(
        "/api/v1/learning/questions",
        headers=headers,
        json={
            "subject_id": subject_id,
            "competency_id": competency_id,
            "question_type": "multiple_choice",
            "content": "Pilih dua jawaban benar",
            "options": [
                {"label": "A", "content": "1", "is_correct": True},
                {"label": "B", "content": "2", "is_correct": True},
            ],
        },
    )
    assert bad.status_code == 422


def test_objective_assessment_end_to_end(client, fixtures):
    admin_headers = _auth(client, "admin")
    subject_id, competency_id = _subject_and_competency(client, admin_headers)
    teacher_headers = _auth(client, "guru")
    question = _make_question(client, teacher_headers, subject_id, competency_id)
    assessment = _make_assessment(
        client, teacher_headers, fixtures["class1"].id, subject_id, [question["id"]]
    )
    assert assessment["question_count"] == 1
    assert assessment["max_points"] == 10

    student_headers = _auth(client, "siswa")
    available = client.get("/api/v1/learning/assessments").json()
    assert [a["title"] for a in available] == ["Asesmen Uji Fase 2"]

    started = client.post(f"/api/v1/learning/assessments/{assessment['id']}/start", headers=student_headers)
    assert started.status_code == 201, started.text
    attempt = started.json()
    assert attempt["status"] == "in_progress"
    assert len(attempt["questions"]) == 1
    # Correct-answer flags and matching keys must not leak before submission.
    assert all(option["is_correct"] is None for option in attempt["questions"][0]["options"])
    assert all(option.get("match_key") is None for option in attempt["questions"][0]["options"])
    assert attempt["questions"][0]["rubric_json"] == {}

    correct_id = question["options"][1]["id"]
    client_id = "client-answer-00001"
    synced = client.put(
        f"/api/v1/learning/attempts/{attempt['id']}/sync",
        headers=student_headers,
        json={
            "answers": [{
                "question_id": question["id"],
                "client_id": client_id,
                "answer": {"selected": correct_id},
                "time_spent_sec": 12,
                "changed_count": 1,
                "client_updated_at": datetime.now(timezone.utc).isoformat(),
            }],
            "focus_loss_count": 0,
            "page_hidden_count": 0,
        },
    )
    assert synced.status_code == 200, synced.text
    assert synced.json()["saved"] == 1

    submitted = client.post(
        f"/api/v1/learning/attempts/{attempt['id']}/submit", headers=student_headers
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["score_percent"] == 100.0
    assert body["graded_automatically"] == 1
    assert body["pending_manual"] == 0

    results = client.get("/api/v1/learning/results").json()
    assert len(results) == 1
    assert results[0]["student_name"] == "Siswa"
    assert results[0]["score"] == 100.0


def test_sync_is_idempotent_and_reports_conflicts(client, fixtures):
    admin_headers = _auth(client, "admin")
    subject_id, competency_id = _subject_and_competency(client, admin_headers)
    teacher_headers = _auth(client, "guru")
    question = _make_question(client, teacher_headers, subject_id, competency_id)
    assessment = _make_assessment(client, teacher_headers, fixtures["class1"].id, subject_id, [question["id"]])
    student_headers = _auth(client, "siswa")
    attempt = client.post(
        f"/api/v1/learning/assessments/{assessment['id']}/start", headers=student_headers
    ).json()

    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "answers": [{
            "question_id": question["id"],
            "client_id": "client-sync-test-01",
            "answer": {"selected": question["options"][1]["id"]},
            "time_spent_sec": 5,
            "changed_count": 1,
            "client_updated_at": now,
        }]
    }
    first = client.put(f"/api/v1/learning/attempts/{attempt['id']}/sync", headers=student_headers, json=payload)
    assert first.status_code == 200
    replay = client.put(f"/api/v1/learning/attempts/{attempt['id']}/sync", headers=student_headers, json=payload)
    assert replay.status_code == 200
    assert replay.json()["saved"] == 1

    old_payload = {
        "answers": [{
            "question_id": question["id"],
            "client_id": "client-sync-old-001",
            "answer": {"selected": question["options"][0]["id"]},
            "time_spent_sec": 1,
            "changed_count": 0,
            "client_updated_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        }]
    }
    conflict = client.put(f"/api/v1/learning/attempts/{attempt['id']}/sync", headers=student_headers, json=old_payload)
    assert conflict.status_code == 200
    assert len(conflict.json()["conflicts"]) == 1
    assert conflict.json()["anomaly_flags"] == []


def test_anomaly_flags_are_advisory_only(client, fixtures):
    headers = _auth(client, "admin")
    subject_id, competency_id = _subject_and_competency(client, headers)
    question = _make_question(client, headers, subject_id, competency_id)
    assessment = _make_assessment(client, headers, fixtures["class1"].id, subject_id, [question["id"]])
    student_headers = _auth(client, "siswa")
    attempt = client.post(
        f"/api/v1/learning/assessments/{assessment['id']}/start", headers=student_headers
    ).json()
    response = client.put(
        f"/api/v1/learning/attempts/{attempt['id']}/sync",
        headers=student_headers,
        json={"answers": [], "focus_loss_count": 6, "page_hidden_count": 4},
    )
    assert response.status_code == 200
    flags = response.json()["anomaly_flags"]
    assert "focus_loss_review" in flags and "page_hidden_review" in flags
    submitted = client.post(
        f"/api/v1/learning/attempts/{attempt['id']}/submit", headers=student_headers
    )
    assert submitted.status_code == 200
    # Score must be based on answers only, never on anomaly flags.
    assert submitted.json()["score_percent"] == 0.0


def test_essay_manual_grade_recalculates_result(client, fixtures):
    headers = _auth(client, "admin")
    subject_id, competency_id = _subject_and_competency(client, headers)
    question = _make_question(
        client, headers, subject_id, competency_id, "essay",
        content="Jelaskan langkah penyelesaiannya", points=20, options=[],
    )
    assessment = _make_assessment(client, headers, fixtures["class1"].id, subject_id, [question["id"]])
    student_headers = _auth(client, "siswa")
    attempt = client.post(
        f"/api/v1/learning/assessments/{assessment['id']}/start", headers=student_headers
    ).json()
    client.put(
        f"/api/v1/learning/attempts/{attempt['id']}/sync",
        headers=student_headers,
        json={"answers": [{
            "question_id": question["id"],
            "client_id": "client-essay-0001",
            "answer": {"text": "Jawaban uraian siswa"},
            "client_updated_at": datetime.now(timezone.utc).isoformat(),
        }]},
    )
    submitted = client.post(
        f"/api/v1/learning/attempts/{attempt['id']}/submit", headers=student_headers
    ).json()
    assert submitted["pending_manual"] == 1
    assert submitted["score_percent"] == 0.0

    # TestClient keeps one cookie jar: log in again before using admin headers.
    headers = _auth(client, "admin")
    answers = client.get(f"/api/v1/learning/attempts/{attempt['id']}/answers", headers=headers).json()
    assert len(answers) == 1
    graded = client.patch(
        f"/api/v1/learning/answers/{answers[0]['id']}/grade",
        headers=headers,
        json={"points_earned": 16, "feedback": "Langkah sudah benar"},
    )
    assert graded.status_code == 200, graded.text
    results = client.get("/api/v1/learning/results").json()
    assert results[0]["score"] == 80.0
    assert results[0]["graded_by"] is not None


def test_student_cannot_access_other_student_attempt_or_teacher_assessment(client, fixtures):
    admin_headers = _auth(client, "admin")
    subject_id, competency_id = _subject_and_competency(client, admin_headers)
    question = _make_question(client, admin_headers, subject_id, competency_id)
    assessment = _make_assessment(client, admin_headers, fixtures["class1"].id, subject_id, [question["id"]])
    # Create the second student while the admin session is still active.
    new_user = client.post(
        "/api/v1/admin/users",
        headers=admin_headers,
        json={
            "username": "siswalain", "full_name": "Siswa Lain",
            "password": TEST_PASSWORD, "role": "student", "class_id": fixtures["class2"].id,
        },
    )
    assert new_user.status_code == 201

    student_headers = _auth(client, "siswa")
    attempt = client.post(
        f"/api/v1/learning/assessments/{assessment['id']}/start", headers=student_headers
    ).json()
    assert client.get(f"/api/v1/learning/attempts/{attempt['id']}").status_code == 200

    # A second student in another class cannot start or read this assessment.
    other_headers = _auth(client, "siswalain")
    assert client.post(
        f"/api/v1/learning/assessments/{assessment['id']}/start", headers=other_headers
    ).status_code == 403
    assert client.get(f"/api/v1/learning/attempts/{attempt['id']}", headers=other_headers).status_code == 403


def test_notes_are_scoped_to_owner(client, fixtures):
    teacher_headers = _auth(client, "guru")
    note = client.post(
        "/api/v1/learning/notes",
        headers=teacher_headers,
        json={
            "student_id": fixtures["users"]["siswa"].id,
            "class_id": fixtures["class1"].id,
            "note_type": "encouragement",
            "title": "Tetap semangat",
            "content": "Penguasaan materi meningkat minggu ini.",
        },
    )
    assert note.status_code == 201, note.text
    student_headers = _auth(client, "siswa")
    own = client.get("/api/v1/learning/notes", headers=student_headers).json()
    assert len(own) == 1 and own[0]["is_read"] is False
    assert client.patch(f"/api/v1/learning/notes/{own[0]['id']}/read", headers=student_headers).status_code == 200
    assert client.get("/api/v1/learning/notes", headers=student_headers).json()[0]["is_read"] is True


def test_analytics_uses_real_results_only(client, fixtures):
    headers = _auth(client, "admin")
    subject_id, competency_id = _subject_and_competency(client, headers)
    question = _make_question(client, headers, subject_id, competency_id)
    assessment = _make_assessment(client, headers, fixtures["class1"].id, subject_id, [question["id"]])
    student_headers = _auth(client, "siswa")
    attempt = client.post(
        f"/api/v1/learning/assessments/{assessment['id']}/start", headers=student_headers
    ).json()
    client.put(
        f"/api/v1/learning/attempts/{attempt['id']}/sync",
        headers=student_headers,
        json={"answers": [{
            "question_id": question["id"],
            "client_id": "client-analytics-01",
            "answer": {"selected": question["options"][0]["id"]},
            "client_updated_at": datetime.now(timezone.utc).isoformat(),
        }]},
    )
    client.post(f"/api/v1/learning/attempts/{attempt['id']}/submit", headers=student_headers)
    headers = _auth(client, "admin")
    analytics = client.get(
        f"/api/v1/learning/analytics?class_id={fixtures['class1'].id}", headers=headers
    ).json()
    assert analytics["attempt_count"] == 1
    assert analytics["average_score"] == 0.0
    assert analytics["passing_count"] == 0
    assert len(analytics["students_needing_help"]) == 1
    assert analytics["hardest_competencies"][0]["accuracy_percent"] == 0.0
    assert analytics["evidence"]["source"].startswith("assessment_results")


def test_import_students_csv(client, fixtures):
    headers = _auth(client, "admin")
    csv_text = (
        "username,full_name,password,student_number,email\n"
        "siswaimport1,Siswa Import Satu,ImportPass123!,1001,import1@contoh.sch.id\n"
        "siswaimport2,Siswa Import Dua,ImportPass123!,1002,\n"
        "admin,Duplikat Admin,ImportPass123!,,\n"
    )
    response = client.post(
        f"/api/v1/learning/import-students?class_id={fixtures['class1'].id}",
        headers=headers,
        files={"file": ("siswa.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 2
    assert body["updated"] == 0  # duplicate username is skipped, never overwritten
    assert body["skipped"] == 1
    students = client.get(
        f"/api/v1/admin/classes/{fixtures['class1'].id}/students", headers=headers
    ).json()
    usernames = {s["username"] for s in students}
    assert {"siswaimport1", "siswaimport2", "siswa"} <= usernames


def test_import_students_xlsx(client, fixtures):
    from io import BytesIO

    from openpyxl import Workbook

    headers = _auth(client, "admin")
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["username", "full_name", "password", "email", "student_number"])
    sheet.append(["siswaxlsx1", "Siswa XLSX", "ImportPass123!", "xlsx@contoh.sch.id", "2001"])
    buffer = BytesIO()
    workbook.save(buffer)

    response = client.post(
        f"/api/v1/learning/import-students?class_id={fixtures['class1'].id}",
        headers=headers,
        files={"file": ("siswa.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["errors"] == []
    students = client.get(
        f"/api/v1/admin/classes/{fixtures['class1'].id}/students", headers=headers
    ).json()
    assert any(student["username"] == "siswaxlsx1" for student in students)


def test_upload_rejects_unsupported_extension(client, fixtures):
    headers = _auth(client, "guru")
    response = client.post(
        "/api/v1/learning/uploads",
        headers=headers,
        files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 400
