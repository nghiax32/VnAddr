"""Legal documents the pipeline reads, with their official download locations.

Each document is taken from two official sources:

- the signed PDF on vanban.chinhphu.vn / datafiles.chinhphu.vn, kept as the reference copy
  (these are scans with no text layer);
- the Official Gazette (Công báo, congbao.chinhphu.vn), whose PDF and DOC files have a text
  layer and are the ones the pipeline extracts text from.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Source:
    doc_id: str  # e.g. "1685/NQ-UBTVQH15"
    kind: str  # "codes" | "ward_resolution" | "village_resolution"
    scope: str  # directory under data/raw/, e.g. "national", "ho-chi-minh"
    title: str
    signed_pdf: str  # scanned, signed copy ("" when its address is not known)
    landing_page: str  # vanban.chinhphu.vn entry
    gazette_page: str  # congbao.chinhphu.vn entry listing the text PDF/DOC downloads


SOURCES: tuple[Source, ...] = (
    Source(
        doc_id="19/2025/QĐ-TTg",
        kind="codes",
        scope="national",
        title="Ban hành Bảng danh mục và mã số các đơn vị hành chính Việt Nam",
        signed_pdf="https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/7/19ttg.signed.pdf",
        landing_page="https://vanban.chinhphu.vn/?pageid=27160&docid=214409",
        gazette_page="https://congbao.chinhphu.vn/van-ban/quyet-dinh-so-19-2025-qd-ttg-45430.htm",
    ),
    Source(
        doc_id="1685/NQ-UBTVQH15",
        kind="ward_resolution",
        scope="ho-chi-minh",
        title="Sắp xếp các đơn vị hành chính cấp xã của Thành phố Hồ Chí Minh năm 2025",
        signed_pdf="https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/6/1685-nq.signed.pdf",
        landing_page="https://vanban.chinhphu.vn/?pageid=27160&docid=214007",
        gazette_page="https://congbao.chinhphu.vn/van-ban/x-45141.htm",
    ),
    Source(
        doc_id="1674/NQ-UBTVQH15",
        kind="ward_resolution",
        scope="ninh-binh",
        title="Sắp xếp các đơn vị hành chính cấp xã của tỉnh Ninh Bình năm 2025",
        signed_pdf="https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/6/1674-nq.signed.pdf",
        landing_page="https://vanban.chinhphu.vn/?pageid=27160&docid=213997",
        gazette_page="https://congbao.chinhphu.vn/van-ban/x-45129.htm",
    ),
    # 2023-2025 round (cấp huyện, cấp xã), needed to follow communes from before 2024 to 2025.
    Source(
        doc_id="1104/NQ-UBTVQH15",
        kind="ward_resolution_2024",
        scope="nam-dinh-2024",
        title="Sắp xếp đơn vị hành chính cấp huyện, cấp xã giai đoạn 2023 - 2025 của tỉnh Nam Định",
        signed_pdf="",
        landing_page="https://vanban.chinhphu.vn/?pageid=27160&docid=210788",
        gazette_page="https://congbao.chinhphu.vn/van-ban/x-42453.htm",
    ),
    Source(
        doc_id="1288/NQ-UBTVQH15",
        kind="ward_resolution_2024",
        scope="ha-nam-2024",
        title="Sắp xếp đơn vị hành chính cấp huyện, cấp xã của tỉnh Hà Nam giai đoạn 2023 - 2025",
        signed_pdf="",
        landing_page="https://vanban.chinhphu.vn/?pageid=27160&docid=211789",
        gazette_page="https://congbao.chinhphu.vn/van-ban/x-43257.htm",
    ),
    Source(
        doc_id="1318/NQ-UBTVQH15",
        kind="ward_resolution_2024",
        scope="ninh-binh-2024",
        title=(
            "Sắp xếp đơn vị hành chính cấp huyện, cấp xã của tỉnh Ninh Bình giai đoạn 2023 - 2025"
        ),
        signed_pdf="",
        landing_page="https://vanban.chinhphu.vn/?pageid=27160&docid=211988",
        gazette_page="https://congbao.chinhphu.vn/van-ban/x-43491.htm",
    ),
    # 2019-2021 round, needed to follow communes from 2019 to the 2023-2025 round.
    Source(
        doc_id="829/NQ-UBTVQH14",
        kind="ward_resolution_2020",
        scope="ha-nam-2020",
        title="Sắp xếp các đơn vị hành chính cấp huyện, cấp xã thuộc tỉnh Hà Nam",
        signed_pdf="",
        landing_page="https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=198694",
        gazette_page="https://congbao.chinhphu.vn/van-ban/x-30317.htm",
    ),
    Source(
        doc_id="858/NQ-UBTVQH14",
        kind="ward_resolution_2020",
        scope="nam-dinh-2020",
        title="Sắp xếp các đơn vị hành chính cấp xã thuộc tỉnh Nam Định",
        signed_pdf="",
        landing_page="https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=199009",
        gazette_page="https://congbao.chinhphu.vn/van-ban/x-30657.htm",
    ),
    Source(
        doc_id="861/NQ-UBTVQH14",
        kind="ward_resolution_2020",
        scope="ninh-binh-2020",
        title="Sắp xếp các đơn vị hành chính cấp xã thuộc tỉnh Ninh Bình",
        signed_pdf="",
        landing_page="https://congbao.chinhphu.vn/van-ban/x-30660.htm",
        gazette_page="https://congbao.chinhphu.vn/van-ban/x-30660.htm",
    ),
)

# Every other rearrangement resolution, listed by pipeline.registry from the Công báo scans.
REGISTRY = Path(__file__).parent / "sources.csv"
KIND_OF_ROUND = {
    "2020": "ward_resolution_2020",
    "2024": "ward_resolution_2024",
    "2025": "ward_resolution",
}


def all_sources() -> tuple[Source, ...]:
    """SOURCES, then the registry rows for documents not already in SOURCES."""
    known = {s.doc_id for s in SOURCES}
    extra = []
    if REGISTRY.exists():
        with REGISTRY.open(encoding="utf-8") as handle:
            for r in csv.DictReader(handle):
                if r["doc_id"] in known:
                    continue
                extra.append(
                    Source(
                        doc_id=r["doc_id"],
                        kind=KIND_OF_ROUND[r["round"]],
                        scope=r["scope"],
                        title=r["title"],
                        signed_pdf="",
                        landing_page=r["gazette_page"],
                        gazette_page=r["gazette_page"],
                    )
                )
    return (*SOURCES, *extra)
