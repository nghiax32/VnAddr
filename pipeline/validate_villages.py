"""Cross-check the village mappings of different rounds against each other (layer 2).

Run with: uv run python -m pipeline.validate_villages

Inputs:  data/interim/parsed/villages-nam-dinh-2021.csv   2021 round, Resolution 63/2021 (OCR)
         data/interim/parsed/villages-ninh-binh.csv        2026 round, commune resolutions
         data/interim/parsed/ninh-binh.csv                 2025 commune mapping, NQ 1674
Outputs: data/reports/villages-validate.json               summary
         data/reports/villages-review.csv                  rows to read again against the image

Checks:
1. counts:      new villages per district match Điều 1 of Resolution 63/2021;
2. duplicates:  an old village is merged only once per round and commune;
3. chain:       a village created in 2021 should appear as an old village in the 2026
                resolution of the commune its old commune became (NQ 1674). A near miss
                ("Hoà Tiên" / "Hòa Tiên" is fine, "Hoà Tlên" is not) points at an OCR error.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from rapidfuzz import fuzz, process

from pipeline.parse_resolutions import PARSED_DIR, REPORTS_DIR

ROUND_2021 = PARSED_DIR / "villages-nam-dinh-2021.csv"
ROUND_2026 = PARSED_DIR / "villages-ninh-binh.csv"
# Old commune -> new commune at each point in time (pipeline.commune_history): built from the
# 2019-2021 and 2023-2025 resolutions and the official 2025 conversion table.
COMMUNE_LOOKUP = PARSED_DIR / "commune_lookup.csv"
OLD_PROVINCE = "36"  # Nam Định before 2025
# The 2021 village round (Resolution 63/2021) came after the 2019-2021 commune round, so its
# commune names are those standing in 2020.
VILLAGE_ROUND_AS_OF = "2020"
COUNTS_2021 = REPORTS_DIR / "villages-nam-dinh-2021.json"

# "Hoà"/"Hòa", "Thuỷ"/"Thủy": the two accent placements are the same name.
ACCENT_STYLE = {
    "oà": "òa",
    "oá": "óa",
    "oả": "ỏa",
    "oã": "õa",
    "oạ": "ọa",
    "oè": "òe",
    "oé": "óe",
    "oẻ": "ỏe",
    "oẽ": "õe",
    "oẹ": "ọe",
    "uỳ": "ùy",
    "uý": "úy",
    "uỷ": "ủy",
    "uỹ": "ũy",
    "uỵ": "ụy",
}


def key(name: str) -> str:
    text = unicodedata.normalize("NFC", name).lower()
    text = re.sub(r"^[\W_]+|[\W_]+$", "", text)  # OCR debris around the name ("_ Xã Liên Minh :")
    text = re.sub(r"^thị tr[ấầắa]n\s+", "thị trấn ", text)  # OCR: "Thị trần", "Thị trắn"
    for old, new in ACCENT_STYLE.items():
        text = text.replace(old, new)
    # Type words, including OCR variants ("tổ dân phó", "tô dân phố"), sometimes repeated.
    for _ in range(2):
        text = re.sub(
            r"^(thôn|xóm|tdp|t[ổôo] d[âa]n ph[ốôóo]|d[âa]n ph[ốôóo]|làng|khu|đội"
            r"|xã|phường|thị trấn|số)\s+",
            "",
            text,
        )
    return re.sub(r"\s+", " ", text)


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    rows21, rows26 = read(ROUND_2021), read(ROUND_2026)
    review: list[dict[str, object]] = []
    summary: dict[str, object] = {}

    # 1. counts (computed by parse_village_tables)
    counts = json.loads(COUNTS_2021.read_text(encoding="utf-8"))
    summary["counts_2021"] = {
        d: "ok" if c["new_read"] == c["new_stated"] else f"{c['new_read']}/{c['new_stated']}"
        for d, c in counts.items()
    }

    # 2. duplicates within a round
    seen: dict[tuple[str, str, str], int] = defaultdict(int)
    for r in rows21:
        seen[(r["district"], key(r["commune"]), key(r["old_name"]))] += 1
    duplicates = [k for k, n in seen.items() if n > 1]
    summary["duplicates_2021"] = len(duplicates)
    for district, commune, old in duplicates:
        review.append(
            {
                "round": 2021,
                "check": "duplicate",
                "district": district,
                "commune": commune,
                "name": old,
                "detail": "old village merged twice",
            }
        )

    # 3. chain 2021 -> 2026: the 2021 commune (with its district: "Xã Hồng Quang" exists in
    # both Ý Yên and Nam Trực) is followed to its 2025 commune through every later round.
    communes: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for c in read(COMMUNE_LOOKUP):
        if c["as_of"] == VILLAGE_ROUND_AS_OF and c["old_province_code"] == OLD_PROVINCE:
            communes[key(c["district"])][key(c["commune"])].add(key(c["new_ward_name"]))

    # Districts merged later (Mỹ Lộc into Nam Định city in 2024): going back from 2025 their
    # communes are known only under the district they merged into.
    merged_into: dict[str, str] = {}
    for path in sorted(PARSED_DIR.glob("*-2024.csv")):
        for r in read(path):
            if r["share"] == "district_merge":
                merged_into[key(re.sub(r"^(huyện|thành phố|thị xã)\s+", "", r["old_name"]))] = key(
                    r["new_name"]
                )

    def new_communes(district: str, commune: str) -> set[str]:
        """New communes a 2021 commune went to; the OCR'd name is matched fuzzily within its
        district (or the district it later merged into)."""
        within = dict(communes.get(merged_into.get(key(district), ""), {}))
        within.update(communes.get(key(district), {}))
        name = key(commune)
        if name in within:
            return within[name]
        best = process.extractOne(name, list(within), scorer=fuzz.ratio)
        return within[best[0]] if best and best[1] >= 85 else set()

    olds_2026: dict[str, set[str]] = defaultdict(set)
    for r in rows26:
        if r["evidence"].startswith("resolution"):
            olds_2026[key(r["commune_name"])].add(key(r["old_name"]))
    linked = near = missing = 0
    seen_new: set[tuple[str, str, str]] = set()
    for r in rows21:
        unique = (r["district"], key(r["commune"]), key(r["new_name"]))
        if unique in seen_new:
            continue  # one check per new village, not per old village merged into it
        seen_new.add(unique)
        targets = new_communes(r["district"], r["commune"])
        if not targets:
            review.append(
                {
                    "round": 2021,
                    "check": "commune_unknown",
                    "district": r["district"],
                    "commune": r["commune"],
                    "name": r["new_name"],
                    "detail": "old commune not found in the official conversion table",
                }
            )
        for target in targets:
            if target not in olds_2026:
                continue  # no 2026 resolution found for that commune yet
            name = key(r["new_name"])
            if name in olds_2026[target]:
                linked += 1
                continue
            best = process.extractOne(name, olds_2026[target], scorer=fuzz.ratio)
            # "Bái Thượng 1" / "Bái Thượng 2" are sibling villages, not an OCR error.
            numbered_sibling = bool(
                best and re.sub(r"\d+$", "", best[0]) == re.sub(r"\d+$", "", name)
            )
            if best and best[1] >= 80 and not numbered_sibling:
                near += 1
                detail = f"2026 resolution has '{best[0]}' ({best[1]:.0f}%)"
                check = "chain_near_miss"
            else:
                missing += 1
                detail = "not found among the old villages of the 2026 resolution"
                check = "chain_missing"
            review.append(
                {
                    "round": 2021,
                    "check": check,
                    "district": r["district"],
                    "commune": r["commune"],
                    "name": r["new_name"],
                    "detail": f"{detail}; page {r['page']}",
                }
            )
    summary["chain_2021_2026"] = {
        "linked": linked,
        "near_miss": near,
        "missing": missing,
        "communes_with_2026_resolution": len(olds_2026),
    }

    # rows to read again: low OCR confidence
    low = [r for r in rows21 if r["evidence"] == "ocr_low_confidence"]
    for r in low:
        review.append(
            {
                "round": 2021,
                "check": "low_confidence",
                "district": r["district"],
                "commune": r["commune"],
                "name": r["old_name"],
                "detail": f"{r['source_text']}; page {r['page']}; conf {r['confidence']}",
            }
        )
    summary["low_confidence_2021"] = len(low)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "villages-validate.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (REPORTS_DIR / "villages-review.csv").open("w", encoding="utf-8", newline="") as h:
        fields = ["round", "check", "district", "commune", "name", "detail"]
        writer = csv.DictWriter(h, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
