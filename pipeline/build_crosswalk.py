"""Read the official new-old commune conversion table of the Statistics Office (Cục Thống kê).

Run with: uv run python -m pipeline.build_crosswalk

Source: https://danhmuchanhchinh.nso.gov.vn/ , file "Bảng chuyển đổi ĐVHC mới - cũ"
        (data/raw/national/nso_chuyen_doi_moi_cu.xlsx, sheet "Tổng hợp_không merge").
Output: data/interim/parsed/crosswalk.csv, one row per (new commune, old commune):
        new_province_code, new_ward_code, new_ward_name, old_ward_code, old_ward_name,
        old_district_code, old_district_name, old_province_code, old_province_name, share

share is "full" ("Nhập toàn bộ"), "part" ("Nhập một phần") or the note as written.
Codes are kept as strings with their leading zeros.

Errors found in the table are corrected from pipeline/crosswalk_corrections.csv, one field
at a time, each with the document that shows the right value. A correction applies only while
the table still holds the wrong value it names; the corrected rows say so in the correction
column, and the source file itself is left as published. Where the table gives one old code to
two communes, the correction also names the commune (old_ward_name) whose row it changes.
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from pathlib import Path

import openpyxl

from pipeline.parse_resolutions import PARSED_DIR

SOURCE = Path("data/raw/national/nso_chuyen_doi_moi_cu.xlsx")
SHEET = "Tổng hợp_không merge"
OUTPUT = PARSED_DIR / "crosswalk.csv"
CORRECTIONS = Path(__file__).parent / "crosswalk_corrections.csv"
NAME_CODE = re.compile(r"^(?P<name>.+?)\s*\((?P<code>\d+)\)\s*$")


def share_of(note: str) -> str:
    """The note column is free text ("Nhập toàn bộ", "Nhâp một phần diện tích",
    "Phần còn lại sau khi tách ...", "Giữ nguyên", "Đổi tên" ...)."""
    lowered = note.lower().replace("nhâp", "nhập")
    if "một phần" in lowered or "phần còn lại" in lowered:
        return "part"
    if "toàn bộ" in lowered:
        return "full"
    if "giữ nguyên" in lowered:
        return "unchanged"
    if "đổi tên" in lowered or "đổi loại hình" in lowered:
        return "renamed"
    return note


FIELDS = [
    "new_province_code",
    "new_province_name",
    "new_ward_code",
    "new_ward_name",
    "old_ward_code",
    "old_ward_name",
    "old_district_code",
    "old_district_name",
    "old_province_code",
    "old_province_name",
    "share",
    "note",
    "correction",
]


def text(value: object) -> str:
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", str(value or ""))).strip()


def name_code(value: object) -> tuple[str, str]:
    match = NAME_CODE.match(text(value))
    return (match["name"], match["code"]) if match else (text(value), "")


def code(value: object, width: int) -> str:
    raw = text(value)
    return raw.zfill(width) if raw.isdigit() else raw


def correct(rows: list[dict[str, str]]) -> list[str]:
    """Apply CORRECTIONS to rows in place; return the corrections that did not apply."""
    if not CORRECTIONS.exists():
        return []
    with CORRECTIONS.open(encoding="utf-8") as handle:
        corrections = list(csv.DictReader(handle))
    missed = []
    for c in corrections:
        hits = [
            r
            for r in rows
            if r["old_ward_code"] == c["old_ward_code"]
            and r[c["field"]] == c["wrong"]
            and (not c.get("old_ward_name") or r["old_ward_name"] == c["old_ward_name"])
        ]
        if not hits:
            missed.append(f"{c['old_ward_code']} {c['field']}: {c['wrong']!r} not in the table")
        for r in hits:
            r[c["field"]] = c["correct"]
            done = f"{c['field']}: {c['wrong']} -> {c['correct']} ({c['source']})"
            r["correction"] = "; ".join(x for x in (r["correction"], done) if x)
    return missed


def main() -> int:
    workbook = openpyxl.load_workbook(SOURCE, read_only=True)
    rows = []
    sheet = next(ws for ws in workbook.worksheets if ws.title.strip() == SHEET)
    for values in sheet.iter_rows(min_row=3, values_only=True):
        province, new_name, new_code, old_name, old_code, note, district, old_province = values[:8]
        if not new_name or not old_name:
            continue  # province heading rows
        new_province_name, new_province_code = name_code(province)
        district_name, district_code = name_code(district)
        old_province_name, old_province_code = name_code(old_province)
        rows.append(
            {
                "new_province_code": new_province_code,
                "new_province_name": new_province_name,
                "new_ward_code": code(new_code, 5),
                "new_ward_name": text(new_name),
                "old_ward_code": code(old_code, 5),
                "old_ward_name": text(old_name),
                "old_district_code": district_code.zfill(3) if district_code else "",
                "old_district_name": district_name,
                "old_province_code": old_province_code.zfill(2) if old_province_code else "",
                "old_province_name": old_province_name,
                "share": share_of(text(note)),
                "note": text(note),
                "correction": "",
            }
        )
    missed = correct(rows)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    new_codes = {r["new_ward_code"] for r in rows}
    old_codes = {r["old_ward_code"] for r in rows}
    shares: dict[str, int] = {}
    for r in rows:
        shares[r["share"]] = shares.get(r["share"], 0) + 1
    print(
        f"{len(rows)} rows, {len(new_codes)} new communes, {len(old_codes)} old communes, "
        f"shares {shares}, {sum(bool(r['correction']) for r in rows)} rows corrected -> {OUTPUT}"
    )
    for line in missed:
        print(f"correction not applied: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
