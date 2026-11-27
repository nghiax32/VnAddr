"""OCR the appendix table of Resolution 63/2021/NQ-HĐND (Nam Định), which is only available as a
scan, into one row per merged village group.

Run with: uv run python -m pipeline.ocr_tables

Each page is rendered at 300 dpi, deskewed, and split into cells along its ruling lines; every
cell is OCR'd on its own with Tesseract (language "vie"), which reads table text far better than
a whole page. The appendix columns are:

    1 STT | 2 administrative unit | 3 villages merged | 4 new village | 5 households
    | 6 people | 7 area (ha) | 8 note

Columns 1 and 2 span several rows (one commune, several merges); they are read once per span.
Every row keeps the lowest Tesseract word confidence of its cells so that low-confidence rows
can be checked against the page image.

Output: data/interim/ocr/nam-dinh-2021/appendix1.csv (+ page images, ignored by git)
"""

from __future__ import annotations

import csv
import itertools
import re
import subprocess
import sys
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image

PDF = Path("data/raw/villages/nam-dinh-2021/63-2021-NQ-HDND.pdf")
OUT_DIR = Path("data/interim/ocr/nam-dinh-2021")
FIRST_PAGE, LAST_PAGE = 5, 37  # Phụ lục 1: kết quả sáp nhập thôn (xóm), tổ dân phố
DPI = 300
DARK = 160


@dataclass
class Cell:
    text: str
    confidence: float  # lowest word confidence, 0..100; 100 for an empty cell


@dataclass
class Row:
    page: int
    y: int
    stt: str
    unit: str
    merged: str
    new_name: str
    households: str
    people: str
    area_ha: str
    confidence: float


def render(page: int) -> Path:
    path = OUT_DIR / "pages" / f"page-{page:02d}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = path.parent / f"tmp-{page:02d}"
        subprocess.run(
            [
                "pdftoppm",
                "-r",
                str(DPI),
                "-gray",
                "-png",
                "-f",
                str(page),
                "-l",
                str(page),
                "-singlefile",
                str(PDF),
                str(prefix),
            ],
            check=True,
        )
        prefix.with_suffix(".png").rename(path)
    return path


