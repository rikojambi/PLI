"""Fase 3 tests: BKT, mastery profiles, adaptive practice, gaps and honesty."""
from uuid import uuid4

from app.core.security import hash_password
from app.db.base import utcnow
from app.models.academic import ClassMember, Competency
from app.models.assessment import Question, StudentAnswer
from app.models.core import User
from app.models.intelligence import AdaptivePractice, BktHistory
from app.services.dropout import evaluate_dropout_dataset, load_dropout_evaluation
from app.services.intelligence import bkt_update, effective_params, rebuild_mastery, validate_params
from tests.conftest import TEST_PASSWORD, login


def _auth(client, username):
    """Log in and return CSRF headers.

    TestClient keeps a single cookie jar, so call this immediately before the
    actions of the intended user (the same pattern used by test_learning.py).
    """
    data = login(client, username)
    return {"X-CSRF-Token": data["csrf_token"]}


def _subject_competency(client, headers, code="MTK3", comp_code="MTK3-1", name="Operasi hitung"):
    subject = client.post(
        "/api/v1/admin/subjects",
        headers=headers,
        json={"code": code, "name": f"Mapel {code}"},
    )
    assert subject.status_code == 201, subject.text
    competency = client.post(
        "/api/v1/admin/competencies",
        headers=headers,
        json={"subject_id": subject.json()["id"], "code": comp_code, "name": name},
    )
    assert competency.status_code == 201, competency.text
    return subject.json()["id"], competency.json()["id"]


