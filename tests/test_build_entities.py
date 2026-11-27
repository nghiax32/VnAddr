"""Tests for reading Decision 19/2025/QĐ-TTg (pipeline.build_entities), on its Official Gazette
(Công báo) text: issue 919+920 (Phụ lục I, and the start and end of the list of tỉnh Hà Tĩnh with
the back cover of the issue) followed by the start of issue 921+922 (its masthead and the start of
the list of tỉnh Quảng Trị). Lines are verbatim; the rows left out are marked below."""

from pipeline.build_entities import check, parse

# Phụ lục I, rows 18 and 19 of 34.
ANNEX_I = """Phụ lục I
DANH MỤC VÀ MÃ SỐ CÁC ĐƠN VỊ HÀNH CHÍNH CẤP TỈNH
(Kèm theo Quyết định số 19/2025/QĐ-TTg
ngày 30 tháng 6 năm 2025 của Thủ tướng Chính phủ)
STT Mã số Tên tỉnh, thành phố
18 42 Tỉnh Hà Tĩnh
19 44 Tỉnh Quảng Trị
"""

# Phụ lục II: the first two and the last two communes of tỉnh Hà Tĩnh (the 65 between are left
# out), the end of issue 919+920, then the start of issue 921+922.
ANNEX_II = """Phụ lục II
DANH MỤC VÀ MÃ SỐ CÁC ĐƠN VỊ HÀNH CHÍNH CẤP XÃ
(Kèm theo Quyết định số 19/2025/QĐ-TTg
ngày 30 tháng 6 năm 2025 của Thủ tướng Chính phủ)
42. TỈNH HÀ TĨNH
(Tổng số đơn vị hành chính cấp xã: 69, gồm 60 xã, 09 phường)
Mã số Tên đơn vị hành chính
18073 Phường Thành Sen
18100 Phường Trần Phú
18838 Xã Kỳ Lạc
18844 Xã Kỳ Thượng
(Xem tiếp Công báo số 921 + 922)
[page 95]
VĂN PHÒNG CHÍNH PHỦ XUẤT BẢN
Địa chỉ: Số 1, Hoàng Hoa Thám, Ba Đình, Hà Nội
Điện thoại liên hệ:
- Nội dung: 080.44417
- Phát hành: 080.44243
Email: congbao@chinhphu.vn
Website http://congbao.chinhphu.vn
[page 1]
VĂN BẢN QUY PHẠM PHÁP LUẬT
THỦ TƯỚNG CHÍNH PHỦ
Quyết định số 19/2025/QĐ-TTg ngày 30 tháng 6 năm 2025
ban hành Bảng danh mục và mã số các đơn vị hành chính Việt Nam
(Tiếp theo Công báo số 919 + 920)
44. TỈNH QUẢNG TRỊ
(Tổng số đơn vị hành chính cấp xã: 78, gồm 69 xã, 08 phường, 01 đặc khu)
Mã số Tên đơn vị hành chính
18859 Phường Đồng Thuận
18871 Phường Đồng Sơn
"""


def test_units_and_stated_counts_are_read() -> None:
    provinces, wards, stated, unread = parse((ANNEX_I + ANNEX_II).splitlines())
    assert provinces == [
        {"code": "42", "name": "Hà Tĩnh", "type": "tinh"},
        {"code": "44", "name": "Quảng Trị", "type": "tinh"},
    ]
    assert wards[0] == {
        "code": "18073",
        "name": "Thành Sen",
        "type": "phuong",
        "province_code": "42",
    }
    assert wards[-1] == {
        "code": "18871",
        "name": "Đồng Sơn",
        "type": "phuong",
        "province_code": "44",
    }
    assert [w["code"] for w in wards] == ["18073", "18100", "18838", "18844", "18859", "18871"]
    assert stated["44"] == {"total": 78, "xa": 69, "phuong": 8, "dac_khu": 1}
    # The back cover and the masthead of the next issue are not read as communes.
    assert unread == []


def test_counts_are_checked_against_the_heading() -> None:
    provinces, wards, stated, _ = parse((ANNEX_I + ANNEX_II).splitlines())
    problems = check(provinces, wards, stated)
    assert "2 provinces in Phụ lục I, expected 34" in problems
    assert "province 42: 4 communes, stated 69" in problems
    assert "province 44: 0 xa, stated 69" in problems
    assert "province 44: 0 dac_khu, stated 1" in problems


def test_a_heading_missing_from_annex_i_is_reported() -> None:
    lines = [line for line in (ANNEX_I + ANNEX_II).splitlines() if line != "19 44 Tỉnh Quảng Trị"]
    _, _, _, unread = parse(lines)
    assert unread == ["heading 44 'TỈNH QUẢNG TRỊ' does not match Phụ lục I"]
