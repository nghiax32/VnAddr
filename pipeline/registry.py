"""Build the list of rearrangement resolutions from the Công báo scans (pipeline/sources.csv).

Run with: uv run python -m pipeline.registry

Inputs (written by walking congbao.chinhphu.vn/van-ban/x-<id>.htm and keeping the titles):
    data/interim/admin_unit_resolutions_2019_2021.csv   UBTVQH14: 2019-2021 round and the
                                                        other unit changes of that term
    data/interim/rearrangement_resolutions.csv          UBTVQH15: 2023-2025 and 2025 rounds
    data/interim/ubtvqh15_titles.csv                    every UBTVQH15 title (optional)

Output: pipeline/sources.csv, one row per resolution that changes administrative units of one
province: number, province, round, scope (folder under data/raw/) and Công báo page. General
resolutions (standards, programmes) are left out. pipeline.sources reads this file.
"""

from __future__ import annotations

import csv
import re
import sys
import unicodedata
from pathlib import Path

INTERIM = Path("data/interim")
OUTPUT = Path(__file__).parent / "sources.csv"
GAZETTE_PAGE = "https://congbao.chinhphu.vn/van-ban/x-{}.htm"

# A resolution that creates, merges, dissolves, renames or redraws units.
UNIT_CHANGE = re.compile(
    r"(thành lập|điều chỉnh địa giới|sắp xếp|nhập|giải thể|đổi tên)[^.]*"
    r"\b(xã|phường|thị trấn|thị xã|thành phố|huyện|quận|đơn vị hành chính)\b",
    re.IGNORECASE,
)
NOT_UNITS = re.compile(r"Đoàn|Hội đồng nhân dân|Ủy ban|quân hàm|Tòa án|Viện|phân loại đô thị")
PROVINCE = re.compile(
    r"(?:tỉnh|thành phố|Thành phố) "
    r"((?:Thừa Thiên |Bà Rịa - )?[A-ZĐÂ][^\s,.;]*(?: [A-ZĐ][^\s,.;]*){0,2})"
)
NUMBER = re.compile(r"số (\d+/(?:NQ-|\d{4}/)UBTVQH1[45])")


def slug(name: str) -> str:
    plain = unicodedata.normalize("NFD", name.replace("Đ", "D").replace("đ", "d"))
    plain = "".join(ch for ch in plain if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def province_of(title: str) -> str:
    found = PROVINCE.findall(title)
    return found[-1] if found else ""


def round_of(number: str, title: str) -> str:
    """'2020' (UBTVQH14 term, 2019-2021 round), '2024' (UBTVQH15 before 2025), '2025'."""
    if number.endswith("UBTVQH14"):
        return "2020"
    if "năm 2025" in title:
        return "2025"
    return "2024"


def read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    titles: dict[str, str] = {}
    for name in (
        "admin_unit_resolutions_2019_2021.csv",
        "rearrangement_resolutions.csv",
        "ubtvqh15_titles.csv",
    ):
        for r in read(INTERIM / name):
            titles[r["gazette_id"]] = unicodedata.normalize("NFC", r["title"])
    rows = []
    skipped = []
    for gazette_id, title in sorted(titles.items(), key=lambda item: int(item[0])):
        number = NUMBER.search(title)
        if not number or not UNIT_CHANGE.search(title) or NOT_UNITS.search(title):
            continue
        province = province_of(title)
        if not province:
            skipped.append(title)  # national resolutions (programmes, standards)
            continue
        doc_round = round_of(number[1], title)
        scope = slug(province) if doc_round == "2025" else f"{slug(province)}-{doc_round}"
        rows.append(
            {
                "doc_id": number[1],
                "round": doc_round,
                "province": province,
                "scope": scope,
                "gazette_page": GAZETTE_PAGE.format(gazette_id),
                "title": title,
            }
        )
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by_round: dict[str, set[str]] = {}
    for r in rows:
        by_round.setdefault(r["round"], set()).add(r["province"])
    for doc_round, provinces in sorted(by_round.items()):
        count = sum(r["round"] == doc_round for r in rows)
        print(f"round {doc_round}: {count} resolutions, {len(provinces)} provinces")
    for title in skipped:
        print(f"skip (no province): {title[:120]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