def _question(client, headers, subject_id, competency_id, **extra):
    body = {
        "subject_id": subject_id,
        "competency_id": competency_id,
        "question_type": "multiple_choice",
        "content": "Berapakah hasil 3 + 4?",
        "points": 10,
        "difficulty": "easy",
        "options": [
            {"label": "A", "content": "6", "is_correct": False, "position": 0},
            {"label": "B", "content": "7", "is_correct": True, "position": 1},
        ],
    }
    body.update(extra)
    response = client.post("/api/v1/learning/questions", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _assessment(client, headers, class_id, subject_id, question_ids, title="Asesmen BKT"):
    response = client.post(
        "/api/v1/learning/assessments",
        headers=headers,
        json={
            "subject_id": subject_id,
            "class_id": class_id,
            "title": title,
            "duration_min": 30,
            "is_published": True,
            "question_ids": question_ids,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _submit_answer(client, student_headers, assessment_id, answers):
    started = client.post(
        f"/api/v1/learning/assessments/{assessment_id}/start", headers=student_headers
    )
    assert started.status_code == 201, started.text
    attempt = started.json()
    synced = client.put(
        f"/api/v1/learning/attempts/{attempt['id']}/sync",
        headers=student_headers,
        json={
            "answers": [
                {
                    "question_id": item["question_id"],
                    "client_id": uuid4().hex,
                    "answer": item["answer"],
                    "time_spent_sec": 12,
                    "changed_count": 0,
                    "client_updated_at": utcnow().isoformat() + "Z",
                }
                for item in answers
            ],
            "focus_loss_count": 0,
            "page_hidden_count": 0,
        },
    )
    assert synced.status_code == 200, synced.text
    submitted = client.post(
        f"/api/v1/learning/attempts/{attempt['id']}/submit", headers=student_headers
    )
    assert submitted.status_code == 200, submitted.text
    return attempt


def _correct_option(question):
    return next(option["id"] for option in question["options"] if option["is_correct"])


def _mastery_row(response, competency_id):
    return next(row for row in response["rows"] if row["competency_id"] == competency_id)


def test_bkt_math_is_bounded_and_parameters_validated():
    params = validate_params({})
    prior = params["p_init"]
    after_correct = bkt_update(prior, True, params)
    after_wrong = bkt_update(prior, False, params)
    # Correct evidence must increase mastery and beat wrong evidence.
    assert after_correct > prior
    assert after_correct > after_wrong
    assert 0.0 <= after_wrong <= 1.0 and 0.0 <= after_correct <= 1.0
    assert bkt_update(after_correct, True, params) > after_correct
    # With near-zero transition, a wrong answer must lower mastery; with
    # default transition the negative evidence can be outweighed by learning.
    low_transit = validate_params({"p_transit": 0.01})
    assert bkt_update(low_transit["p_init"], False, low_transit) < low_transit["p_init"]
    for bad in (
        {"p_slip": 0.9, "p_guess": 0.3},
        {"p_init": 0},
        {"unknown_param": 0.5},
    ):
        try:
            validate_params(bad)
        except ValueError:
            continue
        raise AssertionError(f"Parameter tidak sah diterima: {bad}")


def test_mastery_rebuild_is_idempotent_and_traceable(client, fixtures, db):
    admin = _auth(client, "admin")
    subject_id, competency_id = _subject_competency(client, admin)
    teacher = _auth(client, "guru")
    question = _question(client, teacher, subject_id, competency_id)
    assessment = _assessment(client, teacher, fixtures["class1"].id, subject_id, [question["id"]])
    student = _auth(client, "siswa")
    _submit_answer(client, student, assessment["id"], [
        {"question_id": question["id"], "answer": {"selected": _correct_option(question)}}
    ])

    response = client.get("/api/v1/intelligence/mastery").json()
    mastery = _mastery_row(response, competency_id)
    assert mastery["practice_count"] == 1
    assert mastery["correct_count"] == 1
    assert mastery["mastery_probability"] > 0.2
    assert mastery["status"] in ("developing", "proficient", "mastered")
    assert response["evidence"]["params"]["p_init"] == 0.2

    before = db.query(BktHistory).filter(BktHistory.competency_id == competency_id).count()
    rebuild_mastery(db, fixtures["users"]["siswa"].id, [competency_id])
    db.commit()
    after = db.query(BktHistory).filter(BktHistory.competency_id == competency_id).count()
    assert before == after == 1
    history = db.query(BktHistory).filter(BktHistory.competency_id == competency_id).one()
    assert history.observed_correct is True
    assert history.evidence_id is not None
    assert history.params_json["p_init"] == 0.2


def test_regrade_changes_mastery_from_real_evidence(client, fixtures, db):
    admin = _auth(client, "admin")
    subject_id, competency_id = _subject_competency(client, admin, "MTK4", "MTK4-1", "Uraian")
    teacher = _auth(client, "guru")
    essay = _question(
        client, teacher, subject_id, competency_id,
        question_type="essay", options=[], content="Jelaskan proses penjumlahan.",
    )
    assessment = _assessment(client, teacher, fixtures["class1"].id, subject_id, [essay["id"]], "Asesmen Uraian BKT")
    student = _auth(client, "siswa")
    attempt = _submit_answer(client, student, assessment["id"], [
        {"question_id": essay["id"], "answer": {"text": "3 + 4 = 7"}}
    ])
    pending = client.get("/api/v1/intelligence/mastery").json()
    assert _mastery_row(pending, competency_id)["practice_count"] == 0

    answer_id = db.query(StudentAnswer).filter(StudentAnswer.attempt_id == attempt["id"]).one().id
    teacher = _auth(client, "guru")
    graded = client.patch(
        f"/api/v1/learning/answers/{answer_id}/grade",
        headers=teacher,
        json={"points_earned": 10, "feedback": "Benar"},
    )
    assert graded.status_code == 200, graded.text

    _auth(client, "siswa")
    graded_mastery = _mastery_row(client.get("/api/v1/intelligence/mastery").json(), competency_id)
    assert graded_mastery["practice_count"] == 1
    assert graded_mastery["mastery_probability"] > 0.2
    assert db.query(BktHistory).filter(BktHistory.evidence_id == answer_id).count() == 1


def test_student_cannot_access_another_student(client, fixtures, db):
    other = User(
        school_id=fixtures["school"].id,
        role_id=fixtures["roles"]["student"].id,
        username="siswalain",
        full_name="Siswa Lain",
        password_hash=hash_password(TEST_PASSWORD),
    )
    db.add(other)
    db.flush()
    db.add(ClassMember(class_id=fixtures["class1"].id, user_id=other.id))
    db.commit()
    _auth(client, "siswa")

    for path in ("mastery", "gaps", "recommendations"):
        blocked = client.get(f"/api/v1/intelligence/{path}?student_id={other.id}")
        assert blocked.status_code == 403, (path, blocked.text)
    assert client.get("/api/v1/intelligence/mastery").json()["mode"] == "student"


def test_teacher_scoped_to_own_classes(client, fixtures, db):
    other = User(
        school_id=fixtures["school"].id,
        role_id=fixtures["roles"]["student"].id,
        username="siswakelasdua",
        full_name="Siswa Kelas Dua",
        password_hash=hash_password(TEST_PASSWORD),
    )
    db.add(other)
    db.flush()
    db.add(ClassMember(class_id=fixtures["class2"].id, user_id=other.id))
    db.commit()
    _auth(client, "guru")

    blocked = client.get(f"/api/v1/intelligence/mastery?student_id={other.id}")
    assert blocked.status_code == 403, blocked.text
    own = client.get("/api/v1/intelligence/mastery")
    assert own.status_code == 200
    assert [row["student_id"] for row in own.json()["students"]] == [fixtures["users"]["siswa"].id]
    assert client.get("/api/v1/intelligence/gaps").json()["mode"] == "class"


def test_adaptive_engine_selects_unseen_question_and_updates_mastery(client, fixtures):
    admin = _auth(client, "admin")
    subject_id, competency_id = _subject_competency(client, admin, "MTK6", "MTK6-1")
    teacher = _auth(client, "guru")
    easy = _question(client, teacher, subject_id, competency_id, content="Latihan mudah", difficulty="easy")
    hard = _question(client, teacher, subject_id, competency_id, content="Latihan sulit", difficulty="hard")
    student = _auth(client, "siswa")

    first = client.post("/api/v1/intelligence/adaptive/next-question", headers=student)
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["question"]["id"] == easy["id"]
    assert all(option["is_correct"] is None for option in payload["question"]["options"])
    assert payload["question"]["rubric_json"] == {}
    answered = client.post(
        "/api/v1/intelligence/adaptive/answer",
        headers=student,
        json={"question_id": easy["id"], "answer": {"selected": _correct_option(easy)}},
    )
    assert answered.status_code == 200, answered.text
    result = answered.json()
    assert result["is_correct"] is True
    assert result["mastery_after"] > result["mastery_before"]
    assert result["status"] in ("developing", "proficient", "mastered")

    second = client.post("/api/v1/intelligence/adaptive/next-question", headers=student).json()
    assert second["question"]["id"] == hard["id"]
    assert second["evidence"]["excluded_count"] >= 1
    mastery = _mastery_row(client.get("/api/v1/intelligence/mastery").json(), competency_id)
    assert mastery["practice_count"] == 1
    assert mastery["probability_trend"] == [result["mastery_after"]]


def test_adaptive_answer_is_idempotent_by_client_id(client, fixtures, db):
    admin = _auth(client, "admin")
    subject_id, competency_id = _subject_competency(client, admin, "MTK7", "MTK7-1")
    teacher = _auth(client, "guru")
    question = _question(client, teacher, subject_id, competency_id)
    student = _auth(client, "siswa")
    client_id = uuid4().hex
    body = {
        "question_id": question["id"],
        "answer": {"selected": question["options"][0]["id"]},
        "client_id": client_id,
    }
    first = client.post("/api/v1/intelligence/adaptive/answer", headers=student, json=body)
    assert first.status_code == 200 and first.json()["idempotent"] is False
    replay = client.post("/api/v1/intelligence/adaptive/answer", headers=student, json=body)
    assert replay.status_code == 200 and replay.json()["idempotent"] is True
    assert db.query(AdaptivePractice).filter(AdaptivePractice.client_id == client_id).count() == 1
    assert db.query(BktHistory).filter(BktHistory.competency_id == competency_id).count() == 1


def test_gap_analysis_uses_teacher_labels(client, fixtures):
    admin = _auth(client, "admin")
    subject_id, competency_id = _subject_competency(client, admin, "MTK8", "MTK8-1")
    teacher = _auth(client, "guru")
    wrong = _question(
        client, teacher, subject_id, competency_id,
        content="Salah hitung", gap_category="hitungan",
    )
    right = _question(
        client, teacher, subject_id, competency_id,
        content="Benar konsep", gap_category="konsep",
    )
    assessment = _assessment(
        client, teacher, fixtures["class1"].id, subject_id,
        [wrong["id"], right["id"]], "Asesmen Celah",
    )
    student = _auth(client, "siswa")
    bad_id = next(option["id"] for option in wrong["options"] if not option["is_correct"])
    _submit_answer(client, student, assessment["id"], [
        {"question_id": wrong["id"], "answer": {"selected": bad_id}},
        {"question_id": right["id"], "answer": {"selected": _correct_option(right)}},
    ])

    report = client.get("/api/v1/intelligence/gaps").json()
    row = next(item for item in report["rows"] if item["competency_id"] == competency_id)
    assert row["observations"] == 2
    assert row["category_counts"]["hitungan"] == 1
    assert row["dominant_category"] == "hitungan"
    assert row["accuracy_percent"] == 50.0
    assert report["evidence"]["categories"] == ["aplikasi", "hitungan", "konsep", "membaca_soal", "prosedur"]


def test_recommendations_refresh_is_scoped(client, fixtures):
    admin = _auth(client, "admin")
    subject_id, competency_id = _subject_competency(client, admin, "MTK9", "MTK9-1")
    teacher = _auth(client, "guru")
    _question(client, teacher, subject_id, competency_id)
    student = _auth(client, "siswa")

    refreshed = client.post("/api/v1/intelligence/recommendations/refresh", headers=student)
    assert refreshed.status_code == 200, refreshed.text
    assert len(refreshed.json()) >= 1
    assert all(item["student_id"] == fixtures["users"]["siswa"].id for item in refreshed.json())
    listed = client.get("/api/v1/intelligence/recommendations").json()
    assert len(listed) == len(refreshed.json())

    teacher = _auth(client, "guru")
    assert client.post(
        f"/api/v1/intelligence/recommendations/refresh?student_id={fixtures['users']['siswa'].id}",
        headers=teacher,
    ).status_code == 200


def test_dropout_evaluation_is_honest_and_metrics_are_measurable(client, fixtures):
    _auth(client, "siswa")
    result = client.get("/api/v1/intelligence/dropout-evaluation").json()
    assert result["available"] is False
    assert result["status"] == "evaluasi_tidak_tersedia"
    assert "Belum ada dataset tervalidasi" in result["reason"]
    assert load_dropout_evaluation()["status"] == "evaluasi_tidak_tersedia"
    assert result["advisory_indicators"][0]["is_prediction"] is False

    rows = []
    for index in range(60):
        label = 1 if index % 3 == 0 else 0
        rows.append({
            "student_id": f"s{index}",
            "avg_score": 40 + label * 35 + (index % 5),
            "practice_count": 3 + (index % 7),
            "dropout": label,
        })
    metrics = evaluate_dropout_dataset(rows)
    matrix = metrics["confusion_matrix"]
    assert metrics["n_samples"] == 60
    assert sum(matrix.values()) == metrics["n_test"]
    assert set(("precision", "recall", "f1")) <= metrics.keys()
    assert set(("true_negative", "false_positive", "false_negative", "true_positive")) <= matrix.keys()


def test_bkt_params_admin_only_and_effect_on_new_profiles(client, fixtures, db):
    student_headers = _auth(client, "siswa")
    assert client.get("/api/v1/intelligence/bkt-params").json()["source"] == "environment_defaults"
    assert client.put(
        "/api/v1/intelligence/bkt-params", headers=student_headers, json={"p_init": 0.5}
    ).status_code == 403
    admin = _auth(client, "admin")
    invalid = client.put(
        "/api/v1/intelligence/bkt-params",
        headers=admin,
        json={"p_slip": 0.9, "p_guess": 0.5},
    )
    assert invalid.status_code == 422
    updated = client.put(
        "/api/v1/intelligence/bkt-params",
        headers=admin,
        json={"p_init": 0.5, "recompute": True},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["params"]["p_init"] == 0.5
    assert updated.json()["recomputed_students"] >= 1
    assert client.get("/api/v1/intelligence/bkt-params").json()["source"] == "database_override"
    assert effective_params(db)["p_init"] == 0.5

    _, competency_id = _subject_competency(client, admin, "MTK10", "MTK10-1")
    _auth(client, "siswa")
    fresh = _mastery_row(client.get("/api/v1/intelligence/mastery").json(), competency_id)
    assert fresh["mastery_probability"] == 0.5
    assert fresh["status"] == "not_started"


def test_writes_require_auth_and_csrf(client, fixtures):
    unauthenticated = client.post("/api/v1/intelligence/adaptive/next-question")
    assert unauthenticated.status_code == 401, unauthenticated.text
    login(client, "siswa")  # cookie jar now has a session, but no CSRF header
    missing_csrf = client.post("/api/v1/intelligence/adaptive/next-question")
    assert missing_csrf.status_code == 403, missing_csrf.text
