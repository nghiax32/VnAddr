"""Extract text from the downloaded PDFs into data/interim/text/.

Run with: uv run python -m pipeline.extract

Text is normalised to Unicode NFC and the Công báo running header on each page
("CÔNG BÁO/Số 805 + 806/Ngày 24-6-2025 63") is removed. Pages with almost no text are
reported as scans; they are not OCR'd.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

from pipeline.fetch import MANIFEST

TEXT_DIR = Path("data/interim/text")
SCAN_THRESHOLD = 20  # characters; a page with fewer is treated as an image
GAZETTE_HEADER = re.compile(r"^\s*(\d+\s+)?CÔNG BÁO/Số [\d +]+/Ngày [\d-]+(\s+\d+)?\s*$")


def clean_page(text: str) -> str:
    lines = unicodedata.normalize("NFC", text).splitlines()
    return "\n".join(line for line in lines if not GAZETTE_HEADER.match(line)).strip()


def extract_pdf(path: Path) -> tuple[list[str], int]:
    """Return the cleaned text of each page and the number of pages that look scanned."""
    pages: list[str] = []
    scanned = 0
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            raw = page.extract_text() or ""
            if len(raw.strip()) < SCAN_THRESHOLD:
                scanned += 1
            pages.append(clean_page(raw))
    return pages, scanned


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    problems = 0
    for doc_id, entry in sorted(manifest.items()):
        for file in entry["files"]:
            path = Path(file["path"])
            if path.suffix.lower() != ".pdf":
                continue
            pages, scanned = extract_pdf(path)
            kind = "scan" if scanned == len(pages) else "text"
            print(f"{kind:<5} {doc_id:<18} {len(pages):>4} pages, {scanned:>4} scanned  {path}")
            if file["role"] != "gazette_text":
                continue
            if scanned:
                problems += 1
                print(
                    f"      {scanned} gazette pages without text: ask before OCR", file=sys.stderr
                )
            out = TEXT_DIR / entry["scope"] / f"{path.stem}.txt"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                "".join(f"\f[page {i}]\n{text}\n" for i, text in enumerate(pages, 1)),
                encoding="utf-8",
            )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
