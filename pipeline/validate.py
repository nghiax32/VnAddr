"""Check the commune tables against each other and write the coverage report.

Run with: uv run python -m pipeline.validate

Inputs:  data/interim/parsed/province_new.csv, ward_new.csv     pipeline.build_entities
         data/interim/parsed/crosswalk.csv                      pipeline.build_crosswalk
         data/interim/parsed/commune_history.csv                pipeline.commune_history
         data/interim/parsed/villages-nam-dinh-2021.csv,
         villages-ninh-binh.csv                                 the village rounds
         data/reports/parse_summary.json                        pipeline.parse_resolutions
         data/reports/crosscheck_crosswalk.csv                  pipeline.crosscheck_crosswalk
         pipeline/sources.csv, pipeline/accepted_discrepancies.csv
Output:  data/reports/coverage.md

Checks:
1. units:        34 provinces and 3,321 communes, codes of 2 and 5 digits, no code listed twice,
                 every commune in a listed province;
2. totals:       the communes of each province match the total its 2025 resolution states;
3. new communes: every new commune of the crosswalk is in ward_new, in the same province, and
                 every commune of ward_new is reached by the crosswalk;
4. old communes: each old commune code of the crosswalk names one commune, which is moved whole
                 in one row or split over two rows or more;
5. history:      every row of commune_history ends at a commune of ward_new.

A problem is "recorded" when crosscheck_crosswalk.csv lists the same new commune (it is then
waiting for review there) and "open" otherwise. The exit code is 1 when a problem is open.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pipeline.crosscheck_crosswalk import norm
from pipeline.parse_resolutions import PARSED_DIR, REPORTS_DIR

PROVINCES = PARSED_DIR / "province_new.csv"
WARDS = PARSED_DIR / "ward_new.csv"
CROSSWALK = PARSED_DIR / "crosswalk.csv"
HISTORY = PARSED_DIR / "commune_history.csv"
VILLAGES_2021 = PARSED_DIR / "villages-nam-dinh-2021.csv"
VILLAGES_2026 = PARSED_DIR / "villages-ninh-binh.csv"
VILLAGES_PROVINCE = "37"  # Ninh Bình, which took in Nam Định in 2025
PARSE_SUMMARY = REPORTS_DIR / "parse_summary.json"
CROSSCHECK = REPORTS_DIR / "crosscheck_crosswalk.csv"
SOURCES = Path(__file__).parent / "sources.csv"
ACCEPTED = Path(__file__).parent / "accepted_discrepancies.csv"
REPORT = REPORTS_DIR / "coverage.md"

PROVINCE_COUNT = 34
WARD_COUNT = 3321
PROVINCE_TYPES = {"tinh", "thanh_pho"}
WARD_TYPES = {"phuong", "xa", "dac_khu"}
WHOLE = {"full", "unchanged", "renamed"}  # crosswalk shares that move the whole old commune

Row = dict[str, str]
Problem = dict[str, str]


def read(path: Path) -> list[Row]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def problem(check: str, province: str, item: str, detail: str) -> Problem:
    return {"check": check, "province": province, "item": item, "detail": detail, "status": ""}


def check_units(provinces: list[Row], wards: list[Row]) -> list[Problem]:
    found = []
    if len(provinces) != PROVINCE_COUNT:
        found.append(problem("units", "", "provinces", f"{len(provinces)}, not {PROVINCE_COUNT}"))
    if len(wards) != WARD_COUNT:
        found.append(problem("units", "", "communes", f"{len(wards)}, not {WARD_COUNT}"))
    codes = {p["code"] for p in provinces}
    for p in provinces:
        if not re.fullmatch(r"\d{2}", p["code"]) or p["type"] not in PROVINCE_TYPES:
            found.append(problem("units", p["code"], p["name"], f"code or type {p['type']!r}"))
    for code, n in Counter(p["code"] for p in provinces).items():
        if n > 1:
            found.append(problem("units", code, "province code", f"listed {n} times"))
    for code, n in Counter(w["code"] for w in wards).items():
        if n > 1:
            found.append(problem("units", "", code, f"commune code listed {n} times"))
    for w in wards:
        if not re.fullmatch(r"\d{5}", w["code"]) or w["type"] not in WARD_TYPES:
            found.append(problem("units", w["province_code"], w["code"], f"type {w['type']!r}"))
        if w["province_code"] not in codes:
            found.append(problem("units", w["province_code"], w["code"], "province not listed"))
    return found


def check_totals(wards: list[Row], stated: dict[str, int]) -> list[Problem]:
    """stated: province code -> commune total of its 2025 resolution."""
    counts = Counter(w["province_code"] for w in wards)
    found = []
    for code in sorted(set(counts) | set(stated)):
        if counts.get(code) != stated.get(code):
            detail = f"{counts.get(code, 0)} communes, resolution states {stated.get(code)}"
            found.append(problem("totals", code, "communes", detail))
    return found


def check_new_communes(wards: list[Row], crosswalk: list[Row]) -> list[Problem]:
    province_of = {w["code"]: w["province_code"] for w in wards}
    found = []
    seen = set()
    for r in crosswalk:
        code = r["new_ward_code"]
        if code in seen:
            continue
        seen.add(code)
        if code not in province_of:
            found.append(
                problem(
                    "new communes",
                    r["new_province_code"],
                    r["new_ward_name"],
                    f"{code} is not in ward_new",
                )
            )
        elif province_of[code] != r["new_province_code"]:
            found.append(
                problem(
                    "new communes",
                    r["new_province_code"],
                    r["new_ward_name"],
                    f"{code} is in province {province_of[code]} in ward_new",
                )
            )
    for w in wards:
        if w["code"] not in seen:
            found.append(
                problem(
                    "new communes",
                    w["province_code"],
                    w["name"],
                    f"{w['code']} has no row in the crosswalk",
                )
            )
    return found


def check_old_communes(crosswalk: list[Row]) -> list[Problem]:
    rows: dict[str, list[Row]] = defaultdict(list)
    for r in crosswalk:
        rows[r["old_ward_code"]].append(r)
    found = []
    for code, group in sorted(rows.items()):
        names = sorted({r["old_ward_name"] for r in group})
        province = group[0]["new_province_code"]
        into = "; ".join(f"{r['new_ward_name']} ({r['share']})" for r in group)
        if len(names) > 1:
            found.append(
                problem(
                    "old communes",
                    province,
                    f"{code} {' / '.join(names)}",
                    f"one code for {len(names)} communes: {into}",
                )
            )
        elif any(r["share"] in WHOLE for r in group) and len(group) > 1:
            found.append(
                problem(
                    "old communes",
                    province,
                    f"{code} {names[0]}",
                    f"moved whole and also elsewhere: {into}",
                )
            )
        elif not any(r["share"] in WHOLE for r in group) and len(group) < 2:
            found.append(
                problem(
                    "old communes",
                    province,
                    f"{code} {names[0]}",
                    f"split, but only one part is listed: {into}",
                )
            )
    return found


def check_history(wards: list[Row], history: list[Row]) -> list[Problem]:
    codes = {w["code"] for w in wards}
    return [
        problem(
            "history",
            r["old_province_code"],
            f"{r['old_district']}, {r['old_commune']}",
            f"ends at {r['new_ward_code']}, not in ward_new",
        )
        for r in history
        if r["new_ward_code"] not in codes
    ]


def mark(found: list[Problem], crosswalk: list[Row], crosscheck: list[Row]) -> None:
    """Mark the problems crosscheck_crosswalk.csv already lists for review."""
    listed = {(r["province"], norm(r["new"])) for r in crosscheck}
    into: dict[str, set[str]] = defaultdict(set)
    for r in crosswalk:
        into[r["old_ward_code"]].add(norm(r["new_ward_name"], typed=True))
    for p in found:
        code = p["item"].split(" ")[0]
        names = into.get(code, set()) | {norm(p["item"])}
        recorded = any((p["province"], n) in listed for n in names)
        p["status"] = "recorded" if recorded else "open"


def stated_totals() -> dict[str, int]:
    """Province code -> the commune total stated by its 2025 resolution."""
    provinces = {p["name"]: p["code"] for p in read(PROVINCES)}
    scopes = {r["scope"]: r["province"] for r in read(SOURCES) if r["round"] == "2025"}
    summary = json.loads(PARSE_SUMMARY.read_text(encoding="utf-8"))
    return {
        provinces[scopes[s["scope"]]]: s["stated_total"]
        for s in summary
        if s["scope"] in scopes and scopes[s["scope"]] in provinces
    }


def villages() -> dict[str, str]:
    """Province code -> the village data held for it."""
    held = []
    if VILLAGES_2021.exists():
        rows = read(VILLAGES_2021)
        districts = len({r["district"] for r in rows})
        communes = len({(r["district"], r["commune"]) for r in rows})
        held.append(f"2021 round (Nam Định): {communes} old communes of {districts} districts")
    if VILLAGES_2026.exists():
        rows = read(VILLAGES_2026)
        resolved = {r["commune_code"] for r in rows if r["evidence"].startswith("resolution")}
        other = {r["commune_code"] for r in rows} - resolved
        held.append(
            f"2026 round: {len(resolved)} communes with a resolution, {len(other)} more with "
            "a plan or another document only"
        )
    return {VILLAGES_PROVINCE: "; ".join(held)} if held else {}


def report(
    provinces: list[Row],
    wards: list[Row],
    crosswalk: list[Row],
    history: list[Row],
    stated: dict[str, int],
    found: list[Problem],
    accepted: list[Row],
    village: dict[str, str],
) -> str:
    checks = ["units", "totals", "new communes", "old communes", "history"]
    lines = [
        "# Coverage",
        "",
        "Written by `pipeline.validate` from the tables in `data/interim/parsed/`.",
        "",
        "## Checks",
        "",
        "| Check | Problems | Recorded for review | Open |",
        "|---|---:|---:|---:|",
    ]
    for c in checks:
        mine = [p for p in found if p["check"] == c]
        recorded = sum(p["status"] == "recorded" for p in mine)
        lines.append(f"| {c} | {len(mine)} | {recorded} | {len(mine) - recorded} |")
    lines += ["", "## Problems", ""]
    if found:
        lines += ["| Check | Province | Item | Detail | Status |", "|---|---|---|---|---|"]
        lines += [
            f"| {p['check']} | {p['province']} | {p['item']} | {p['detail']} | {p['status']} |"
            for p in found
        ]
    else:
        lines.append("None.")
    lines += [
        "",
        "## Accepted discrepancies",
        "",
        "Reviewed in `pipeline/accepted_discrepancies.csv`.",
        "",
        "| Scope | Check | Computed | Stated | Reason |",
        "|---|---|---:|---:|---|",
    ]
    lines += [
        f"| {r['scope']} | {r['check']} | {r['computed']} | {r['stated']} | {r['reason']} |"
        for r in accepted
    ]
    reached = Counter(
        w["province_code"] for w in wards if w["code"] in {r["new_ward_code"] for r in crosswalk}
    )
    old: dict[str, set[str]] = defaultdict(set)
    for r in crosswalk:
        old[r["new_province_code"]].add(r["old_ward_code"])
    province_of = {w["code"]: w["province_code"] for w in wards}
    followed: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for r in history:
        followed[province_of.get(r["new_ward_code"], "")].add(
            (r["old_province_code"], r["old_district"], r["old_commune"])
        )
    counts = Counter(w["province_code"] for w in wards)
    lines += [
        "",
        "## By province",
        "",
        "Communes: in `ward_new.csv`, and as stated by the 2025 resolution. Reached: communes with "
        "a row in the crosswalk. Old communes: codes of the crosswalk moved into the province. "
        "Communes of 2019: rows of `commune_history.csv` ending in the province.",
        "",
        "| Code | Province | Communes | Stated | Reached | Old communes | Communes of 2019 "
        "| Villages |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for p in provinces:
        c = p["code"]
        lines.append(
            f"| {c} | {p['name']} | {counts[c]} | {stated.get(c, '')} | {reached[c]} "
            f"| {len(old[c])} | {len(followed[c])} | {village.get(c, 'none')} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    provinces, wards, crosswalk = read(PROVINCES), read(WARDS), read(CROSSWALK)
    history = read(HISTORY)
    stated = stated_totals()
    found = (
        check_units(provinces, wards)
        + check_totals(wards, stated)
        + check_new_communes(wards, crosswalk)
        + check_old_communes(crosswalk)
        + check_history(wards, history)
    )
    mark(found, crosswalk, read(CROSSCHECK))
    text = report(provinces, wards, crosswalk, history, stated, found, read(ACCEPTED), villages())
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(text, encoding="utf-8")
    for p in found:
        print(f"{p['status']:<8} {p['check']:<12} {p['province']:<3} {p['item']}: {p['detail']}")
    open_ = sum(p["status"] == "open" for p in found)
    print(f"{len(found)} problems, {open_} open -> {REPORT}")
    return 1 if open_ else 0


if __name__ == "__main__":
    sys.exit(main())
