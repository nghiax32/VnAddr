"""List the documents of vanban.chinhphu.vn and find the unit changes made after 1 July 2025.

Run with: uv run python -m pipeline.scan_unit_changes [first_docid [last_docid]]

No official register lists the changes made to the units of Decision 19/2025, and the Official
Gazette (Công báo) does not carry every resolution (237/NQ-UBTVQH16 and 30/2026/QH16 are
published only as signed scans on vanban.chinhphu.vn). This step reads the document page
?pageid=27160&docid=N of vanban.chinhphu.vn for every docid in the range, one request a second,
and keeps its number, issue date, issuer and title.

The range starts at FIRST_DOCID (a document of 16 June 2025, before Decision 19/2025) unless
given. Without a last docid the scan goes on past the highest docid listed until STOP_AFTER
docids in a row have no document. Docids already listed with a document are not read again; a
docid without one ("Không tìm thấy văn bản này") is read again on the next run, and so is a
docid that could not be read. After MAX_ERRORS such docids in a row (the network is down, or the
site is) the scan stops, keeping what it has read.

Output: data/interim/vanban_index.csv, one row per docid: docid, status ("ok", "not_found"),
        number, issued (ISO date), issuer, title, files.
        data/reports/unit_change_scan.json: the docids listed, and the documents issued from
        1 July 2025 whose title changes units:
        - resolutions of the National Assembly or its Standing Committee, each marked "known"
          when pipeline.sources lists it as a unit_change source and "new" otherwise;
        - Government resolutions on a proposal (hồ sơ Đề án) to change units, which precede
          such a resolution and are listed for review only.
The exit code is 1 when a new resolution is found or a docid could not be read.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from pipeline.http import Blocked, Http, NotFound
from pipeline.parse_resolutions import REPORTS_DIR
from pipeline.registry import NOT_UNITS, UNIT_CHANGE
from pipeline.sources import all_sources

PAGE = "https://vanban.chinhphu.vn/?pageid=27160&docid={}"
INDEX = Path("data/interim/vanban_index.csv")
REPORT = REPORTS_DIR / "unit_change_scan.json"
FIELDS = ["docid", "status", "number", "issued", "issuer", "title", "files"]
FIRST_DOCID = 214000
STOP_AFTER = 30
MAX_ERRORS = 10
SINCE = "2025-07-01"
NOT_FOUND_TEXT = "Không tìm thấy văn bản này"
LABELS = {
    "Số ký hiệu": "number",
    "Ngày ban hành": "issued",
    "Cơ quan ban hành": "issuer",
    "Trích yếu": "title",
}
LEGISLATURE = re.compile(r"^(quốc hội|ủy ban thường vụ quốc hội)$", re.IGNORECASE)
PROPOSAL = re.compile(r"hồ sơ Đề án", re.IGNORECASE)
DATE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def read_page(docid: int, html: str) -> dict[str, str]:
    """The index row of one document page."""
    soup = BeautifulSoup(html, "html.parser")
    row = dict.fromkeys(FIELDS, "")
    row["docid"] = str(docid)
    if soup.find(string=lambda s: s is not None and s.strip() == NOT_FOUND_TEXT):
        row["status"] = "not_found"
        return row
    row["status"] = "ok"
    for cell in soup.select("td.col1"):
        field = LABELS.get(cell.get_text(strip=True))
        value = cell.find_next_sibling("td")
        if field and value is not None:
            row[field] = " ".join(value.get_text(" ", strip=True).split())
    date = DATE.fullmatch(row["issued"])
    row["issued"] = f"{date[3]}-{date[2]}-{date[1]}" if date else row["issued"]
    links = soup.select('a[href^="https://datafiles.chinhphu.vn/"]')
    row["files"] = ";".join(sorted({str(a["href"]) for a in links}))
    return row


def classify(row: dict[str, str], known: set[str]) -> str:
    """'known' or 'new' for a unit-change resolution, 'proposal' for a Government resolution on
    a proposal to change units, '' for anything else."""
    if row["status"] != "ok" or row["issued"] < SINCE:
        return ""
    title = row["title"]
    if not UNIT_CHANGE.search(title) or NOT_UNITS.search(title):
        return ""
    if LEGISLATURE.match(row["issuer"]):
        return "known" if row["number"] in known else "new"
    if PROPOSAL.search(title):
        return "proposal"
    return ""


def read_index() -> dict[int, dict[str, str]]:
    if not INDEX.exists():
        return {}
    with INDEX.open(encoding="utf-8") as handle:
        return {int(r["docid"]): r for r in csv.DictReader(handle)}


def write_index(index: dict[int, dict[str, str]]) -> None:
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    with INDEX.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(index[d] for d in sorted(index))


def scan(http: Http, index: dict[int, dict[str, str]], first: int, last: int | None) -> list[str]:
    """Read the pages of the range into index; return the docids that could not be read."""
    errors = []
    docid, misses, read, failing = first, 0, 0, 0
    top = max((d for d, r in index.items() if r["status"] == "ok"), default=first)
    while (docid <= last) if last is not None else (docid <= top or misses < STOP_AFTER):
        if index.get(docid, {}).get("status") != "ok":
            try:
                index[docid] = read_page(docid, http.get(PAGE.format(docid)).text)
                failing = 0
            except NotFound as exc:
                errors.append(f"{docid}: {exc}")
                failing += 1
                if failing == MAX_ERRORS:
                    errors.append(
                        f"stopped at docid {docid}: {MAX_ERRORS} docids in a row not read"
                    )
                    break
            read += 1
            if read % 100 == 0:  # keep what was read if the run stops
                write_index(index)
                print(f"docid {docid}", flush=True)
        found = index.get(docid, {}).get("status") == "ok"
        misses = 0 if found else misses + 1
        docid += 1
    return errors


def main() -> int:
    args = [int(a) for a in sys.argv[1:3]]
    first = args[0] if args else FIRST_DOCID
    last = args[1] if len(args) > 1 else None
    index = read_index()
    blocked = ""
    try:
        errors = scan(Http(archive=False), index, first, last)
    except Blocked as exc:  # automated access refused: stop, as the download policy requires
        errors, blocked = [], str(exc)
    write_index(index)
    known = {s.doc_id for s in all_sources() if s.kind == "unit_change"}
    found: dict[str, list[dict[str, str]]] = {"new": [], "known": [], "proposal": []}
    for docid in sorted(index):
        label = classify(index[docid], known)
        if label:
            row = index[docid]
            found[label].append({k: row[k] for k in ("docid", "number", "issued", "title")})
    listed = [d for d, r in index.items() if r["status"] == "ok"]
    not_found = len(index) - len(listed)
    report = {
        "docids": {
            "first": min(index, default=0),
            "last_with_document": max(listed, default=0),
            "with_document": len(listed),
            "not_found": not_found,
        },
        "latest_issued": max((index[d]["issued"] for d in listed), default=""),
        "resolutions_new": found["new"],
        "resolutions_known": found["known"],
        "proposals": found["proposal"],
        "errors": errors,
        "blocked": blocked,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for label in ("new", "known", "proposal"):
        for r in found[label]:
            print(f"{label:<8} {r['docid']} {r['number']:<18} {r['issued']} {r['title'][:80]}")
    for line in errors:
        print(f"error: {line}")
    if blocked:
        print(f"blocked: {blocked}")
    print(f"{len(listed)} documents, {not_found} docids without one -> {REPORT}")
    return 1 if found["new"] or blocked or errors else 0


if __name__ == "__main__":
    sys.exit(main())
