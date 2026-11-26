"""Honest dropout evaluation.

There is intentionally NO validated labelled student dataset shipped with this
project, therefore the API must report ``evaluasi_tidak_tersedia``. This module
provides the evaluation harness that can be used later when a school supplies
a validated, consented dataset, but it never exposes a model or a prediction
before that happens.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from app.core.config import DATA_DIR

DATASET_DIR = DATA_DIR / "datasets" / "dropout"
MANIFEST_PATH = DATASET_DIR / "manifest.json"
EXCLUDED_FIELDS = {"student_id", "nama", "name", "username", "full_name"}

UNAVAILABLE_REQUIREMENTS = [
    "Dataset berlabel dengan persetujuan dan kebijakan privasi yang jelas.",
    "Manifest dengan validated=true, sumber data, tanggal validasi, dan checksum.",
    "Metrik precision/recall/F1 dan confusion matrix pada data uji yang terpisah.",
    "Dokumentasi batasan: populasi, periode, dan kriteria label.",
]


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "status": "evaluasi_tidak_tersedia",
        "reason": reason,
        "requirements": UNAVAILABLE_REQUIREMENTS,
        "advisory_note": "Indikator penguasaan hanya untuk ditinjau guru, bukan prediksi ketertinggalan.",
        "computed_at": None,
    }


def load_dropout_evaluation() -> dict[str, Any]:
    """Return metrics only when a validated manifest and metric file exist."""
    if not MANIFEST_PATH.exists():
        return _unavailable(
            "Belum ada dataset tervalidasi. Tidak ada model prediksi yang diaktifkan."
        )
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _unavailable(f"Manifest dataset tidak dapat dibaca: {exc}")
    if manifest.get("validated") is not True:
        return _unavailable("Manifest dataset belum ditandai validated=true.")

    metrics_name = str(manifest.get("metrics_file") or "metrics.json")
    metrics_path = (DATASET_DIR / metrics_name).resolve()
    if DATASET_DIR.resolve() not in metrics_path.parents and metrics_path != DATASET_DIR.resolve():
        return _unavailable("Lokasi berkas metrik tidak valid.")
    if not metrics_path.exists():
        return _unavailable("Berkas metrik tidak ditemukan.")
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    expected = manifest.get("sha256")
    if expected:
        actual = hashlib.sha256(metrics_path.read_bytes()).hexdigest()
        if actual != str(expected):
            return _unavailable("Checksum metrik tidak cocok dengan manifest.")
    return {
        "available": True,
        "status": "evaluasi_tersedia",
        "reason": None,
        "metrics": payload,
        "source": manifest.get("source"),
        "validated_at": manifest.get("validated_at"),
        "limitations": manifest.get("limitations") or [],
        "requirements": UNAVAILABLE_REQUIREMENTS,
        "note": "Evaluasi deskriptif pada data uji; bukan izin untuk vonis otomatis terhadap siswa.",
    }


def _positive(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return 1 if float(value) >= 1 else 0
    text = str(value).strip().lower()
    return 1 if text in {"1", "true", "yes", "y", "dropout", "keluar"} else 0


def evaluate_dropout_dataset(
    rows: Iterable[dict[str, Any]],
    label_field: str = "dropout",
    feature_fields: Iterable[str] | None = None,
    test_size: float = 0.25,
    random_state: int = 42,
) -> dict[str, Any]:
    """Evaluate a baseline logistic model. Offline harness only.

    The caller is responsible for confirming consent and label validity before
    publishing any result through ``load_dropout_evaluation``.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score
    from sklearn.model_selection import train_test_split

    data = [dict(row) for row in rows]
    if len(data) < 20:
        raise ValueError("Dataset minimal 20 baris untuk evaluasi yang bermakna")
    if label_field not in data[0]:
        raise ValueError(f"Kolom label {label_field} tidak ditemukan")
    excluded = EXCLUDED_FIELDS | {label_field}
    fields = list(feature_fields) if feature_fields else [
        key for key in data[0] if key not in excluded
    ]
    if not fields:
        raise ValueError("Tidak ada kolom fitur yang dapat dipakai")

    import math

    X: list[list[float]] = []
    y: list[int] = []
    for row in data:
        features: list[float] = []
        for field in fields:
            try:
                value = float(row.get(field, 0))
            except (TypeError, ValueError):
                value = 0.0
            if not math.isfinite(value):
                value = 0.0
            features.append(value)
        X.append(features)
        y.append(_positive(row[label_field]))
    if len(set(y)) < 2:
        raise ValueError("Label harus memuat dua kelas (dropout dan tidak)")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )
    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)
    predicted = model.predict(X_test)
    tn, fp, fn, tp = confusion_matrix(y_test, predicted, labels=[0, 1]).ravel()
    return {
        "model": "logistic_regression_baseline",
        "n_samples": len(data),
        "n_train": len(X_train),
        "n_test": len(X_test),
        "feature_fields": fields,
        "positive_label": "dropout",
        "precision": round(float(precision_score(y_test, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, predicted, zero_division=0)), 4),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
        "limitations": [
            "Baseline linier; tidak menangkap perubahan perilaku jangka panjang.",
            "Metrik hanya berlaku untuk populasi dan periode dataset ini.",
            "Output tidak boleh dipakai sebagai vonis otomatis terhadap siswa.",
        ],
    }
