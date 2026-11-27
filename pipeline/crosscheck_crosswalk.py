"""Check the commune mapping parsed from the resolutions against the Statistics Office's
official conversion table (pipeline.build_crosswalk). Two independent official sources: the
resolution text and the conversion table should agree on every old -> new pair.

Run with: uv run python -m pipeline.crosscheck_crosswalk

Output: data/reports/crosscheck_crosswalk.csv  pairs found in only one source, or whose
        whole/part status differs
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata

from pipeline.parse_resolutions import PARSED_DIR, REPORTS_DIR
from pipeline.registry import slug

TYPE_WORDS = {
    "phuong": "phường",
    "xa": "xã",
    "thi_tran": "thị trấn",
    "dac_khu": "đặc khu",
    "huyen": "huyện",
}
ACCENT_STYLE = {
    "oà": "òa",
    "oá": "óa",
    "oả": "ỏa",
    "oã": "õa",
    "oạ": "ọa",
    "uỷ": "ủy",
    "uý": "úy",
    "uỳ": "ùy",
    "uỹ": "ũy",
    "uỵ": "ụy",
}


def norm(name: str, typed: bool = False) -> str:
    """typed: a name from the conversion table, which always starts with its type word."""
    text = unicodedata.normalize("NFC", name).lower().strip()
    for old, new in ACCENT_STYLE.items():
        text = text.replace(old, new)
    # Apostrophes: "Cư M\u2019gar" (resolution) / "Cư M'gar" (table), "N' Thôn Hạ".
    text = text.replace("\u2019", "'").replace("' ", "'")
    # Prefix typos in the conversion table: "Xa Ea Kly", "Thi trấn Ngan Dừa". Only there: "Xa
    # Dung" is also a commune name.
    types = (
        r"phường|xã|xa|thị trấn|thi trấn|đặc khu|huyện"
        if typed
        else r"phường|xã|thị trấn|đặc khu|huyện"
    )
    text = re.sub(rf"^({types})\s+", "", text)
    text = re.sub(r"^0+(\d)", r"\1", text)  # "Phường 01" -> "1"
    return re.sub(r"\s+", " ", text)


def district_key(name: str) -> str:
    return norm(re.sub(r"^(quận|huyện|thị xã|thành phố)\s+", "", name, flags=re.IGNORECASE))


def main() -> int:
    with (PARSED_DIR / "crosswalk.csv").open(encoding="utf-8") as handle:
        crosswalk = list(csv.DictReader(handle))
    problems: list[dict[str, str]] = []
    # Province code of each 2025 province, by the folder name of its resolution ("ninh-binh").
    provinces = {
        slug(re.sub(r"^(Tỉnh|Thành phố)\s+", "", r["new_province_name"])): r["new_province_code"]
        for r in crosswalk
    }
    totals = {"agree": 0, "differ": 0, "only_resolution": 0, "only_crosswalk": 0}
    for scope, province in sorted(provinces.items()):
        if not (PARSED_DIR / f"{scope}.csv").exists():
            print(f"{province}: no parsed resolution for {scope}")
            continue
        with (PARSED_DIR / f"{scope}.csv").open(encoding="utf-8") as handle:
            parsed = list(csv.DictReader(handle))
        official = [r for r in crosswalk if r["new_province_code"] == province]
        by_pair: dict[tuple[str, str], list[dict[str, str]]] = {}
        for r in official:
            by_pair.setdefault(
                (norm(r["new_ward_name"], typed=True), norm(r["old_ward_name"], typed=True)), []
            ).append(r)
        matched: set[int] = set()
        agree = differ = only_resolution = 0
        for p in parsed:
            pair = (norm(p["new_name"]), norm(p["old_name"]))
            candidates = by_pair.get(pair, [])
            if p["old_type"] == "huyen":
                # "huyện Côn Đảo thành đặc khu Côn Đảo": the table lists the district's
                # communes; a district without communes (Hoàng Sa, Bạch Long Vĩ) has no row.
                district = [
                    r
                    for r in official
                    if district_key(r["old_district_name"]) == norm(p["old_name"])
                    and norm(r["new_ward_name"], typed=True) == norm(p["new_name"])
                ]
                matched.update(id(r) for r in district)
                agree += 1
                if not district:
                    problems.append(
                        {
                            "province": province,
                            "issue": "district without communes",
                            "new": p["new_name"],
                            "old": f"huyện {p['old_name']}",
                            "resolution": p["mapping_type"],
                            "crosswalk": "",
                            "source": p["source_text"][:160],
                        }
                    )
                continue
            if p["old_qualifier"] and len(candidates) > 1:
                wanted = district_key(p["old_qualifier"])
                candidates = [
                    c for c in candidates if district_key(c["old_district_name"]) == wanted
                ] or candidates
            if not candidates:
                only_resolution += 1
                problems.append(
                    {
                        "province": province,
                        "issue": "only in resolution",
                        "new": p["new_name"],
                        "old": f"{p['old_name']} {p['old_qualifier']}",
                        "resolution": p["mapping_type"],
                        "crosswalk": "",
                        "source": p["source_text"][:160],
                    }
                )
                continue
            # Two old communes of the same name (different districts) each take their own row.
            c = next((c for c in candidates if id(c) not in matched), candidates[0])
            matched.add(id(c))
            resolution_share = {
                "merged_full": "full",
                "split_partial": "part",
                "unchanged": "unchanged",
                "renamed": "renamed",
            }[p["mapping_type"]]
            if resolution_share == c["share"] or (
                resolution_share in ("full", "renamed") and c["share"] in ("full", "renamed")
            ):
                agree += 1
            else:
                differ += 1
                problems.append(
                    {
                        "province": province,
                        "issue": "whole/part differs",
                        "new": p["new_name"],
                        "old": f"{p['old_name']} {p['old_qualifier']}",
                        "resolution": resolution_share,
                        "crosswalk": c["note"],
                        "source": p["source_text"][:160],
                    }
                )
        only_crosswalk = [r for r in official if id(r) not in matched]
        for r in only_crosswalk:
            problems.append(
                {
                    "province": province,
                    "issue": "only in crosswalk",
                    "new": r["new_ward_name"],
                    "old": f"{r['old_ward_name']} ({r['old_district_name']})",
                    "resolution": "",
                    "crosswalk": r["note"],
                    "source": "",
                }
            )
        totals["agree"] += agree
        totals["differ"] += differ
        totals["only_resolution"] += only_resolution
        totals["only_crosswalk"] += len(only_crosswalk)
        print(
            f"{province} {scope}: {len(parsed)} resolution rows, {len(official)} crosswalk rows; "
            f"agree {agree}, whole/part differs {differ}, only in resolution "
            f"{only_resolution}, only in crosswalk {len(only_crosswalk)}"
        )
    print(f"all: {totals}")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with (REPORTS_DIR / "crosscheck_crosswalk.csv").open("w", encoding="utf-8", newline="") as h:
        fields = ["province", "issue", "new", "old", "resolution", "crosswalk", "source"]
        writer = csv.DictWriter(h, fieldnames=fields)
        writer.writeheader()
        writer.writerows(problems)
    return 0


if __name__ == "__main__":
    sys.exit(main())
