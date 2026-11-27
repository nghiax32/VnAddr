"""Turn the OCR'd appendix of Resolution 63/2021/NQ-HĐND (Nam Định) into village mapping rows.

Run with: uv run python -m pipeline.parse_village_tables

Input:  data/interim/ocr/nam-dinh-2021/appendix1.csv (pipeline.ocr_tables)
Output: data/interim/parsed/villages-nam-dinh-2021.csv
        data/reports/villages-nam-dinh-2021.json   counts per district against Điều 1

A row of column 3 reads "Sáp nhập thôn An Lễ với thôn Trung Nghĩa"; column 4 gives the new
village. Old villages are separated by "với", "và" and by commas between units of the same
type ("TDP 8, TDP 9"); a comma between different types qualifies a unit instead
("xóm Trung, thôn Đại Đê" is xóm Trung of thôn Đại Đê).
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

from pipeline.parse_resolutions import PARSED_DIR, REPORTS_DIR

OCR_CSV = Path("data/interim/ocr/nam-dinh-2021/appendix1.csv")
DOC = "63/2021/NQ-HĐND"
EFFECTIVE = "2021-12-12"
# Điều 1 of the resolution: (old units merged, new units) per district.
STATED = {
    "Mỹ Lộc": (76, 34),
    "Nam Định": (537, 156),  # 147 from merging + 9 from splitting 4 TDP
    "Vụ Bản": (98, 46),
    "Ý Yên": (228, 84),
    "Nam Trực": (288, 114),
    "Trực Ninh": (342, 142),
    "Nghĩa Hưng": (151, 60),
    "Xuân Trường": (236, 103),
    "Giao Thuỷ": (242, 106),
    "Hải Hậu": (284, 127),
}
TYPES = r"thôn|xóm|TDP|tổ dân phố|tổ|khu|làng|đội"
TYPE_AT_START = re.compile(rf"^({TYPES})\b", re.IGNORECASE)


@dataclass
class Row:
    district: str
    commune: str
    new_type: str
    new_name: str
    old_type: str
    old_name: str
    action: str
    evidence: str  # "ocr" | "ocr_low_confidence"
    confidence: float
    document: str
    effective: str
    page: int
    source_text: str


# Characters Tesseract confuses with digits in village numbers ("xóm I1", "TDP 1ó", "xóm l8").
DIGIT_LOOKALIKES = str.maketrans(
    {
        "I": "1",
        "l": "1",
        "Ì": "1",
        "Ï": "1",
        "]": "1",
        "|": "1",
        "!": "1",
        "ó": "6",
        "ố": "6",
        "§": "8",
        "Š": "5",
        "O": "0",
        "o": "0",
    }
)
NUMBER_LIKE = re.compile(r"^[0-9IlÌÏ\]|!óố§ŠOo]{1,3}$")


def fix_numbers(name: str) -> str:
    """Repair a village number misread as letters. Only the first token of the name (the
    number right after "xóm", "TDP"...) or a token that already contains a digit is changed,
    so Roman numerals inside names ("Thanh Thủy II") are kept."""
    tokens = name.split()
    for i, token in enumerate(tokens):
        if NUMBER_LIKE.match(token) and (i == 0 or any(ch.isdigit() for ch in token)):
            fixed = token.translate(DIGIT_LOOKALIKES)
            if fixed.isdigit():
                tokens[i] = fixed
    return " ".join(tokens)


def split_type(text: str) -> tuple[str, str]:
    text = re.sub(rf"^({TYPES})\.(?=\S)", r"\1 ", text.strip(), flags=re.IGNORECASE)  # "TDP.18"
    text = re.sub(r"(?<=\s)[\]|!](?=\s|$)", "1", text)  # "xóm ]" is "xóm 1"
    text = re.sub(r"[\[\]|:;\"'_`\u201c\u201d\u2018\u2019]+", " ", text)  # OCR debris
    text = re.sub(r"(?<=\d)\s+[lI](?=\s*$)", "", text)  # stray "l" after a number: "xóm 2 l"
    text = re.sub(r"\s+", " ", text).strip(" .,;")
    match = TYPE_AT_START.match(text)
    if not match:
        return "", text
    kind = match.group(1)
    kind = "TDP" if kind.upper() == "TDP" or kind.lower() == "tổ dân phố" else kind.lower()
    name = text[match.end() :].strip()
    if re.match(r"^số\s+", name):  # "TDP số 5"
        return kind, "số " + fix_numbers(name[3:].strip())
    return kind, fix_numbers(name)


# Part of a village rather than a whole one: "16 hộ gia đình thuộc xóm 1", "cụm dân cư xóm 3",
# "phần còn lại của TDP Lâm Thượng", "phía Tây Đơn vị 16".
PARTIAL = re.compile(
    r"\b(\d+|[IVXl]+)\s+hộ\b|cụm dân cư|phần còn lại|một phần|\bphía (Đông|Tây|Nam|Bắc)|dong gồm",
    re.IGNORECASE,
)


def old_units(text: str) -> list[tuple[str, str]]:
    # OCR may garble the first letter ("3áp nhập", "»áp nhập") or drop "nhập" ("Sáp xóm").
    text = re.sub(
        r"^\W*\S?[aáắ]p\s+(nh[aâậấ]p\s+)?|^(Sắp xếp|Nhập)\s+", "", text.strip(), flags=re.IGNORECASE
    )
    units: list[tuple[str, str]] = []
    for part in re.split(r"\s+với\s+|\s+và\s+", text):
        pieces = [p for p in re.split(r",\s*", part) if p.strip()]
        current = pieces[0]
        for piece in pieces[1:]:
            # "xóm Trung, thôn Đại Đê": a different type after the comma qualifies the unit.
            # "TDP 8, TDP 9" or "thôn Thượng Đồng, Phú Thọ": same or no type is a list.
            piece_type = split_type(piece)[0]
            if not piece_type or piece_type == split_type(current)[0]:
                units.append(split_type(current))
                current = piece
            else:
                current = f"{current}, {piece}"
        units.append(split_type(current))
    previous = ""
    out = []
    for kind, name in units:
        kind = kind or previous
        previous = kind
        out.append((kind, name))
    return out


CORRECTIONS = Path("data/audit/nam-dinh-2021-corrections.csv")
ADDITIONS = Path("data/audit/nam-dinh-2021-additions.csv")  # rows the table detection missed
SECOND_PASS = OCR_CSV.parent / "second_pass.csv"
SPLIT = re.compile(r"^(?:chia\s+)?tách\s+(?P<old>.+?)\s+thành\b", re.IGNORECASE)


def evidence_sources() -> tuple[dict[tuple[str, str], dict[str, str]], set[tuple[str, str]]]:
    """Rows read by eye (layer 3) and rows whose two OCR readings agree."""
    corrections: dict[tuple[str, str], dict[str, str]] = {}
    if CORRECTIONS.exists():
        with CORRECTIONS.open(encoding="utf-8") as handle:
            corrections = {(r["page"], r["y"]): r for r in csv.DictReader(handle)}
    agreed: set[tuple[str, str]] = set()
    if SECOND_PASS.exists():
        with SECOND_PASS.open(encoding="utf-8") as handle:
            agreed = {(r["page"], r["y"]) for r in csv.DictReader(handle) if r["agreed"] == "True"}
    return corrections, agreed


def main() -> int:
    rows = list(csv.DictReader(OCR_CSV.open(encoding="utf-8")))
    rows.sort(key=lambda r: (int(r["page"]), int(r["y"])))
    corrections, agreed = evidence_sources()
    district = ""
    out: list[Row] = []
    for r in rows:
        where = (r["page"], r["y"])
        confidence = float(r["confidence"])
        if where in corrections:
            fixed = corrections[where]
            if fixed["merged"] == "SKIP":
                continue  # a heading OCR'd as a row
            r = dict(r, merged=fixed["merged"], new_name=fixed["new_name"])
            evidence = "ocr_verified"
        elif confidence >= 80:
            evidence = "ocr"
        elif where in agreed:
            evidence = "ocr_agreed"
        else:
            evidence = "ocr_unverified"
        if r["merged"].startswith("("):
            # District header row: "III | Huyện Vụ Bản | (98) | (46)". OCR may garble
            # "Huyện" ("Huvên"), so the district is matched by name.
            best = process.extractOne(r["unit"], list(STATED), scorer=fuzz.partial_ratio)
            district = best[0] if best and best[1] >= 80 else r["unit"]
            continue
        new_type, new_name = split_type(r["new_name"])
        split = SPLIT.match(r["merged"])
        olds = [split_type(split.group("old"))] if split else old_units(r["merged"])
        for old_type, old_name in olds:
            partial = bool(PARTIAL.search(old_name))
            out.append(
                Row(
                    district=district,
                    commune=r["unit"],
                    new_type=new_type,
                    new_name=new_name,
                    old_type=old_type,
                    old_name=old_name,
                    action=("split" if split else "split_partial" if partial else "merged"),
                    evidence=evidence,
                    confidence=confidence,
                    document=DOC,
                    effective=EFFECTIVE,
                    page=int(r["page"]),
                    source_text=f"{r['merged']} → {r['new_name']}",
                )
            )
    if ADDITIONS.exists():
        with ADDITIONS.open(encoding="utf-8") as handle:
            for a in csv.DictReader(handle):
                split = SPLIT.match(a["merged"])
                old_type, old_name = split_type(split.group("old") if split else a["merged"])
                new_type, new_name = split_type(a["new_name"])
                out.append(
                    Row(
                        district=a["district"],
                        commune=a["commune"],
                        new_type=new_type,
                        new_name=new_name,
                        old_type=old_type,
                        old_name=old_name,
                        action="split" if split else "merged",
                        evidence="ocr_verified",
                        confidence=0.0,
                        document=DOC,
                        effective=EFFECTIVE,
                        page=int(a["page"]),
                        source_text=f"{a['merged']} → {a['new_name']}",
                    )
                )
    report: dict[str, dict[str, object]] = {}
    by_district: dict[str, list[Row]] = defaultdict(list)
    for row in out:
        by_district[row.district].append(row)
    for name, (old_stated, new_stated) in STATED.items():
        found = by_district.get(name, [])
        new_found = len({(r.commune, r.new_name, r.page, r.source_text) for r in found})
        report[name] = {
            "new_stated": new_stated,
            "new_read": new_found,
            "old_stated": old_stated,
            "old_read": sum(r.action == "merged" for r in found),
            "partial_read": sum(r.action == "split_partial" for r in found),
            "split_read": sum(r.action == "split" for r in found),
            "evidence": {
                e: sum(r.evidence == e for r in found)
                for e in ("ocr", "ocr_agreed", "ocr_verified", "ocr_unverified")
            },
        }
        whole = sum(r.action == "merged" for r in found)
        flag = "ok  " if new_found == new_stated and whole == old_stated else "DIFF"
        print(
            f"{flag} {name:<12} new {new_found:>4}/{new_stated:<4} "
            f"old {whole:>4}/{old_stated:<4} "
            f"partial {sum(r.action == 'split_partial' for r in found)} "
            f"split {sum(r.action == 'split' for r in found)}"
        )
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with (PARSED_DIR / "villages-nam-dinh-2021.csv").open("w", encoding="utf-8", newline="") as h:
        writer = csv.DictWriter(h, fieldnames=list(Row.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(r) for r in out)
    (REPORTS_DIR / "villages-nam-dinh-2021.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
