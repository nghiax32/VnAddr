"""Parse the commune-level resolutions into raw mapping rows (names only, no codes yet).

Run with: uv run python -m pipeline.parse_resolutions

Input:  data/interim/text/<scope>/*.txt (from pipeline.extract)
Output: data/interim/parsed/<scope>.csv          one row per (old unit, new unit)
        data/reports/unparsed.csv                clauses the parser could not read
        data/reports/parse_summary.json          counts and consistency checks per resolution

A clause looks like:

    5. Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của Phường 1, Phường 2, Phường 3,
    Phường 5 và một phần diện tích tự nhiên, quy mô dân số của Phường 4 (Quận 3) thành
    phường mới có tên gọi là phường Bàn Cờ.

The old units are split into segments by three markers: "toàn bộ ..." (whole unit),
"một phần ..." (part of a unit that is split) and "phần còn lại của ..." (the rest of a unit
split by an earlier clause). The last two give mapping_type "split_partial".
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pipeline.extract import TEXT_DIR
from pipeline.fetch import MANIFEST

PARSED_DIR = Path("data/interim/parsed")
REPORTS_DIR = Path("data/reports")

PAGE_MARK = re.compile(r"\f\[page \d+\]\n")
DOC_ID = re.compile(r"Số:\s*(\d+/NQ-UBTVQH15)")
CLAUSE_START = re.compile(r"^(\d+)\.\s+(.*)$")

UNIT_TYPES = "phường|xã|thị trấn|đặc khu|huyện"
# The text has typing slips: a missing space ("Bình Tiếnthành xã", "tên gọilà") and, once, no
# "mới có tên gọi là" at all ("... thành xã Ninh Thạnh Lợi.").
NEW_UNIT = re.compile(
    rf"^(?P<verb>Sắp xếp|Nhập)\s+(?P<body>.+?)\s*thành\s+(?P<ntype>{UNIT_TYPES})\s+"
    rf"(?:(?:mới\s+)?có tên gọi\s*là\s+(?:(?P<ntype2>{UNIT_TYPES})\s+)?)?(?P<nname>.+?)\.?$"
)
RENAME = re.compile(
    rf"^Đổi tên\s+(?P<otype>{UNIT_TYPES})\s+(?P<oname>.+?)\s+thành\s+(?P<ntype>{UNIT_TYPES})\s+"
    r"(?P<nname>.+?)\.?$"
)
# "Điều chỉnh một phần diện tích tự nhiên của xã A để nhập vào xã B": a boundary change. A keeps
# its name with the rest of its area and counts as a commune formed by the resolution (the
# conversion table lists A -> A, part); the moved part is named again in the clause that
# rearranges B ("... được điều chỉnh theo quy định tại khoản 3 Điều này").
ADJUST = re.compile(
    rf"^Điều chỉnh một phần diện tích.*? của (?P<otype>{UNIT_TYPES})\s+(?P<oname>.+?)\s+"
    rf"để nhập vào (?:{UNIT_TYPES})\s+.+?\.?$"
)
# Wording varies between clauses: "quy mô dân của", "diện tích tự nhiên và quy mô dân số",
# "bộ diện tích" (no "toàn"), "toàn bộ xã A", a missing or doubled "của", "một phần diện tích
# tự nhiên, toàn bộ quy mô dân số của" (part of the area, all of the population: still a split).
MARKERS = re.compile(
    r"(?P<full>(?:toàn\s+)?bộ diện tích tự nhiên(?:,|\s+và)?\s*quy mô dân(?: số)?(?:\s+của)*"
    rf"|toàn bộ(?=\s+(?:các\s+)?(?:{UNIT_TYPES})\s))"
    r"|(?P<part>một phần diện tích(?: tự nhiên)?(?:,?\s*(?:toàn bộ\s+)?quy mô dân(?: số)?)?"
    r"(?:\s+của)*"
    # Area and population sent to different new units (xã Kỳ Lợi, Hà Tĩnh): "toàn bộ diện tích
    # tự nhiên của xã A" to one, "một phần quy mô dân số của xã A" to another.
    r"|toàn bộ diện tích tự nhiên(?:\s+của)+|một phần quy mô dân(?: số)?(?:\s+của)*)"
    r"|(?P<rest>phần(?: quy mô dân số)? còn lại(?:\s+của)*)"
)
# Words run together in the text: "phườngNgọc Sơn", "Phú Thịnhvà Song Phú", "vàcác xã".
GLUED = (
    (re.compile(rf"\b({UNIT_TYPES})(?=[A-ZĐ])"), r"\1 "),
    (re.compile(r"(?<=[a-zà-ỹđ])và(?=\s|các\b)"), " và"),
    (re.compile(r"\bvà(?=các\b)"), "và "),
)
AFTER_CLAUSE = re.compile(
    r"\s*(?:sau khi (?:thực hiện\s+)?sắp xếp|được điều chỉnh) theo quy định tại\s+"
    r"(?P<refs>(?:các\s+)?khoản \d+(?:\s*(?:,|và)\s*(?:khoản\s+)?\d+)*)"
    r"(?:\s+(?:của\s+)?Điều này)?"  # left out when another reference follows
)
ITEM = re.compile(
    rf"^(?:các\s+)?(?:(?P<type>{UNIT_TYPES}|Phường|Xã)\s+)?(?P<name>.+?)"
    r"(?:\s*\((?P<qual>[^)]+)\))?$"
)
AREA = re.compile(r"^(?:Trường bắn|[Kk]hu vực)\s")
SUMMARY_TOTAL = re.compile(r"có\s+(\d+)\s+đơn vị hành chính cấp xã")
SUMMARY_UNCHANGED = re.compile(r"không thực hiện sắp xếp là\s+(?P<list>.+?)\.?$")

TYPE_CODES = {
    "phường": "phuong",
    "xã": "xa",
    "thị trấn": "thi_tran",
    "đặc khu": "dac_khu",
    "huyện": "huyen",  # Côn Đảo district became a special zone
}
SHARE_TO_MAPPING = {"full": "merged_full", "part": "split_partial", "rest": "split_partial"}


@dataclass
class Row:
    doc_id: str
    clause: int
    new_type: str
    new_name: str
    old_type: str
    old_name: str
    old_qualifier: str
    qualifier_inferred: bool
    share: str  # "full" | "part" | "rest" | "unchanged"
    mapping_type: str
    rest_after_clauses: str
    source_text: str


@dataclass
class Summary:
    doc_id: str
    scope: str
    clauses: int = 0
    parsed: int = 0
    unparsed: int = 0
    stated_total: int | None = None
    unchanged: int = 0
    rows: int = 0
    checks: list[str] = field(default_factory=list)


def clauses_of(text: str) -> tuple[str, list[tuple[int, str]]]:
    text = PAGE_MARK.sub("", text)
    match = DOC_ID.search(text)
    doc_id = match.group(1) if match else "?"
    body = text.split("Điều 1.", 1)[1].split("Điều 2.", 1)[0]
    clauses: list[list[object]] = []
    for line in body.splitlines():
        start = CLAUSE_START.match(line)
        if start:
            clauses.append([int(start.group(1)), start.group(2).strip()])
        elif clauses:
            clauses[-1][1] = f"{clauses[-1][1]} {line.strip()}"
    return doc_id, [(int(n), re.sub(r"\s+", " ", str(s))) for n, s in clauses]  # type: ignore[call-overload]


LIST_BREAK = re.compile(rf"[()]|,\s*|\s+và\s+|(?<!các)\s+(?=(?:{UNIT_TYPES})\s+[A-ZĐ0-9])")


def split_items(segment: str) -> list[str]:
    """Split a list of units on commas and "và", but not inside parentheses ("(huyện Châu
    Thành, tỉnh Trà Vinh)"), and also where a type word starts a new unit with no separator
    ("thị trấn Nghèn xã Thiên Lộc")."""
    items, depth, start = [], 0, 0
    for match in LIST_BREAK.finditer(segment):
        token = match.group()
        if token in "()":
            depth += 1 if token == "(" else -1
        elif depth == 0:
            items.append(segment[start : match.start()])
            start = match.end()
    items.append(segment[start:])
    return [item.strip(" ,") for item in items if item.strip(" ,")]


def parse_items(segment: str) -> list[tuple[str, str, str]]:
    """Return (type, name, qualifier) for each unit named in a segment."""
    items: list[tuple[str, str, str]] = []
    current_type = ""
    for raw in split_items(segment):
        match = ITEM.match(raw.strip())
        if not match:
            raise ValueError(f"unreadable unit: {raw!r}")
        unit_type = (match.group("type") or "").lower()
        name = match.group("name").strip()
        # "phường Phường 4": the type word is repeated in the text.
        doubled = re.match(rf"^({UNIT_TYPES}|Phường)\s+(.+)$", name, flags=re.IGNORECASE)
        if unit_type and doubled:
            name = doubled.group(2)
        if unit_type:
            current_type = unit_type
        elif AREA.match(name):
            # An area that is not a commune ("Trường bắn TB1", "khu vực bãi bồi ven biển").
            items.append(("khu_vuc", name, match.group("qual") or ""))
            continue
        if not current_type:
            raise ValueError(f"unit without type: {raw!r}")
        items.append((current_type, name, match.group("qual") or ""))
    return items


def parse_clause(doc_id: str, number: int, text: str) -> list[Row]:
    for pattern, replacement in GLUED:
        text = pattern.sub(replacement, text)
    renamed = RENAME.match(text) or ADJUST.match(text)
    if renamed:
        adjusted = "ntype" not in renamed.re.groupindex
        old_type = TYPE_CODES[renamed.group("otype")]
        return [
            Row(
                doc_id=doc_id,
                clause=number,
                new_type=old_type if adjusted else TYPE_CODES[renamed.group("ntype")],
                new_name=renamed.group("oname" if adjusted else "nname").strip(),
                old_type=old_type,
                old_name=renamed.group("oname").strip(),
                old_qualifier="",
                qualifier_inferred=False,
                share="part" if adjusted else "renamed",
                mapping_type="split_partial" if adjusted else "renamed",
                rest_after_clauses="",
                source_text=f"{number}. {text}",
            )
        ]
    match = NEW_UNIT.match(text)
    if not match:
        raise ValueError("does not match 'Sắp xếp/Nhập ... thành <loại> mới có tên gọi là ...'")
    new_type = TYPE_CODES[match.group("ntype")]
    new_name = match.group("nname").strip()
    body = match.group("body")
    markers = list(MARKERS.finditer(body))
    if not markers or body[: markers[0].start()].strip():
        raise ValueError("old units are not introduced by 'toàn bộ / một phần / phần còn lại'")

    rows: list[Row] = []
    previous_share = ""
    for i, marker in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(body)
        segment = body[marker.end() : end].strip()
        segment = re.sub(r"(,|\s+và)$", "", segment).strip()
        share = str(marker.lastgroup)
        pieces = [(segment, share, "")]
        after = AFTER_CLAUSE.search(segment)
        if after:
            refs = ";".join(re.findall(r"\d+", after.group("refs")))
            # Units named after the reference ("... khoản 110 Điều này và xã Phong Quang")
            # belong to the list before this one, not to "phần còn lại".
            tail = segment[after.end() :].strip(" ,")
            tail = re.sub(r"^và\s+", "", tail)
            pieces = [(segment[: after.start()].strip(" ,"), share, refs)]
            if tail:
                pieces.append((tail, previous_share or share, ""))
        for piece, piece_share, refs in pieces:
            segment_rows = [
                Row(
                    doc_id=doc_id,
                    clause=number,
                    new_type=new_type,
                    new_name=new_name,
                    old_type=TYPE_CODES.get(unit_type, unit_type),
                    old_name=name,
                    old_qualifier=qual,
                    qualifier_inferred=False,
                    share=piece_share,
                    mapping_type=SHARE_TO_MAPPING[piece_share],
                    rest_after_clauses=refs,
                    source_text=f"{number}. {text}",
                )
                for unit_type, name, qual in parse_items(piece)
            ]
            rows += segment_rows
        previous_share = share
    infer_qualifiers(rows)
    return rows


def infer_qualifiers(rows: list[Row]) -> None:
    """Numbered wards ("Phường 4") only make sense with their district. A district written once
    after a list ("Phường 8 và Phường 9 (Quận 4)") is copied to the numbered wards before it
    that have none, and flagged as inferred so that validation checks it. Only a numbered ward
    passes its district on: in "Phường 9, phần còn lại của xã Hòa An (huyện Phú Hòa)" the
    district belongs to Hòa An alone."""
    pending: list[Row] = []
    for row in rows:
        if row.old_name.isdigit() and not row.old_qualifier:
            pending.append(row)
        elif row.old_qualifier and pending and row.old_name.isdigit():
            for earlier in pending:
                earlier.old_qualifier = row.old_qualifier
                earlier.qualifier_inferred = True
            pending = []


def parse_summary(doc_id: str, number: int, text: str, summary: Summary) -> list[Row]:
    total = SUMMARY_TOTAL.search(text)
    summary.stated_total = int(total.group(1)) if total else None
    unchanged = SUMMARY_UNCHANGED.search(text)
    if not unchanged:
        return []
    rows = []
    for unit_type, name, qual in parse_items(unchanged.group("list")):
        code = TYPE_CODES.get(unit_type, unit_type)
        rows.append(
            Row(
                doc_id,
                number,
                code,
                name,
                code,
                name,
                qual,
                False,
                "unchanged",
                "unchanged",
                "",
                f"{number}. {text}",
            )
        )
    return rows


def check(rows: list[Row], summary: Summary) -> None:
    formed = {(r.clause, r.new_name) for r in rows if r.share != "unchanged"}
    unchanged = [r for r in rows if r.share == "unchanged"]
    summary.unchanged = len(unchanged)
    if summary.stated_total is not None and len(formed) + len(unchanged) != summary.stated_total:
        summary.checks.append(
            f"FAIL total: {len(formed)} formed + {len(unchanged)} unchanged "
            f"!= {summary.stated_total} stated"
        )
    else:
        summary.checks.append(f"ok   total: {len(formed)} formed + {len(unchanged)} unchanged")

    def key(r: Row) -> tuple[str, str, str]:
        return (r.old_type, r.old_name, r.old_qualifier)

    by_unit: dict[tuple[str, str, str], list[Row]] = defaultdict(list)
    for r in rows:
        by_unit[key(r)].append(r)
    # A unit written once with its district and once without ("xã Bình Thạnh" and "xã Bình
    # Thạnh (huyện Thủ Thừa)") is the same unit when only one district is ever written.
    for unit in [u for u in by_unit if not u[2]]:
        named = [u for u in by_unit if u[:2] == unit[:2] and u[2]]
        if len(named) == 1:
            by_unit[named[0]] += by_unit.pop(unit)
    for unit, uses in sorted(by_unit.items()):
        shares = sorted(r.share for r in uses)
        label = " ".join(x for x in unit if x)
        if shares in (["full"], ["unchanged"], ["renamed"]):
            continue
        if set(shares) <= {"full", "unchanged", "renamed"}:
            # Two communes of the same name in different districts, written without the
            # district; the crosscheck with the conversion table tells them apart.
            summary.checks.append(f"warn {label}: same name in {len(shares)} clauses {shares}")
        elif {"full", "unchanged", "renamed"} & set(shares):
            summary.checks.append(f"FAIL {label}: whole unit also used elsewhere {shares}")
        elif len(uses) < 2:
            # A split unit goes to two or more new units ("một phần" several times, or
            # "một phần" and "phần còn lại").
            summary.checks.append(f"FAIL {label}: split unit used only once {shares}")
        for r in uses:
            if r.share == "rest":
                parts = {u.clause for u in uses if u.share == "part"}
                refs = {int(x) for x in r.rest_after_clauses.split(";") if x}
                if refs and not refs & parts and not refs & {u.clause for u in uses}:
                    summary.checks.append(
                        f"FAIL {label}: clause {r.clause} refers to khoản {sorted(refs)}, "
                        f"but the unit is split in khoản {sorted(parts)}"
                    )
    inferred = sum(r.qualifier_inferred for r in rows)
    summary.checks.append(f"info {inferred} district qualifiers inferred from a list")


def main() -> int:
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    unparsed: list[dict[str, object]] = []
    summaries: list[Summary] = []
    # Only the 2025 round; the earlier rounds are read by pipeline.parse_resolutions_2024.
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    scopes = {e["scope"] for e in manifest.values() if e["kind"] == "ward_resolution"}
    for path in sorted(p for p in TEXT_DIR.glob("*/*.txt") if p.parent.name in scopes):
        text = path.read_text(encoding="utf-8")
        doc_id, clauses = clauses_of(text)
        if doc_id == "?":
            continue
        summary = Summary(doc_id=doc_id, scope=path.parent.name, clauses=len(clauses))
        rows: list[Row] = []
        for number, clause in clauses:
            try:
                if clause.startswith("Sau khi sắp xếp"):
                    rows += parse_summary(doc_id, number, clause, summary)
                else:
                    rows += parse_clause(doc_id, number, clause)
                summary.parsed += 1
            except ValueError as exc:
                summary.unparsed += 1
                unparsed.append(
                    {"doc_id": doc_id, "clause": number, "error": str(exc), "text": clause}
                )
        summary.rows = len(rows)
        check(rows, summary)
        summaries.append(summary)
        out = PARSED_DIR / f"{path.parent.name}.csv"
        with out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0])))
            writer.writeheader()
            writer.writerows(asdict(r) for r in rows)
        print(
            f"{doc_id:<18} {summary.parsed}/{summary.clauses} clauses parsed, "
            f"{summary.rows} rows -> {out}"
        )
        for line in summary.checks:
            print(f"    {line}")

    with (REPORTS_DIR / "unparsed.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["doc_id", "clause", "error", "text"])
        writer.writeheader()
        writer.writerows(unparsed)
    (REPORTS_DIR / "parse_summary.json").write_text(
        json.dumps([asdict(s) for s in summaries], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 1 if unparsed else 0


if __name__ == "__main__":
    sys.exit(main())