def deskew(image: Image.Image) -> Image.Image:
    small = image.resize((image.width // 4, image.height // 4))
    best = max(
        np.arange(-3.0, 3.01, 0.05),
        key=lambda angle: float(
            ((np.asarray(small.rotate(angle, fillcolor=255)) < DARK).mean(axis=1) ** 2).sum()
        ),
    )
    return image.rotate(float(best), fillcolor=255, resample=Image.Resampling.BICUBIC)


def lines(dark: np.ndarray, axis: int, threshold: float, gap: int = 6) -> list[int]:
    positions = np.where(dark.mean(axis=axis) > threshold)[0]
    groups: list[list[int]] = []
    for p in positions:
        if groups and p - groups[-1][-1] <= gap:
            groups[-1].append(int(p))
        else:
            groups.append([int(p)])
    return [int(np.mean(g)) for g in groups]


def column_lines(dark: np.ndarray, rows: list[int]) -> list[int]:
    """The 9 vertical ruling lines of the table.

    Scans are not perfectly straight, so a vertical line drifts by a few pixels from top to
    bottom. Each pixel row is widened horizontally (11 px) before averaging, and only the part
    of the page between the first and last horizontal line is used. Text aligned in a column
    ("Sáp nhập ...") gives fainter bands; the 9 strongest, well separated peaks are kept."""
    body = dark[rows[0] : rows[-1]] if len(rows) >= 2 else dark
    widened = body.copy()
    for shift in range(1, 6):
        widened[:, shift:] |= body[:, :-shift]
        widened[:, :-shift] |= body[:, shift:]
    profile = widened.mean(axis=0)
    peaks = [
        x
        for x in range(1, len(profile) - 1)
        if profile[x] >= 0.5 and profile[x] == profile[max(0, x - 25) : x + 26].max()
    ]
    merged: list[int] = []
    for x in peaks:
        if merged and x - merged[-1] < 25:
            continue
        merged.append(x)
    strongest = sorted(sorted(merged, key=lambda x: -profile[x])[:9])
    return strongest


def ocr(image: Image.Image) -> Cell:
    if (np.asarray(image) < DARK).mean() < 0.002:
        return Cell("", 100.0)
    with tempfile.NamedTemporaryFile(suffix=".png") as handle:
        image.save(handle.name)
        result = subprocess.run(
            ["tesseract", handle.name, "-", "-l", "vie", "--psm", "6", "tsv"],
            capture_output=True,
            text=True,
            check=True,
        )
    words: list[tuple[int, int, int, str]] = []
    confidences: list[float] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 12 and parts[11].strip() and float(parts[10]) >= 0:
            words.append((int(parts[2]), int(parts[4]), int(parts[5]), parts[11]))
            confidences.append(float(parts[10]))
    text = " ".join(w[3] for w in sorted(words))
    text = unicodedata.normalize("NFC", re.sub(r"\s+", " ", text)).strip(" |")
    return Cell(text, min(confidences) if confidences else 0.0)


def crop(image: Image.Image, x0: int, y0: int, x1: int, y1: int, pad: int = 7) -> Image.Image:
    return image.crop((x0 + pad, y0 + pad, x1 - pad, y1 - pad))


def spans(dark: np.ndarray, rows: list[int], x0: int, x1: int) -> list[tuple[int, int]]:
    """Row ranges of a column whose cells span several rows: a horizontal line only splits
    the column where it actually crosses it."""
    crossing = [
        y for y in rows if dark[max(0, y - 4) : y + 5, x0 + 10 : x1 - 10].any(axis=0).mean() > 0.8
    ]
    return list(itertools.pairwise(crossing))


def read_page(page: int) -> tuple[list[Row], str]:
    image = deskew(Image.open(render(page)).convert("L"))
    dark = np.asarray(image) < DARK
    rows = lines(dark, axis=1, threshold=0.3)
    cols = column_lines(dark, rows)
    if len(cols) < 9 or len(rows) < 3:
        return [], f"page {page}: {len(cols)} vertical and {len(rows)} horizontal lines"
    cols = cols[:9]

    def span_text(c: int) -> list[tuple[int, int, Cell]]:
        return [
            (a, b, ocr(crop(image, cols[c], a, cols[c + 1], b)))
            for a, b in spans(dark, rows, cols[c], cols[c + 1])
            if b - a > 25
        ]

    stt_spans, unit_spans = span_text(0), span_text(1)

    def at(found: list[tuple[int, int, Cell]], y: int) -> Cell:
        return next((cell for a, b, cell in found if a <= y < b), Cell("", 100.0))

    out: list[Row] = []
    for top, bottom in itertools.pairwise(rows):
        if bottom - top < 25:
            continue
        cells = [ocr(crop(image, cols[c], top, cols[c + 1], bottom)) for c in (2, 3, 4, 5, 6)]
        merged = cells[0].text
        if not merged or merged in {"3"} or merged.startswith("Tên thôn"):
            continue  # header rows
        middle = (top + bottom) // 2
        stt, unit = at(stt_spans, middle), at(unit_spans, middle)
        out.append(
            Row(
                page,
                top,
                stt.text,
                unit.text,
                merged,
                cells[1].text,
                cells[2].text,
                cells[3].text,
                cells[4].text,
                min(c.confidence for c in [stt, unit, cells[0], cells[1]]),
            )
        )
    return out, ""


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages = range(FIRST_PAGE, LAST_PAGE + 1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read_page, pages))
    rows = [row for found, _ in results for row in found]
    problems = [problem for _, problem in results if problem]
    with (OUT_DIR / "appendix1.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Row.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(r) for r in rows)
    low = sum(1 for r in rows if r.confidence < 80)
    print(f"{len(rows)} rows from {len(pages)} pages, {low} with confidence < 80")
    for problem in problems:
        print("  unread", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
