"""Follow every commune from 2019 to the 2025 system, through each rearrangement round.

Run with: uv run python -m pipeline.commune_history

Rounds, oldest first (pilot: the three old provinces that now form Ninh Bình):
    2019-2021  data/interim/parsed/<province>-2020.csv   (NQ .../NQ-UBTVQH14)
    2023-2025  data/interim/parsed/<province>-2024.csv   (NQ .../NQ-UBTVQH15)
    1 Jul 2025 data/interim/parsed/crosswalk.csv         (Statistics Office conversion table)

Output: data/interim/parsed/commune_history.csv, one row per (commune as of 2019, final
commune): the old province, district and commune, every step with its document, clause and
date, the new 2025 commune with its code, and whether any step moved only part of the commune.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict

from pipeline.parse_resolutions import PARSED_DIR
from pipeline.parse_resolutions_2024 import (
    ALIASES,
    DISTRICT_TYPE,
    OLD_NAMES,
    accepted,
    district_of,
    plain_key,
    same_name,
    spelling,
    stages,
    state_before_2024,
    table_key,
    undo,
    unit_key,
)
from pipeline.parse_resolutions_2024 import Row as RoundRow
from pipeline.registry import slug

OUTPUT = PARSED_DIR / "commune_history.csv"
# (as of, province, district, commune) -> new commune, for names as they stood at each point:
# "2019" (before the 2019-2021 round), "2020" (after it), "2024" (after the 2023-2025 round).
LOOKUP = PARSED_DIR / "commune_lookup.csv"


def district_key(name: str) -> str:
    """A district with its type, normalised: huyện Hồng Ngự and thành phố Hồng Ngự are two."""
    name = name.replace(" (phần còn lại)", "")  # "huyện Trà Lĩnh (phần còn lại)"
    name = re.sub(r",\s*tỉnh .*$", "", name)  # "huyện Yên Định, tỉnh Thanh Hóa"
    return plain_key(name).strip()


def split_district(key: str) -> tuple[str, str]:
    """(type, name) of a district_key(): "thị xã kinh môn" -> ("thị xã", "kinh môn")."""
    m = DISTRICT_TYPE.match(key)
    return (m[1], m[2]) if m else ("", key)


def split_key(key: str) -> tuple[str, str]:
    """(type, name) of a unit_key(): "thi_tran đầm hà" -> ("thi_tran", "đầm hà")."""
    unit_type, _, name = key.partition(" ")
    return unit_type, name


def read_round(path: str) -> list[RoundRow]:
    """Rows of one round; a province with no resolution in that round has none."""
    if not (PARSED_DIR / path).exists():
        return []
    with (PARSED_DIR / path).open(encoding="utf-8") as handle:
        return [RoundRow(**r) for r in csv.DictReader(handle)]  # type: ignore[arg-type]


Step = dict[str, str]


def apply(rows: list[RoundRow], district: str, commune: str) -> list[tuple[str, str, Step]]:
    """Where (district, commune) goes in one round: [(district, commune, step)]; unchanged
    communes keep their name and only follow a district merge."""
    districts = {
        district_key(f"{r.old_type} {r.old_name}"): district_key(f"{r.new_type} {r.new_name}")
        for r in rows
        if r.share == "district_merge"
    }
    new_district = districts.get(district, district)
    out = []
    matched = []
    for r in rows:
        if r.share == "district_merge" or unit_key(r.old_type, r.old_name) != commune:
            continue
        if district_of(r) and district_key(district_of(r)) not in (district, new_district):
            continue
        step = {
            "doc": r.doc_id,
            "clause": r.clause,
            "effective": r.effective,
            "to": f"{r.new_type} {r.new_name}",
            "share": r.share,
        }
        # A district merged later in the same round (Cao Bằng: communes of huyện Phục Hòa
        # rearranged in February 2020, the district merged into Quảng Hòa in March).
        target = district_key(r.district) or new_district
        matched.append(r)
        out.append((districts.get(target, target), unit_key(r.new_type, r.new_name), step))
    if out and all(s["share"] == "part" and c != commune for _, c, s in out):
        # Only part of it was moved ("Điều chỉnh 9,80 km2 diện tích tự nhiên của xã Hương Minh
        # vào xã Hương Quang"): the rest may go on under its own name. The branch only counts
        # if a later round or the 2025 table still has the commune.
        out.append(
            (
                new_district,
                commune,
                {
                    **out[0][2],
                    "to": f"{matched[0].old_type} {matched[0].old_name}",
                    "share": "part",
                },
            )
        )
    return out or [(new_district, commune, {})]


def main() -> int:
    with (PARSED_DIR / "crosswalk.csv").open(encoding="utf-8") as handle:
        crosswalk = list(csv.DictReader(handle))
    # An alias would also rename a unit the table itself spells that way.
    clashes = {
        c[column]
        for c in crosswalk
        for column, kind in (("old_ward_name", "commune"), ("old_district_name", "district"))
        if re.sub(r"^\S+(?: (?:trấn|xã|phố))? ", "", spelling(c[column])) in ALIASES[kind]
    }
    for name in sorted(clashes):
        print(f"warning: name_aliases.csv renames {name!r}, which the table also has")
    reviewed = accepted()
    out: list[dict[str, str]] = []
    lookup: set[tuple[str, ...]] = set()
    report: dict[str, object] = {}
    # Every old province, by the folder name its resolutions are kept under ("nam-dinh");
    # the 2019-2021 titles name Thừa Thiên Huế by its old name.
    provinces = {
        c["old_province_code"]: slug(re.sub(r"^(Tỉnh|Thành phố)\s+", "", c["old_province_name"]))
        for c in crosswalk
    }
    folder_2020 = {v: k for k, v in OLD_NAMES.items()}
    for code, name in sorted(provinces.items()):
        r2020 = read_round(f"{folder_2020.get(name, name)}-2020.csv")
        r2024 = read_round(f"{name}-2024.csv")
        before_2024 = state_before_2024(crosswalk, code, r2024)
        before_2020 = undo(before_2024, r2020)  # as state_before_2024 undoes 2023-2025
        table: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for c in crosswalk:
            if c["old_province_code"] == code:
                table[(district_key(c["old_district_name"]), table_key(c["old_ward_name"]))].append(
                    c
                )
        unresolved = []
        for district_full, commune in sorted(before_2020):
            start = district_key(district_full)
            paths: list[tuple[str, str, list[Step], list[tuple[str, str, str]]]] = [
                (start, commune, [], [("2019", start, commune)])
            ]
            for as_of, rows in (("2020", r2020), ("2024", r2024)):
                for stage in stages(rows):  # documents of one round, by effective date
                    # A commune moved or renamed may be changed again by the same stage
                    # (xã Đại Bản to quận Hồng Bàng, then phường Đại Bản): follow it, a few
                    # steps at most.
                    todo, paths = paths, []
                    for _ in range(3):
                        moved = []
                        for d, c, steps, seen in todo:
                            for d2, c2, s in apply(stage, d, c):
                                path = (
                                    d2,
                                    c2,
                                    steps + ([{**s, "round": as_of}] if s else []),
                                    seen,
                                )
                                again = s.get("share") in ("moved", "renamed")
                                (moved if again else paths).append(path)
                        todo = moved
                    paths += todo
                paths = [(d, c, steps, [*seen, (as_of, d, c)]) for d, c, steps, seen in paths]
            found = False
            for d, c, steps, seen in paths:
                if not d:  # no district in the text: the commune, if its name is unique here
                    named = {k for k in table if k[1] == c}
                    d = next(iter(named))[0] if len(named) == 1 else d
                if (d, c) not in table:  # another type in the table (see undo), alone there
                    typed = [k for k in table if k[0] == d and same_name(k[1], c)]
                    c = typed[0][1] if len(typed) == 1 else c
                for t in table.get((d, c), []):
                    found = True
                    for as_of, d_k, c_k in seen:
                        # Partial if any later step, or the 2025 table, moved only part of it.
                        later = [s for s in steps if s["round"] > as_of]
                        partial = t["share"] == "part" or any(s["share"] == "part" for s in later)
                        lookup.add(
                            (
                                as_of,
                                code,
                                *reversed(split_district(d_k)),
                                *split_key(c_k),
                                t["new_ward_code"],
                                t["new_ward_name"],
                                str(partial),
                            )
                        )
                    final = {
                        "doc": "Bảng chuyển đổi ĐVHC mới - cũ (Cục Thống kê)",
                        "clause": "",
                        "effective": "2025-07-01",
                        "to": t["new_ward_name"],
                        "share": t["share"],
                    }
                    all_steps = [*steps, final]
                    out.append(
                        {
                            "old_province_code": code,
                            "old_district": district_full,
                            "old_commune_type": split_key(commune)[0],
                            "old_commune": split_key(commune)[1],
                            "new_ward_code": t["new_ward_code"],
                            "new_ward_name": t["new_ward_name"],
                            "partial": str(any(s["share"] == "part" for s in all_steps)),
                            "steps": json.dumps(all_steps, ensure_ascii=False),
                        }
                    )
            if not found:
                unresolved.append(f"{district_full} | {commune}")
        report[name] = {"communes_2019": len(before_2020), "unresolved": unresolved}
        # Communes left unfollowed for a reviewed reason ("not_followed", 0 expected).
        reason = reviewed.get((name, "not_followed", len(unresolved), 0)) if unresolved else None
        if reason:
            report[name]["accepted"] = reason  # type: ignore[index]
        print(
            f"{name}: {len(before_2020)} communes as of 2019, {len(unresolved)} not followed "
            f"to 2025{' (accepted)' if reason else ''}"
        )
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    with LOOKUP.open("w", encoding="utf-8", newline="") as handle:
        plain = csv.writer(handle)
        plain.writerow(
            [
                "as_of",
                "old_province_code",
                "district",
                "district_type",
                "commune_type",
                "commune",
                "new_ward_code",
                "new_ward_name",
                "partial",
            ]
        )
        plain.writerows(sorted(lookup))
    print(
        json.dumps(
            {k: v["unresolved"][:10] for k, v in report.items()},  # type: ignore[index]
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
