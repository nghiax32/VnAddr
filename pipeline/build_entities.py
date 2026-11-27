"""Read the new administrative units from Decision 19/2025/QĐ-TTg.

Run with: uv run python -m pipeline.build_entities

Source: the Official Gazette (Công báo) text of 19/2025/QĐ-TTg, issues 919+920 and 921+922
        (data/interim/text/national/gazette_2025_*_19-2025-QĐ-TTg.txt, from pipeline.extract).
        Phụ lục I lists the 34 provinces, Phụ lục II the communes of each province under a heading
        that states their number by type ("Tổng số đơn vị hành chính cấp xã: 126, gồm 75 xã,
        51 phường").
        Later changes: data/interim/parsed/unit_changes.csv and unit_change_totals.csv, read by
        pipeline.parse_unit_changes from the resolutions issued after 1 July 2025.
Output: data/interim/parsed/province_new.csv (code, name, type)
        data/interim/parsed/ward_new.csv (code, name, type, province_code)
        Both hold the units as they stand after every later change ("as_of" in the report).
        data/interim/parsed/entity_changes.csv, one row per unit changed after 1 July 2025:
        level, code, effective, old_type, old_name, new_type, new_name, source_doc,
        source_clause. An address written with the name or type of before the change is found
        here.
        data/reports/entities.json, the checks below and the differences from crosswalk.csv.

Types are "tinh" or "thanh_pho" for provinces and "xa", "phuong" or "dac_khu" for communes;
names are stored without the type ("Ba Đình" for "Phường Ba Đình"). Codes are kept as strings.

Checks: 34 provinces; the headings of Phụ lục II match Phụ lục I; each province has the number of
communes of each type its heading states; codes are unique. Every line of Phụ lục II is either
read or listed as unread. The communes are then compared with the new communes of the conversion
table of the Statistics Office (crosswalk.csv, from pipeline.build_crosswalk): codes missing on
either side, codes whose names differ only in spelling (accent placement, apostrophe), and codes
with another name or province. The special zones formed from an island district that had no
communes (huyện Côn Đảo, Bạch Long Vĩ ...) have no row in the table, which maps old communes to
new ones. This comparison uses the list as Decision 19/2025 publishes it, the date of the table.

Each later change has to match exactly one unit of the old type and name, and after each
resolution the province must have the number of communes of each type the resolution states.

Decision 19/2025 (30 June 2025) is later than Official Letter 1027/CTK-CSCL (25 June 2025), which
corrected names and codes announced in Notice 915/CTK-CSCL. The list is read as the decision
publishes it, with no correction from 1027 applied on top.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from pipeline.extract import TEXT_DIR
from pipeline.parse_resolutions import PARSED_DIR, REPORTS_DIR
from pipeline.parse_resolutions_2024 import spelling

DOC_ID = "19/2025/QĐ-TTg"
PROVINCES_OUT = PARSED_DIR / "province_new.csv"
WARDS_OUT = PARSED_DIR / "ward_new.csv"
CROSSWALK = PARSED_DIR / "crosswalk.csv"
REPORT = REPORTS_DIR / "entities.json"
CHANGES = PARSED_DIR / "unit_changes.csv"  # from pipeline.parse_unit_changes
CHANGE_TOTALS = PARSED_DIR / "unit_change_totals.csv"
CHANGES_OUT = PARSED_DIR / "entity_changes.csv"
EFFECTIVE_19 = "2025-07-01"
PROVINCE_COUNT = 34

PROVINCE_TYPES = {"tỉnh": "tinh", "thành phố": "thanh_pho"}
WARD_TYPES = {"xã": "xa", "phường": "phuong", "đặc khu": "dac_khu"}

ANNEX_I_ROW = re.compile(r"^\d+ (?P<code>\d{2}) (?P<type>Tỉnh|Thành phố) (?P<name>.+)$")
HEADING = re.compile(r"^(?P<code>\d{2})\. (?P<type>TỈNH|THÀNH PHỐ) (?P<name>.+)$")
TOTAL = re.compile(r"^\(Tổng số đơn vị hành chính cấp xã: (?P<total>\d+), gồm (?P<parts>.+)\)$")
PART = re.compile(r"(?P<count>\d+) (?P<type>xã|phường|đặc khu)")
WARD_ROW = re.compile(r"^(?P<code>\d{5}) (?P<type>Phường|Xã|Đặc khu) (?P<name>.+)$")
# Lines of Phụ lục II that carry no unit: page markers, the repeated column heading and the
# note that the list continues in the next issue.
LAYOUT = re.compile(r"^(\[page \d+\]|Mã số Tên đơn vị hành chính|\(Xem tiếp Công báo .+\))$")


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text)).strip()


def gazette_lines() -> list[str]:
    """The lines of both issues, in issue order."""
    files = sorted((TEXT_DIR / "national").glob("gazette_2025_*_19-2025-Q*-TTg.txt"))
    if not files:
        raise FileNotFoundError(f"no gazette text of {DOC_ID} in {TEXT_DIR / 'national'}")
    return [nfc(line) for f in files for line in f.read_text(encoding="utf-8").splitlines()]


def parse(
    lines: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, dict[str, int]], list[str]]:
    """Return (provinces, wards, stated counts per province code, unread lines)."""
    provinces: list[dict[str, str]] = []
    wards: list[dict[str, str]] = []
    stated: dict[str, dict[str, int]] = {}
    headings: dict[str, str] = {}
    unread: list[str] = []
    annex = ""
    province = ""  # code of the province whose communes are being read
    for line in lines:
        if line == "Phụ lục I":
            annex = "I"
            continue
        if line == "Phụ lục II":
            annex, province = "II", ""
            continue
        if annex == "I":
            row = ANNEX_I_ROW.match(line)
            if row:
                provinces.append(
                    {
                        "code": row["code"],
                        "name": row["name"],
                        "type": PROVINCE_TYPES[row["type"].lower()],
                    }
                )
            continue
        if annex != "II":
            continue
        heading = HEADING.match(line)
        if heading:
            province = heading["code"]
            headings[province] = f"{heading['type']} {heading['name']}"
            continue
        if not province:
            continue  # title of the annex, or the masthead of the next issue
        if line.startswith("(Xem tiếp Công báo"):
            province = ""  # the back cover of the issue follows
            continue
        total = TOTAL.match(line)
        if total:
            counts = {WARD_TYPES[p["type"]]: int(p["count"]) for p in PART.finditer(total["parts"])}
            stated[province] = {"total": int(total["total"]), **counts}
            continue
        row = WARD_ROW.match(line)
        if row:
            wards.append(
                {
                    "code": row["code"],
                    "name": row["name"],
                    "type": WARD_TYPES[row["type"].lower()],
                    "province_code": province,
                }
            )
            continue
        if line and not LAYOUT.match(line):
            unread.append(line)
    labels = {v: k for k, v in PROVINCE_TYPES.items()}
    listed = {p["code"]: f"{labels[p['type']]} {p['name']}" for p in provinces}
    for code, heading_name in headings.items():
        if heading_name.casefold() != listed.get(code, "").casefold():
            unread.append(f"heading {code} {heading_name!r} does not match Phụ lục I")
    return provinces, wards, stated, unread


def check(
    provinces: list[dict[str, str]],
    wards: list[dict[str, str]],
    stated: dict[str, dict[str, int]],
) -> list[str]:
    problems = []
    if len(provinces) != PROVINCE_COUNT:
        problems.append(f"{len(provinces)} provinces in Phụ lục I, expected {PROVINCE_COUNT}")
    for kind, rows in (("province", provinces), ("commune", wards)):
        for code, n in Counter(r["code"] for r in rows).items():
            if n > 1:
                problems.append(f"{kind} code {code} listed {n} times")
    for p in provinces:
        if p["code"] not in stated:
            problems.append(f"province {p['code']} has no commune list in Phụ lục II")
    for code, counts in sorted(stated.items()):
        found = Counter(w["type"] for w in wards if w["province_code"] == code)
        if sum(found.values()) != counts["total"]:
            problems.append(
                f"province {code}: {sum(found.values())} communes, stated {counts['total']}"
            )
        for unit_type in WARD_TYPES.values():
            if found[unit_type] != counts.get(unit_type, 0):
                problems.append(
                    f"province {code}: {found[unit_type]} {unit_type}, "
                    f"stated {counts.get(unit_type, 0)}"
                )
    return problems


def full_name(ward: dict[str, str]) -> str:
    label = {v: k for k, v in WARD_TYPES.items()}[ward["type"]]
    return f"{label.capitalize()} {ward['name']}"


def compare_crosswalk(wards: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Differences between Phụ lục II and the new communes of crosswalk.csv."""
    if not CROSSWALK.exists():
        return {}
    with CROSSWALK.open(encoding="utf-8") as handle:
        table = {
            r["new_ward_code"]: {
                "name": r["new_ward_name"],
                "province_code": r["new_province_code"],
            }
            for r in csv.DictReader(handle)
        }
    listed = {w["code"]: w for w in wards}
    differ: list[dict[str, str]] = []
    spelled: list[dict[str, str]] = []
    for code in sorted(listed.keys() & table.keys()):
        decision, nso = listed[code], table[code]
        if full_name(decision) == nso["name"] and decision["province_code"] == nso["province_code"]:
            continue
        pair = {
            "code": code,
            "decision": f"{full_name(decision)} ({decision['province_code']})",
            "crosswalk": f"{nso['name']} ({nso['province_code']})",
        }
        same = decision["province_code"] == nso["province_code"]
        (
            spelled if same and spelling(full_name(decision)) == spelling(nso["name"]) else differ
        ).append(pair)
    return {
        "only_decision": [
            {"code": c, "name": full_name(listed[c])} for c in sorted(listed.keys() - table.keys())
        ],
        "only_crosswalk": [
            {"code": c, "name": table[c]["name"]} for c in sorted(table.keys() - listed.keys())
        ],
        "spelling": spelled,
        "differ": differ,
    }


