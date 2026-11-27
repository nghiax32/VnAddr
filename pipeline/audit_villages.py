"""Prepare page-image sheets for checking OCR rows by eye (layers 3 and 4).

Run with: uv run python -m pipeline.audit_villages sample [N]     random sample, fixed seed
          uv run python -m pipeline.audit_villages review          low-confidence / flagged rows
          uv run python -m pipeline.audit_villages score           compare with the answer key

Each sheet stacks up to ROWS_PER_SHEET table rows cut from the deskewed page image (columns 2-4:
commune, villages merged, new village), each labelled with its number. The OCR text of the same
rows is written to sheets.csv. Whoever checks the sheets records a verdict per row in
data/reports/audit-nam-dinh-2021.csv (row, verdict ok|error, correct text, note).
"""

from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from pipeline.ocr_tables import OUT_DIR, deskew, render

AUDIT_DIR = Path("data/interim/audit/nam-dinh-2021")
SEED = 20261126
ROWS_PER_SHEET = 15
X0, X1 = 350, 2690  # columns 2-4 at 300 dpi
SCALE = 0.45


def ocr_rows() -> list[dict[str, str]]:
    with (OUT_DIR / "appendix1.csv").open(encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle) if not r["merged"].startswith("(")]
    rows.sort(key=lambda r: (int(r["page"]), int(r["y"])))
    return rows


def row_bottom(rows: list[dict[str, str]], row: dict[str, str]) -> int:
    later = [int(r["y"]) for r in rows if r["page"] == row["page"] and int(r["y"]) > int(row["y"])]
    return min(later) if later else int(row["y"]) + 140


def sheets(selected: list[dict[str, str]], all_rows: list[dict[str, str]], name: str) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    pages: dict[str, Image.Image] = {}
    with (AUDIT_DIR / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row", "page", "y", "commune", "merged", "new_name", "confidence"])
        for start in range(0, len(selected), ROWS_PER_SHEET):
            crops = []
            for i, row in enumerate(selected[start : start + ROWS_PER_SHEET], start + 1):
                page = row["page"]
                if page not in pages:
                    pages[page] = deskew(Image.open(render(int(page))).convert("L"))
                top, bottom = int(row["y"]) - 4, row_bottom(all_rows, row) + 6
                crop = pages[page].crop((X0, top, X1, bottom))
                crop = crop.resize((int(crop.width * SCALE), int(crop.height * SCALE)))
                label = Image.new("L", (60, crop.height), 255)
                ImageDraw.Draw(label).text((8, crop.height // 2 - 6), str(i), fill=0)
                line = Image.new("L", (label.width + crop.width, crop.height), 255)
                line.paste(label, (0, 0))
                line.paste(crop, (label.width, 0))
                crops.append(line)
                writer.writerow(
                    [
                        i,
                        page,
                        row["y"],
                        row["unit"],
                        row["merged"],
                        row["new_name"],
                        row["confidence"],
                    ]
                )
            sheet = Image.new(
                "L", (max(c.width for c in crops), sum(c.height + 4 for c in crops)), 255
            )
            y = 0
            for crop in crops:
                sheet.paste(crop, (0, y))
                y += crop.height + 4
            sheet.save(AUDIT_DIR / f"{name}-{start // ROWS_PER_SHEET + 1:02d}.png")


TRUTH = Path("data/audit/nam-dinh-2021-sample.csv")


def comparable(row_merged: str, row_new: str) -> tuple[tuple[str, ...], str]:
    from pipeline.parse_village_tables import old_units, split_type
    from pipeline.validate_villages import key

    olds = tuple(sorted(f"{t} {key(n)}" for t, n in old_units(row_merged)))
    new_type, new_name = split_type(row_new)
    return olds, f"{new_type} {key(new_name)}"


def wilson(errors: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = errors / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def score() -> int:
    """Compare the pipeline output with the rows read by eye from the page images."""
    from pipeline.parse_village_tables import evidence_sources

    corrections, _ = evidence_sources()
    ocr = {}
    for r in ocr_rows():
        fixed = corrections.get((r["page"], r["y"]))
        ocr[(r["page"], r["y"])] = dict(r, **fixed) if fixed else r
    with TRUTH.open(encoding="utf-8") as handle:
        truth = list(csv.DictReader(handle))
    errors = []
    for t in truth:
        got = ocr[(t["page"], t["y"])]
        if comparable(got["merged"], got["new_name"]) != comparable(t["merged"], t["new_name"]):
            errors.append((t["row"], got["merged"], got["new_name"], t["merged"], t["new_name"]))
    low, high = wilson(len(errors), len(truth))
    print(
        f"{len(truth) - len(errors)}/{len(truth)} rows exact; error rate "
        f"{len(errors) / len(truth):.0%} (95% CI {low:.0%}-{high:.0%})"
    )
    for row, got_m, got_n, want_m, want_n in errors:
        print(f"  row {row}: got  {got_m} -> {got_n}\n          want {want_m} -> {want_n}")
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "sample"
    rows = ocr_rows()
    if mode == "score":
        return score()
    if mode == "sample":
        size = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        selected = random.Random(SEED).sample(rows, size)
        selected.sort(key=lambda r: (int(r["page"]), int(r["y"])))
        sheets(selected, rows, "sample")
    else:
        # Rows whose two OCR readings disagree (pipeline.ocr_second_pass).
        with (OUT_DIR / "second_pass.csv").open(encoding="utf-8") as handle:
            disagree = {
                (r["page"], r["y"]) for r in csv.DictReader(handle) if r["agreed"] != "True"
            }
        selected = [r for r in rows if (r["page"], r["y"]) in disagree]
        sheets(selected, rows, "review")
    print(f"{len(selected)} rows -> {AUDIT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
