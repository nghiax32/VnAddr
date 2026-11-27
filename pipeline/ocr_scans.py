"""OCR the documents that are published only as scans.

Run with: uv run python -m pipeline.ocr_scans [kind ...]   (default kind: unit_change)

Some resolutions have no text layer anywhere: the signed PDF on vanban.chinhphu.vn is a scan,
and the Official Gazette (Công báo) copy, when there is one, is a scan too. For each document of
the given kinds this renders every page of its gazette PDF (or, without one, its signed PDF) at
300 dpi and reads it with Tesseract (Vietnamese, one text block per page).

Output: data/interim/text/<scope>/<file stem>.txt, pages marked "[page N]" as pipeline.extract
does. The text is the OCR output as read; corrections made from the page images are kept in
data/audit/ and applied by the step that reads the text (pipeline.parse_unit_changes).

Needs the system tools pdftoppm (poppler-utils) and tesseract with the "vie" language pack.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from pipeline.extract import TEXT_DIR
from pipeline.fetch import MANIFEST

DPI = 300


def ocr_pdf(path: Path) -> list[str]:
    """Return the OCR text of each page of a PDF."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdftoppm", "-r", str(DPI), "-gray", "-png", str(path), f"{tmp}/page"],
            check=True,
        )
        pages = []
        for image in sorted(Path(tmp).glob("page-*.png"), key=lambda p: int(p.stem.split("-")[1])):
            result = subprocess.run(
                ["tesseract", str(image), "-", "-l", "vie", "--psm", "6"],
                check=True,
                capture_output=True,
                text=True,
            )
            pages.append(unicodedata.normalize("NFC", result.stdout).strip())
    return pages


def scanned_file(files: list[dict[str, str]]) -> Path | None:
    """The gazette PDF if there is one, else the signed PDF."""
    for role in ("gazette_text", "signed_scan"):
        for f in files:
            if f["role"] == role and f["path"].lower().endswith(".pdf"):
                return Path(f["path"])
    return None


def main() -> int:
    kinds = set(sys.argv[1:]) or {"unit_change"}
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for doc_id, entry in sorted(manifest.items()):
        if entry["kind"] not in kinds:
            continue
        path = scanned_file(entry["files"])
        if path is None:
            print(f"skip {doc_id}: no PDF in the manifest", file=sys.stderr)
            continue
        pages = ocr_pdf(path)
        out = TEXT_DIR / entry["scope"] / f"{path.stem}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "".join(f"\f[page {i}]\n{text}\n" for i, text in enumerate(pages, 1)),
            encoding="utf-8",
        )
        print(f"ocr  {doc_id:<18} {len(pages):>3} pages -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
