"""Tests for the listing of vanban.chinhphu.vn (pipeline.scan_unit_changes).

The page fragments are verbatim from vanban.chinhphu.vn: the field table of docid 218009
(30/2026/QH16) and the message of a docid without a document (220380). The rows are the values
those pages give for docids 219325, 219333, 214000 and 220221."""

from pipeline.http import NotFound
from pipeline.scan_unit_changes import MAX_ERRORS, classify, read_page, scan

PAGE_218009 = """<table style="width: 100%">
            <tr>
                <td class="col1" style="width: 135px">Số ký hiệu</td>
                <td>
                    30/2026/QH16</td>
            </tr>
            <tr>
                <td class="col1">Ngày ban hành</td>
                <td>
                    24-04-2026</td>
            </tr>
            <tr>
                <td class="col1">Cơ quan ban hành</td>
                <td>
                    Quốc hội</td>
            </tr>
            <tr>
                <td class="col1">Trích yếu</td>
                <td>
                    Về việc thành lập thành phố Đồng Nai</td>
            </tr>
            <tr class="doc-list">
                <td class="col1">Tài liệu đính kèm</td>
                <td>
                            <div class="rp-file" style="display: flex">
                                <a href="https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/4/nq30_nqthanhlaptpdongnai.pdf" title="Tải về" download style="color: #005594" target='_blank' class="view-file">nq30_nqthanhlaptpdongnai.pdf
                                </a>
                            </div>
                </td>
            </tr>
        </table>"""  # noqa: E501

PAGE_220380 = """<h4 class="title">
            <span id="ctrl_190596_91_lb_noidung">Không tìm thấy văn bản này</span>
        </h4>"""


def row(docid: str, number: str, issued: str, issuer: str, title: str) -> dict[str, str]:
    return {
        "docid": docid,
        "status": "ok",
        "number": number,
        "issued": issued,
        "issuer": issuer,
        "title": title,
        "files": "",
    }


def test_a_document_page_is_read() -> None:
    assert read_page(218009, PAGE_218009) == {
        "docid": "218009",
        "status": "ok",
        "number": "30/2026/QH16",
        "issued": "2026-04-24",
        "issuer": "Quốc hội",
        "title": "Về việc thành lập thành phố Đồng Nai",
        "files": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/4/nq30_nqthanhlaptpdongnai.pdf",
    }


def test_a_docid_without_a_document_is_marked() -> None:
    page = read_page(220380, PAGE_220380)
    assert (page["status"], page["number"]) == ("not_found", "")


def test_unit_change_resolutions_are_found() -> None:
    city = row(
        "219325", "36/2026/QH16", "2026-08-24", "Quốc hội", "Về việc thành lập thành phố Quảng Ninh"
    )
    assert classify(city, {"36/2026/QH16"}) == "known"
    assert classify(city, set()) == "new"


def test_other_documents_are_left_out() -> None:
    court = row(
        "219333",
        "417/NQ-UBTVQH16",
        "2026-08-24",
        "ỦY BAN THƯỜNG VỤ QUỐC HỘI",
        "Về việc thành lập Tòa án nhân dân, Viện kiểm sát nhân dân thành phố Quảng Ninh",
    )
    before = row(
        "214000",
        "1679/NQ-UBTVQH15",
        "2025-06-16",
        "ỦY BAN THƯỜNG VỤ QUỐC HỘI",
        "Về việc sắp xếp các đơn vị hành chính cấp xã của tỉnh Quảng Ninh năm 2025",
    )
    assert classify(court, set()) == ""
    assert classify(before, set()) == ""  # the 2025 round, before Decision 19/2025


def test_a_government_proposal_is_listed_for_review() -> None:
    proposal = row(
        "220221",
        "351/NQ-CP",
        "2026-11-06",
        "Chính phủ",
        "Về hồ sơ Đề án điều chỉnh địa giới đơn vị hành chính giữa thành phố Hà Nội "
        "và tỉnh Phú Thọ",
    )
    assert classify(proposal, set()) == "proposal"


class Offline:
    """Stands in for pipeline.http.Http when the network is down: every request fails."""

    def __init__(self) -> None:
        self.requests = 0

    def get(self, url: str) -> None:
        self.requests += 1
        raise NotFound(url)


def test_the_scan_stops_when_pages_cannot_be_read() -> None:
    http = Offline()
    index: dict[int, dict[str, str]] = {}
    errors = scan(http, index, 220000, 220100)  # type: ignore[arg-type]
    assert http.requests == MAX_ERRORS
    last = 220000 + MAX_ERRORS - 1
    assert errors[-1] == f"stopped at docid {last}: {MAX_ERRORS} docids in a row not read"
    assert index == {}  # nothing is recorded for a page that was not read
