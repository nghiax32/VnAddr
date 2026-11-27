"""Parse village rearrangement documents into raw old → new village rows.

Run with: uv run python -m pipeline.parse_villages

Input:  data/raw/villages/ninh-binh/state.json and the files it lists
Output: data/interim/parsed/villages-ninh-binh.csv
        data/reports/villages-ninh-binh.json   coverage per commune

Two kinds of document are read:

- resolutions of the commune People's Council (evidence "resolution"), e.g.
    "3. Thành lập thôn Hào Kiệt trên cơ sở nhập toàn bộ Đội 6 Nhì Giáp với Đội 7 Nhì Giáp và
     thôn Nhất Giáp."
    "13. Giữ nguyên thôn Đại Lại."
- plans submitted before the resolution (evidence "plan"; the names are proposals), e.g.
    "1.2. Sắp xếp, hợp nhất toàn bộ thôn Mới với thôn Pheo Tiền và thôn Cầu Uông, với tổng số
     hộ gia đình là 553 hộ; ... Tên gọi dự kiến: thôn Kim Thái"
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

import pdfplumber

from pipeline.extract import SCAN_THRESHOLD
from pipeline.parse_resolutions import PARSED_DIR, REPORTS_DIR

STATE = Path("data/raw/villages/ninh-binh/state.json")

# "t[ổôo] d[âa]n ph[ốôóo]" also accepts OCR misreadings of "tổ dân phố" ("tô dân phó").
VILLAGE_TYPES = r"thôn|xóm|làng|t[ổôo] d[âa]n ph[ốôóo]|TDP|khu phố|khu dân cư|khu|đội|tổ|ấp|bản"
TYPE_WORD = re.compile(rf"^(?P<type>{VILLAGE_TYPES})\s+(?P<name>.+)$", re.IGNORECASE)
# OCR sometimes drops the full stop or reads it as a comma ("1 Thành lập", "7, Thành lập").
CLAUSE = re.compile(
    r"^(?P<num>\d+(?:\.\d+)*)(?:[.,]\s+|\s+(?=Thành lập|Giữ nguyên|Đổi tên))(?P<text>.*)$"
)
FOUND = re.compile(
    rf"^Thành lập\s+(?P<new>(?:{VILLAGE_TYPES})\s+.+?)\s+trên cơ sở\s+"
    r"(?:nhập|sáp nhập|hợp nhất)\s+(?:toàn bộ|toàn)\s+(?P<old>.+?)\.?$",
    re.IGNORECASE,
)
KEEP = re.compile(rf"^Giữ nguyên\s+(?P<list>(?:{VILLAGE_TYPES})\s+.+?)\.?$", re.IGNORECASE)
RENAME = re.compile(
    rf"^Đổi tên\s+(?P<old>(?:{VILLAGE_TYPES})\s+.+?)\s+thành\s+"
    rf"(?P<new>(?:{VILLAGE_TYPES})\s+.+?)\.?$",
    re.IGNORECASE,
)
PLAN = re.compile(
    r"^Sắp xếp,?\s+(?:hợp nhất|sáp nhập|nhập)\s+(?:toàn bộ\s+)?(?P<old>.+?)"
    r"(?:,\s*với tổng số.*?)?\s*Tên gọi(?: dự kiến)?:\s*(?P<new>.+?)\.?$",
    re.IGNORECASE,
)
SPLIT_LIST = re.compile(r",\s*|\s+với\s+|\s+và\s+")


@dataclass
class Row:
    commune_code: str
    commune_name: str
    evidence: str  # "resolution" | "plan"
    document: str
    document_url: str
    adopted: str
    effective: str
    clause: str
    action: str  # "merged" | "unchanged" | "renamed"
    new_type: str
    new_name: str
    old_type: str
    old_name: str
    source_text: str


def unit(text: str, inherited: str = "") -> tuple[str, str]:
    text = text.strip(" .;,")
    match = TYPE_WORD.match(text)
    if not match:
        return inherited, text
    kind, name = match.group("type").lower(), match.group("name").strip()
    if re.fullmatch(r"t[ổôo] d[âa]n ph[ốôóo]|tdp", kind):
        kind = "tổ dân phố"
    doubled = TYPE_WORD.match(name)  # "thôn thôn Mỹ Côi": the type word is repeated
    if doubled and doubled.group("type").lower() == kind:
        name = doubled.group("name").strip()
    return kind, name


def first_sentence(text: str) -> str:
    """Text up to the first full stop followed by a capitalised word."""
    for match in re.finditer(r"\.\s+(\S)", text):
        if match.group(1).isupper():
            return text[: match.start()]
    return text


def plausible_name(name: str) -> bool:
    """Village names are short; longer pieces are sentences caught by a loose match
    ("với tổng số hộ gia đình là 605 hộ; Lý do không thực hiện ...")."""
    return 0 < len(name.split()) <= 6 and not re.search(r"[:;]|\bhộ\b|\blý do\b", name, re.I)


def units(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    current = ""
    for item in SPLIT_LIST.split(text):
        if not item.strip() or not plausible_name(unit(item)[1]):
            continue
        kind, name = unit(item, current)
        current = kind or current
        out.append((kind, name))
    return out


def ocr_pdf(path: Path) -> str:
    """OCR a scanned PDF page by page with Tesseract (vie), caching the text next to it."""
    cache = path.with_suffix(".ocr.txt")
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    texts = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdftoppm", "-r", "300", "-gray", "-png", str(path), f"{tmp}/p"], check=True
        )
        for image in sorted(Path(tmp).glob("p*.png")):
            result = subprocess.run(
                ["tesseract", str(image), "-", "-l", "vie", "--psm", "4"],
                capture_output=True,
                text=True,
                check=True,
            )
            texts.append(result.stdout)
    text = unicodedata.normalize("NFC", "\n".join(texts))
    cache.write_text(text, encoding="utf-8")
    return text


def read_text(path: Path, ocr: bool = True) -> tuple[str, bool]:
    """Text of a document and whether it came from OCR."""
    if path.suffix.lower() != ".pdf":
        return "", False
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    if sum(len(p.strip()) for p in pages) >= SCAN_THRESHOLD * len(pages):
        return unicodedata.normalize("NFC", "\n".join(pages)), False
    return (ocr_pdf(path), True) if ocr else ("", True)


def clauses(text: str) -> list[tuple[str, str]]:
    found: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.isdigit():  # page number
            continue
        match = CLAUSE.match(line)
        if match:
            found.append([match.group("num"), match.group("text")])
        elif found and line and not re.match(r"^(Điều \d+|[IVX]+\.|-|\+)", line):
            found[-1][1] += " " + line
        elif found and re.match(r"^(Điều \d+|[IVX]+\.)", line):
            found.append(["", ""])
    return [(n, re.sub(r"\s+", " ", t)) for n, t in found if n]


def plain(text: str) -> str:
    """Upper case without diacritics, so that OCR accent errors ("QUYÉT") still match."""
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").upper()


def kind_of(text: str) -> str:
    """A resolution has the title NGHỊ QUYẾT and its own "QUYẾT NGHỊ:" section; a plan or a
    notice that only cites a resolution ("Căn cứ Nghị quyết số ...") is not one."""
    head = plain(text[:1500])
    body = plain(text)
    titled = re.search(r"^\W*NGHI QUYET\W*$", head, re.MULTILINE) or re.search(
        r"/\s*NQ\s*-\s*HDND", head
    )
    if titled and ("HOI DONG NHAN DAN" in head or "HDND" in head) and "QUYET NGHI" in body:
        return "resolution"
    if any(word in head for word in ("PHUONG AN", "DE AN", "TO TRINH")):
        return "plan"
    return "other"


def dates(text: str) -> tuple[str, str]:
    adopted = re.search(r"thông qua ngày (\d{1,2}) tháng (\d{1,2}) năm (\d{4})", text)
    effective = re.search(
        r"hiệu lực(?: thi hành)?(?: kể)? từ ngày (\d{1,2}) tháng (\d{1,2}) năm (\d{4})", text
    )

    def iso(m: re.Match[str] | None) -> str:
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}" if m else ""

    return iso(adopted), iso(effective)


def article_1(text: str) -> str:
    """Text of Điều 1 (up to Điều 2), located on the text without diacritics so that OCR
    accent errors do not hide it. Plain text keeps the same length as the original."""
    flat = plain(text)
    start = re.search(r"DIEU\s*1\b", flat)
    if not start:
        return text
    end = re.search(r"DIEU\s*2\b", flat[start.end() :])
    return text[start.start() : start.end() + end.start() if end else len(text)]


def parse_document(text: str, base: dict[str, str]) -> tuple[list[Row], list[str]]:
    kind = kind_of(text)
    adopted, effective = dates(text)
    rows: list[Row] = []
    unread: list[str] = []
    body = article_1(text) if kind == "resolution" else text
    for number, clause in clauses(body):
        common = dict(base, evidence=kind, adopted=adopted, effective=effective, clause=number)
        source = f"{number}. {clause}"
        sentence = first_sentence(clause)
        if match := FOUND.match(sentence):
            new_type, new_name = unit(match.group("new"))
            for old_type, old_name in units(match.group("old")):
                rows.append(
                    Row(
                        **common,
                        action="merged",
                        new_type=new_type,
                        new_name=new_name,
                        old_type=old_type,
                        old_name=old_name,
                        source_text=source,
                    )
                )
        elif match := KEEP.match(sentence):
            for old_type, old_name in units(match.group("list")):
                rows.append(
                    Row(
                        **common,
                        action="unchanged",
                        new_type=old_type,
                        new_name=old_name,
                        old_type=old_type,
                        old_name=old_name,
                        source_text=source,
                    )
                )
        elif match := RENAME.match(sentence):
            new_type, new_name = unit(match.group("new"))
            old_type, old_name = unit(match.group("old"))
            rows.append(
                Row(
                    **common,
                    action="renamed",
                    new_type=new_type,
                    new_name=new_name,
                    old_type=old_type,
                    old_name=old_name,
                    source_text=source,
                )
            )
        elif kind == "plan" and (match := PLAN.match(clause)):
            new_type, new_name = unit(match.group("new"))
            for old_type, old_name in units(match.group("old")):
                rows.append(
                    Row(
                        **common,
                        action="merged",
                        new_type=new_type,
                        new_name=new_name,
                        old_type=old_type,
                        old_name=old_name,
                        source_text=source,
                    )
                )
        elif re.match(
            r"^(Thành lập|Sắp xếp,? (hợp nhất|sáp nhập|nhập)|Giữ nguyên|Đổi tên|Nhập|Sáp nhập)\s",
            clause,
        ):
            unread.append(source)
    return rows, unread


def main() -> int:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    rows: list[Row] = []
    report: dict[str, dict[str, object]] = {}
    for code, entry in sorted(state.items()):
        info: dict[str, object] = {
            "name": entry["name"],
            "platform": entry.get("platform"),
            "documents": len(entry.get("documents", [])),
            "files": 0,
            "scanned_files": 0,
            "best_evidence": "",
            "rows": 0,
            "unread_clauses": [],
        }
        for doc in entry.get("documents", []):
            for file in doc.get("files", []):
                info["files"] = int(info["files"]) + 1  # type: ignore[call-overload]
                text, from_ocr = read_text(Path(file["path"]))
                if from_ocr:
                    info["scanned_files"] = int(info["scanned_files"]) + 1  # type: ignore[call-overload]
                base = {
                    "commune_code": code,
                    "commune_name": entry["name"],
                    "document": doc["title"],
                    "document_url": file["url"],
                }
                found, unread = parse_document(text, base)
                if from_ocr:
                    for row in found:
                        row.evidence += "_ocr"
                rows += found
                info["rows"] = int(info["rows"]) + len(found)  # type: ignore[call-overload]
                info["unread_clauses"] += unread  # type: ignore[operator]
                for row in found:
                    if row.evidence.startswith("resolution") or not info["best_evidence"]:
                        info["best_evidence"] = row.evidence
        report[code] = info
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with (PARSED_DIR / "villages-ninh-binh.csv").open("w", encoding="utf-8", newline="") as h:
        writer = csv.DictWriter(h, fieldnames=list(Row.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)
    (REPORTS_DIR / "villages-ninh-binh.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    total = len(report)
    by = {
        k: sum(1 for r in report.values() if str(r["best_evidence"]).startswith(k))
        for k in ("resolution", "plan")
    }
    print(
        f"communes: {total}, with resolution: {by['resolution']}, plan only: {by['plan']}, "
        f"none: {total - by['resolution'] - by['plan']}, rows: {len(rows)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
