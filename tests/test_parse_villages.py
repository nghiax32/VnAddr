"""Village parser tests on text copied from the Resolution of the People's Council of Liên Minh
commune (Ninh Bình) on rearranging villages in 2026, adopted on 23 June 2026."""

from pipeline.parse_villages import parse_document

LIEN_MINH = """HỘI ĐỒNG NHÂN DÂN CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM
XÃ LIÊN MINH Độc lập - Tự do - Hạnh phúc
NGHỊ QUYẾT
Về việc sắp xếp, tổ chức lại thôn (xóm) trên địa bàn xã Liên Minh năm 2026
QUYẾT NGHỊ:
Điều 1. Sắp xếp, tổ chức lại thôn trên địa bàn xã như sau:
1. Thành lập thôn Thượng trên cơ sở nhập toàn bộ Đội 1 xóm Thượng với
Đội 2 xóm Thượng.
3. Thành lập thôn Hào Kiệt trên cơ sở nhập toàn bộ Đội 6 Nhì Giáp với Đội
7 Nhì Giáp và thôn Nhất Giáp.
2
10. Thành lập thôn Cố Bản trên cơ sở nhập toàn thôn Phong Vinh với thôn
Đồng Tiến và thôn Làng Mới.
13. Giữ nguyên thôn Đại Lại.
Lý do không thực hiện sắp xếp, tổ chức lại: Đảm bảo theo quy định tại Nghị
định số 185/2026/NĐ-CP ngày 26/5/2026 của Chính phủ.
Điều 3. Nghị quyết có hiệu lực thi hành kể từ ngày 01 tháng 7 năm 2026.
Nghị quyết này đã được Hội đồng nhân dân xã Liên Minh khoá II kỳ họp thứ
hai thông qua ngày 23 tháng 6 năm 2026./.
"""

BASE = {"commune_code": "13786", "commune_name": "Liên Minh", "document": "", "document_url": ""}


def test_liên_minh_resolution() -> None:
    rows, unread = parse_document(LIEN_MINH, BASE)
    assert unread == []
    got = [(r.clause, r.action, r.old_type, r.old_name, r.new_type, r.new_name) for r in rows]
    assert got == [
        ("1", "merged", "đội", "1 xóm Thượng", "thôn", "Thượng"),
        ("1", "merged", "đội", "2 xóm Thượng", "thôn", "Thượng"),
        ("3", "merged", "đội", "6 Nhì Giáp", "thôn", "Hào Kiệt"),
        ("3", "merged", "đội", "7 Nhì Giáp", "thôn", "Hào Kiệt"),
        ("3", "merged", "thôn", "Nhất Giáp", "thôn", "Hào Kiệt"),
        ("10", "merged", "thôn", "Phong Vinh", "thôn", "Cố Bản"),
        ("10", "merged", "thôn", "Đồng Tiến", "thôn", "Cố Bản"),
        ("10", "merged", "thôn", "Làng Mới", "thôn", "Cố Bản"),
        ("13", "unchanged", "thôn", "Đại Lại", "thôn", "Đại Lại"),
    ]
    assert {(r.evidence, r.adopted, r.effective) for r in rows} == {
        ("resolution", "2026-06-23", "2026-07-01")
    }