def write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def apply_changes(
    provinces: list[dict[str, str]],
    wards: list[dict[str, str]],
    changes: list[dict[str, str]],
    totals: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[str]]:
    """Apply the later changes to the units in place, one document at a time in order of
    effect; return (one row per unit changed, problems). Codes do not change: Decision 19/2025,
    Điều 3, khoản 3 keeps the code of a unit that is renamed or changes from rural to urban."""
    applied: list[dict[str, str]] = []
    problems: list[str] = []
    documents = sorted({(c["effective"], c["source_doc"]) for c in changes})
    for effective, doc_id in documents:
        for c in (c for c in changes if c["source_doc"] == doc_id):
            if c["level"] == "province":
                matches = [
                    p
                    for p in provinces
                    if p["name"] == c["old_name"] and p["type"] == PROVINCE_TYPES[c["old_type"]]
                ]
                new_type = PROVINCE_TYPES[c["new_type"]]
            else:
                codes = {p["code"] for p in provinces if p["name"] == c["province"]}
                matches = [
                    w
                    for w in wards
                    if w["province_code"] in codes
                    and w["name"] == c["old_name"]
                    and w["type"] == WARD_TYPES[c["old_type"]]
                ]
                new_type = WARD_TYPES[c["new_type"]]
            unit = f"{c['old_type']} {c['old_name']} ({c['province']})"
            if len(matches) != 1:
                problems.append(f"{doc_id} {c['clause']}: {unit} matches {len(matches)} units")
                continue
            [match] = matches
            applied.append(
                {
                    "level": c["level"],
                    "code": match["code"],
                    "effective": effective,
                    "old_type": match["type"],
                    "old_name": match["name"],
                    "new_type": new_type,
                    "new_name": c["new_name"],
                    "source_doc": doc_id,
                    "source_clause": c["clause"],
                }
            )
            match["type"], match["name"] = new_type, c["new_name"]
        for t in (t for t in totals if t["source_doc"] == doc_id):
            codes = {p["code"] for p in provinces if p["name"] == t["province"]}
            found = Counter(w["type"] for w in wards if w["province_code"] in codes)
            stated = {"total": int(t["total"]), "phuong": int(t["phuong"]), "xa": int(t["xa"])}
            counted = {"total": sum(found.values()), "phuong": found["phuong"], "xa": found["xa"]}
            if counted != stated:
                problems.append(f"{doc_id}: {t['province']} has {counted}, stated {stated}")
    return applied, problems


