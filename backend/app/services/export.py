"""Fase 5 server-generated Excel/PDF exports.

Exports contain only rows already authorised by the dashboard service. The
browser never assembles the file, so RBAC and school scoping stay server-side.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_HEADERS = {
    "results": [
        ("date", "Tanggal"),
        ("student_name", "Siswa"),
        ("class_name", "Kelas"),
        ("subject_name", "Mapel"),
        ("assessment_title", "Asesmen"),
        ("score", "Skor"),
        ("mastery_percent", "Penguasaan (%)"),
    ],
    "scores": [
        ("label", "Tanggal"),
        ("score", "Rata-rata skor"),
        ("mastery_percent", "Rata-rata penguasaan (%)"),
        ("attempts", "Jumlah hasil"),
    ],
    "mastery": [
        ("label", "Tanggal"),
        ("mastery_percent", "Rata-rata penguasaan BKT (%)"),
        ("observations", "Observasi"),
    ],
    "competencies": [
        ("student_name", "Siswa"),
        ("code", "Kode"),
        ("competency", "Kompetensi"),
        ("mastery_percent", "Penguasaan (%)"),
        ("status", "Status"),
        ("practice_count", "Latihan"),
        ("observations", "Observasi"),
    ],
}
_TITLES = {
    "results": "Hasil Asesmen",
    "scores": "Perkembangan Skor",
    "mastery": "Perkembangan Penguasaan (BKT)",
    "competencies": "Profil Kompetensi",
}


def _value(row: dict[str, Any], key: str) -> str:
    value = row.get(key, "")
    if value is None:
        return ""
    return str(value)


def _ascii(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


def _sheet_rows(data: dict[str, Any], sheet: str) -> list[list[str]]:
    columns = _HEADERS[sheet]
    rows = [[label for _, label in columns]]
    for item in data.get(sheet, []):
        rows.append([_value(item, key) for key, _ in columns])
    return rows


def build_xlsx(data: dict[str, Any]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet in _HEADERS:
        worksheet = workbook.create_sheet(_TITLES[sheet][:31])
        for row_index, row in enumerate(_sheet_rows(data, sheet), start=1):
            for column_index, value in enumerate(row, start=1):
                cell = worksheet.cell(row=row_index, column=column_index, value=value)
                if row_index == 1:
                    cell.font = Font(bold=True)
        for column_index, (_, label) in enumerate(_HEADERS[sheet], start=1):
            letter = worksheet.cell(row=1, column=column_index).column_letter
            worksheet.column_dimensions[letter].width = max(14, min(42, len(label) + 6))
        worksheet.freeze_panes = "A2"
    workbook.properties.title = "Laporan Perkembangan PLI"
    workbook.properties.description = "Diekspor dari data asesmen dan BKT yang terverifikasi"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_pdf(data: dict[str, Any], scope_label: str) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title="Laporan Perkembangan PLI",
        leftMargin=32,
        rightMargin=32,
        topMargin=36,
        bottomMargin=32,
    )
    styles = getSampleStyleSheet()
    story = [Paragraph(_ascii("Laporan Perkembangan Personal Learning Intelligence"), styles["Title"])]
    story.append(Paragraph(_ascii(f"Cakupan: {scope_label}"), styles["Normal"]))
    story.append(Paragraph(_ascii(f"Filter: {data.get('filters', {})}"), styles["Normal"]))
    story.append(Spacer(1, 10))

    for sheet in _HEADERS:
        rows = _sheet_rows(data, sheet)
        if len(rows) <= 1:
            continue
        story.append(Paragraph(_ascii(_TITLES[sheet]), styles["Heading2"]))
        table_rows = [[_ascii(cell) for cell in row] for row in rows[:60]]
        table = Table(table_rows, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#312e81")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(table)
        if len(rows) > 61:
            story.append(Paragraph(_ascii(f"Menampilkan 60 dari {len(rows) - 1} baris. Gunakan Excel untuk semua data."), styles["Normal"]))
        story.append(Spacer(1, 12))

    if len(story) == 4:
        story.append(Paragraph(_ascii("Data tidak tersedia untuk filter yang dipilih."), styles["Normal"]))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            _ascii("Catatan: penguasaan adalah indikator BKT dari jawaban nyata, bukan prediksi dropout atau penilaian otomatis."),
            styles["Normal"],
        )
    )
    document.build(story)
    return buffer.getvalue()


def safe_filename(prefix: str, extension: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", prefix).strip("-") or "laporan"
    return f"{clean}-{stamp}.{extension}"
