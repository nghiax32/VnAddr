"""Second, independent OCR reading of low-confidence rows of the 2021 appendix.

Run with: uv run python -m pipeline.ocr_second_pass

The cells of every row with confidence < LOW are read again from the page image with a
different setup (2x upscale, binarised, single-line mode). When both readings give the same
villages after normalisation, the row is marked "agreed"; otherwise it goes to the list read by
eye (data/interim/ocr/nam-dinh-2021/disagreements.csv).

Output: data/interim/ocr/nam-dinh-2021/second_pass.csv  (page, y, merged2, new_name2, agreed)
"""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

from pipeline.audit_villages import comparable, ocr_rows
from pipeline.ocr_tables import DARK, OUT_DIR, column_lines, deskew, lines, render

LOW = 80.0


def read_line(image: Image.Image) -> str:
    big = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    binary = big.point(lambda v: 0 if v < 170 else 255)
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        binary.save(handle.name)
        mode = "7" if image.height < 90 else "6"
        result = subprocess.run(
            ["tesseract", handle.name, "-", "-l", "vie", "--psm", mode],
            capture_output=True,
            text=True,
            check=True,
        )
    return unicodedata.normalize("NFC", " ".join(result.stdout.split()))


def page_rows(page: int, wanted: list[dict[str, str]]) -> list[dict[str, object]]:
    image = deskew(Image.open(render(page)).convert("L"))
    dark = np.asarray(image) < DARK
    rows = lines(dark, axis=1, threshold=0.3)
    cols = column_lines(dark, rows)
    out = []
    for r in wanted:
        top = int(r["y"])
        bottom = next((y for y in rows if y > top + 25), top + 140)
        cells = [image.crop((cols[c] + 7, top + 7, cols[c + 1] - 7, bottom - 7)) for c in (2, 3)]
        merged2, new2 = (read_line(cell) for cell in cells)
        agreed = comparable(merged2, new2) == comparable(r["merged"], r["new_name"])
        out.append(
            {"page": page, "y": top, "merged2": merged2, "new_name2": new2, "agreed": agreed}
        )
    return out


def main() -> int:
    low = [r for r in ocr_rows() if float(r["confidence"]) < LOW]
    by_page: dict[int, list[dict[str, str]]] = {}
    for r in low:
        by_page.setdefault(int(r["page"]), []).append(r)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = [
            row for rows in pool.map(lambda p: page_rows(*p), by_page.items()) for row in rows
        ]
    path = OUT_DIR / "second_pass.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["page", "y", "merged2", "new_name2", "agreed"])
        writer.writeheader()
        writer.writerows(results)
    agreed = sum(bool(r["agreed"]) for r in results)
    print(
        f"{len(results)} low-confidence rows read again: {agreed} agree, "
        f"{len(results) - agreed} disagree -> {path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