def main() -> int:
    provinces, wards, stated, unread = parse(gazette_lines())
    problems = check(provinces, wards, stated)
    differences = compare_crosswalk(wards)
    applied, change_problems = apply_changes(
        provinces, wards, read_csv(CHANGES), read_csv(CHANGE_TOTALS)
    )
    write(PROVINCES_OUT, provinces, ["code", "name", "type"])
    write(WARDS_OUT, wards, ["code", "name", "type", "province_code"])
    write(CHANGES_OUT, applied, list(applied[0]) if applied else [])
    as_of = max([EFFECTIVE_19, *(a["effective"] for a in applied)])
    report = {
        "source_doc": DOC_ID,
        "as_of": as_of,
        "provinces": len(provinces),
        "communes": len(wards),
        "communes_by_type": dict(Counter(w["type"] for w in wards)),
        "problems": problems,
        "unread": unread,
        "changes_applied": dict(Counter(a["source_doc"] for a in applied)),
        "change_problems": change_problems,
        "crosswalk": differences,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"{len(provinces)} provinces, {len(wards)} communes {report['communes_by_type']} "
        f"as of {as_of}, {len(applied)} later changes -> {PROVINCES_OUT}, {WARDS_OUT}"
    )
    for line in problems + unread + change_problems:
        print(f"problem: {line}")
    for kind, rows in differences.items():
        print(f"crosswalk {kind}: {len(rows)}")
    return 1 if problems or unread or change_problems else 0


if __name__ == "__main__":
    sys.exit(main())
