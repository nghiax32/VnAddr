"""Compare the commune tables with the data of the vietnamadminunits library.

Run with: uv run python -m pipeline.crosscheck_vietnamadminunits

vietnamadminunits (https://github.com/tranngocminhhieu/vietnamadminunits, MIT license) is a dev
dependency. Its data is read only to compare with; nothing of it is copied into the tables or
into src/vn_addr/data/, and a difference is listed for review, not corrected to match it.

Inputs:  data/interim/parsed/ward_new.csv, entity_changes.csv   pipeline.build_entities
         data/interim/parsed/crosswalk.csv                      pipeline.build_crosswalk
         vietnamadminunits/data/dataset.db                      tables admin_units (34
                                                                provinces) and
                                                                admin_units_legacy (63)
         vietnamadminunits/data/converter_2025.json             old commune -> new commune
Output:  data/reports/diff_vietnamadminunits.csv, one row per difference:
         check ("new_unit", "old_unit", "mapping"), province (new code), code, name, field,
         ours, theirs, note.

Checks:
1. new_unit: the 3,321 communes, by code: name, type and province. A type changed after
   1 July 2025 (entity_changes.csv) is noted with its document.
2. old_unit: the communes before 1 July 2025, by code: name, district and province.
3. mapping:  for each old commune code, the new communes it moves into. The library keys its
   mapping by name ("tinhtiengiang_thanhphomytho_phuong4"); the keys are turned into codes
   through its own two tables. A district without communes (the five special zones) has no
   commune code and is left out, as in pipeline.crosscheck_crosswalk.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

from pipeline.crosscheck_crosswalk import district_key, norm
from pipeline.parse_resolutions import PARSED_DIR, REPORTS_DIR

WARDS = PARSED_DIR / "ward_new.csv"
CHANGES = PARSED_DIR / "entity_changes.csv"
CROSSWALK = PARSED_DIR / "crosswalk.csv"
REPORT = REPORTS_DIR / "diff_vietnamadminunits.csv"
FIELDS = ["check", "province", "code", "name", "field", "ours", "theirs", "note"]
TYPES = {"Phường": "phuong", "Xã": "xa", "Đặc khu": "dac_khu"}
SPELLING = "spelling only (diacritics, spaces, hyphens)"

Row = dict[str, str]


def library_data() -> Path:
    spec = importlib.util.find_spec("vietnamadminunits")
    if spec is None or spec.origin is None:
        raise SystemExit("vietnamadminunits is not installed: uv sync --group dev")
    return Path(spec.origin).parent / "data"


def read(path: Path) -> list[Row]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def diff(
    check: str,
    province: str,
    code: str,
    name: str,
    field: str,
    ours: str,
    theirs: str,
    note: str = "",
) -> Row:
    return dict(zip(FIELDS, [check, province, code, name, field, ours, theirs, note], strict=True))


def plain(name: str) -> str:
    """The name without diacritics, spaces, hyphens or apostrophes: "Đăk Đoa" -> "dakdoa"."""
    text = unicodedata.normalize("NFD", name.replace("Đ", "D").replace("đ", "d"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def spelling(ours: str, theirs: str) -> str:
    return SPELLING if plain(ours) == plain(theirs) else ""


def compare_new(wards: list[Row], theirs: list[Row], changes: list[Row]) -> list[Row]:
    """theirs: rows of admin_units."""
    by_code = {r["wardCode"]: r for r in theirs}
    changed = {
        c["code"]: c for c in changes if c["level"] == "commune" and c["old_type"] != c["new_type"]
    }
    found = []
    for w in wards:
        t = by_code.get(w["code"])
        if t is None:
            found.append(
                diff("new_unit", w["province_code"], w["code"], w["name"], "code", w["code"], "")
            )
            continue
        if norm(w["name"]) != norm(t["wardShort"]):
            found.append(
                diff(
                    "new_unit",
                    w["province_code"],
                    w["code"],
                    w["name"],
                    "name",
                    w["name"],
                    t["wardShort"],
                    spelling(w["name"], t["wardShort"]),
                )
            )
        their_type = TYPES.get(t["wardType"], t["wardType"])
        if w["type"] != their_type:
            c = changed.get(w["code"])
            note = (
                f"{c['source_doc']}, {c['source_clause']}, from {c['effective']}"
                if c and c["old_type"] == their_type
                else ""
            )
            found.append(
                diff(
                    "new_unit",
                    w["province_code"],
                    w["code"],
                    w["name"],
                    "type",
                    w["type"],
                    their_type,
                    note,
                )
            )
        if w["province_code"] != t["provinceCode"]:
            found.append(
                diff(
                    "new_unit",
                    w["province_code"],
                    w["code"],
                    w["name"],
                    "province",
                    w["province_code"],
                    t["provinceCode"],
                )
            )
    ours = {w["code"] for w in wards}
    for code, t in sorted(by_code.items()):
        if code not in ours:
            found.append(
                diff("new_unit", t["provinceCode"], code, t["wardShort"], "code", "", code)
            )
    return found


def compare_old(crosswalk: list[Row], theirs: list[Row]) -> list[Row]:
    """theirs: rows of admin_units_legacy."""
    by_code = {r["wardCode"]: r for r in theirs if r["wardCode"]}
    ours: dict[str, Row] = {}
    names: dict[str, set[str]] = defaultdict(set)
    for r in crosswalk:
        if not r["old_ward_code"]:  # an area without a commune code (a coastal flat, Kim Sơn)
            continue
        ours.setdefault(r["old_ward_code"], r)
        names[r["old_ward_code"]].add(r["old_ward_name"])
    found = []
    for code, r in sorted(ours.items()):
        province, name = r["new_province_code"], " / ".join(sorted(names[code]))
        t = by_code.get(code)
        if t is None:
            found.append(diff("old_unit", province, code, name, "code", code, ""))
            continue
        if {norm(n, typed=True) for n in names[code]} != {norm(t["ward"], typed=True)}:
            note = spelling(name, t["ward"])
            found.append(diff("old_unit", province, code, name, "name", name, t["ward"], note))
        if district_key(r["old_district_name"]) != district_key(t["district"]):
            found.append(
                diff(
                    "old_unit",
                    province,
                    code,
                    name,
                    "district",
                    r["old_district_name"],
                    t["district"],
                    spelling(r["old_district_name"], t["district"]),
                )
            )
        if r["old_province_code"] != t["provinceCode"]:
            found.append(
                diff(
                    "old_unit",
                    province,
                    code,
                    name,
                    "province",
                    r["old_province_code"],
                    t["provinceCode"],
                )
            )
    for code, t in sorted(by_code.items()):
        if code not in ours:
            found.append(diff("old_unit", "", code, t["ward"], "code", "", code))
    return found


def their_mapping(
    converter: dict[str, dict[str, dict[str, list[object]]]],
    new: list[Row],
    legacy: list[Row],
) -> dict[str, set[str]]:
    """Old commune code -> new commune codes, from converter_2025.json and the two tables."""
    new_code = {(r["provinceKey"], r["wardKey"]): r["wardCode"] for r in new}
    old_code = {
        f"{r['provinceKey']}_{r['districtKey']}_{r['wardKey'] or ''}": r["wardCode"]
        for r in legacy
        if r["wardCode"]
    }
    mapping: dict[str, set[str]] = defaultdict(set)
    for province, wards in converter["DICT_PROVINCE_WARD_NO_DIVIDED"].items():
        for ward, olds in wards.items():
            for old in olds:
                if str(old) in old_code and (province, ward) in new_code:
                    mapping[old_code[str(old)]].add(new_code[(province, ward)])
    for province, divided in converter["DICT_PROVINCE_WARD_DIVIDED"].items():
        for old, options in divided.items():
            for option in options:
                ward = str(option["newWardKey"])  # type: ignore[index]
                if old in old_code and (province, ward) in new_code:
                    mapping[old_code[old]].add(new_code[(province, ward)])
    return mapping


def compare_mapping(
    crosswalk: list[Row], wards: list[Row], theirs: dict[str, set[str]]
) -> list[Row]:
    name = {w["code"]: w["name"] for w in wards}
    ours: dict[str, set[str]] = defaultdict(set)
    first: dict[str, Row] = {}
    corrected: set[str] = set()
    for r in crosswalk:
        if not r["old_ward_code"]:
            continue
        ours[r["old_ward_code"]].add(r["new_ward_code"])
        first.setdefault(r["old_ward_code"], r)
        if r["correction"]:
            corrected.add(r["old_ward_code"])

    def names(codes: set[str]) -> str:
        return "; ".join(f"{name.get(c, '')} ({c})" for c in sorted(codes))

    found = []
    for code in sorted(set(ours) | set(theirs)):
        if ours.get(code, set()) == theirs.get(code, set()):
            continue
        row = first.get(code)
        note = "crosswalk_corrections.csv" if code in corrected else ""
        found.append(
            diff(
                "mapping",
                row["new_province_code"] if row else "",
                code,
                row["old_ward_name"] if row else "",
                "new communes",
                names(ours.get(code, set())),
                names(theirs.get(code, set())),
                note,
            )
        )
    return found


def main() -> int:
    data = library_data()
    with sqlite3.connect(data / "dataset.db") as conn:
        conn.row_factory = sqlite3.Row
        new = [dict(r) for r in conn.execute("SELECT * FROM admin_units")]
        legacy = [dict(r) for r in conn.execute("SELECT * FROM admin_units_legacy")]
    converter = json.loads((data / "converter_2025.json").read_text(encoding="utf-8"))
    wards, crosswalk = read(WARDS), read(CROSSWALK)
    found = (
        compare_new(wards, new, read(CHANGES))
        + compare_old(crosswalk, legacy)
        + compare_mapping(crosswalk, wards, their_mapping(converter, new, legacy))
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with REPORT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(found)
    print(f"vietnamadminunits {version('vietnamadminunits')}")
    for check in ("new_unit", "old_unit", "mapping"):
        mine = [f for f in found if f["check"] == check]
        noted = sum(bool(f["note"]) for f in mine)
        print(f"{check:<9} {len(mine):>4} differences, {noted} with a note")
    print(f"-> {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
