"""Read the resolutions that change units after 1 July 2025 (sources of kind "unit_change").

Run with: uv run python -m pipeline.parse_unit_changes

Input:  the OCR text from pipeline.ocr_scans, with the corrections read from the page images in
        data/audit/unit-changes-2026-ocr.csv (doc_id, page, ocr, image). A correction replaces
        its OCR text on that page and applies only while the text appears there exactly once.
Output: data/interim/parsed/unit_changes.csv, one row per unit changed: source_doc, clause,
        effective (ISO date), level ("commune" or "province"), province, old_type, old_name,
        new_type, new_name.
        data/interim/parsed/unit_change_totals.csv, the commune counts a resolution states for the
        province after the change: source_doc, effective, province, total, phuong, xa.
        data/reports/unit_changes.json, rows per document, sentences not read, corrections not
        applied.

The forms read are those of the 2026 resolutions:

    a) Thành lập phường Trảng Bom trên cơ sở nguyên trạng diện tích tự nhiên và quy mô dân số
       của xã Trảng Bom.
    Thành lập thành phố Đồng Nai trên cơ sở toàn bộ diện tích tự nhiên và quy mô dân số của
       tỉnh Đồng Nai.
    2. Sau khi thành lập các phường, tỉnh Đồng Nai có 95 đơn vị hành chính cấp xã, gồm
       33 phường và 62 xã.

Clause letters are checked to run in order (a, b, c, d, đ, e, g, ...); every "x) Thành lập"
clause has to be read, or the document is reported.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from pipeline.extract import TEXT_DIR
from pipeline.fetch import MANIFEST
from pipeline.parse_resolutions import PARSED_DIR, REPORTS_DIR

KIND = "unit_change"
AUDIT = Path("data/audit/unit-changes-2026-ocr.csv")
CHANGES_OUT = PARSED_DIR / "unit_changes.csv"
TOTALS_OUT = PARSED_DIR / "unit_change_totals.csv"
REPORT = REPORTS_DIR / "unit_changes.json"
LETTERS = list("abcdđeghiklmnopqrstuvxy")  # the Vietnamese clause letters

PAGE = re.compile(r"\f?\[page (\d+)\]\n")
# "quy mô dân số" is matched loosely ("dân sô" in the OCR); the names are not.
COMMUNE = re.compile(
    r"(?<!\S)(?P<letter>\S)\) Thành lập (?P<new_type>phường|xã) (?P<new_name>[^.;:]+?) trên cơ sở "
    r"nguyên trạng diện tích tự nhiên và quy mô dân s\S+ của (?P<old_type>xã|phường) "
    r"(?P<old_name>[^.;:]+?)\."
)
PROVINCE = re.compile(  # the name stops at the next "Thành lập" (after the article heading)
    r"Thành lập (?P<new_type>thành phố) (?P<new_name>(?:(?!Thành lập)[^.;:])+?) trên cơ sở "
    r"toàn bộ diện tích tự "
    r"nhiên và quy mô dân s\S+ của (?P<old_type>tỉnh) (?P<old_name>[^.;:]+?)\."
)
# Any one character before ")" counts as a clause letter, so that a letter misread by the OCR
# ("ø)" for "g)") is reported by the letter check instead of being skipped.
CLAUSE = re.compile(r"(?<!\S)\S\) Thành lập\b")
ARTICLE_1 = re.compile(r"Điều 1\. Thành lập [^.]*? thuộc (?:tỉnh|thành phố) (?P<province>.+?) 1\.")
TOTAL = re.compile(
    r"Sau khi thành lập các phường, (?:tỉnh|thành phố) (?P<province>[^,]+?) có (?P<total>\d+) "
    r"đơn vị hành chính cấp xã, gồm (?P<phuong>\d+) phường và (?P<xa>\d+) xã\."
)
EFFECTIVE = re.compile(r"có hiệu lực thi hành từ ngày (\d{1,2}) tháng (\d{1,2}) năm (\d{4})")


def split_pages(text: str) -> list[str]:
    parts = PAGE.split(text)
    return [parts[i + 1] for i in range(1, len(parts), 2)]


def read_corrections() -> list[dict[str, str]]:
    if not AUDIT.exists():
        return []
    with AUDIT.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def correct(doc_id: str, pages: list[str], corrections: list[dict[str, str]]) -> list[str]:
    """Apply the image readings of doc_id to its pages in place; return those not applied."""
    missed = []
    for c in corrections:
        if c["doc_id"] != doc_id:
            continue
        index = int(c["page"]) - 1
        if index < len(pages) and pages[index].count(c["ocr"]) == 1:
            pages[index] = pages[index].replace(c["ocr"], c["image"])
        else:
            missed.append(f"{doc_id} page {c['page']}: {c['ocr']!r} not found once")
    return missed


def parse(doc_id: str, text: str) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    """Return (changes, stated totals, problems) for the text of one resolution."""
    flat = re.sub(r"\s+", " ", text)
    problems: list[str] = []
    effective_match = EFFECTIVE.search(flat)
    effective = ""
    if effective_match:
        day, month, year = effective_match.groups()
        effective = f"{year}-{int(month):02d}-{int(day):02d}"
    else:
        problems.append(f"{doc_id}: no effective date")
    article = ARTICLE_1.search(flat)
    province = article["province"] if article else ""
    changes: list[dict[str, str]] = []
    letters = []
    for m in COMMUNE.finditer(flat):
        letters.append(m["letter"])
        changes.append(
            {
                "source_doc": doc_id,
                "clause": f"Điều 1, khoản 1, điểm {m['letter']}",
                "effective": effective,
                "level": "commune",
                "province": province,
                "old_type": m["old_type"],
                "old_name": m["old_name"],
                "new_type": m["new_type"],
                "new_name": m["new_name"],
            }
        )
    for m in PROVINCE.finditer(flat):
        changes.append(
            {
                "source_doc": doc_id,
                "clause": "Điều 1",
                "effective": effective,
                "level": "province",
                "province": m["old_name"],
                "old_type": m["old_type"],
                "old_name": m["old_name"],
                "new_type": m["new_type"],
                "new_name": m["new_name"],
            }
        )
    clauses = len(CLAUSE.findall(flat))
    if clauses != len(letters):
        problems.append(f"{doc_id}: {clauses} clauses, {len(letters)} read")
    if letters != LETTERS[: len(letters)]:
        problems.append(f"{doc_id}: clause letters out of order: {' '.join(letters)}")
    if letters and not province:
        problems.append(f"{doc_id}: province not found in Điều 1")
    if not changes:
        problems.append(f"{doc_id}: no change read")
    totals = [
        {
            "source_doc": doc_id,
            "effective": effective,
            "province": m["province"],
            "total": m["total"],
            "phuong": m["phuong"],
            "xa": m["xa"],
        }
        for m in TOTAL.finditer(flat)
    ]
    return changes, totals, problems


def write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    corrections = read_corrections()
    changes: list[dict[str, str]] = []
    totals: list[dict[str, str]] = []
    problems: list[str] = []
    per_doc: dict[str, int] = {}
    for doc_id, entry in sorted(manifest.items()):
        if entry["kind"] != KIND:
            continue
        texts = [
            TEXT_DIR / entry["scope"] / f"{Path(f['path']).stem}.txt"
            for f in entry["files"]
            if f["path"].lower().endswith(".pdf")
        ]
        text_file = next((t for t in texts if t.exists()), None)
        if text_file is None:
            problems.append(f"{doc_id}: no text (run pipeline.ocr_scans)")
            continue
        pages = split_pages(text_file.read_text(encoding="utf-8"))
        problems += correct(doc_id, pages, corrections)
        doc_changes, doc_totals, doc_problems = parse(doc_id, "\n".join(pages))
        changes += doc_changes
        totals += doc_totals
        problems += doc_problems
        per_doc[doc_id] = len(doc_changes)
    write(CHANGES_OUT, changes, list(changes[0]) if changes else [])
    write(TOTALS_OUT, totals, list(totals[0]) if totals else [])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps({"changes": per_doc, "problems": problems}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for doc_id, n in per_doc.items():
        print(f"{doc_id:<18} {n:>3} changes")
    for line in problems:
        print(f"problem: {line}")
    print(f"-> {CHANGES_OUT}, {TOTALS_OUT}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
