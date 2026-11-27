"""Parser tests for wordings met in the 2025 resolutions of the other provinces. Each clause is
copied verbatim from the Official Gazette (Công báo) text of the resolution named in the test,
with its line breaks joined, as the parser reads it (pipeline.parse_resolutions.clauses_of)."""

from pipeline.parse_resolutions import parse_clause


def units(rows: list) -> list[tuple[str, str, str, str, str]]:  # type: ignore[type-arg]
    return [(r.old_type, r.old_name, r.old_qualifier, r.share, r.new_name) for r in rows]


def test_area_and_population_sent_to_different_wards() -> None:
    # 1665/NQ-UBTVQH15 (Hà Tĩnh), Điều 1, khoản 62, 63 and 64.
    doc = "1665/NQ-UBTVQH15"
    rows = parse_clause(
        doc,
        62,
        "Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của phường Kỳ Long, phường Kỳ Thịnh "
        "và toàn bộ diện tích tự nhiên của xã Kỳ Lợi thành phường mới có tên gọi là phường "
        "Vũng Áng.",
    )
    rows += parse_clause(
        doc,
        63,
        "Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của phường Hưng Trí, phường Kỳ "
        "Trinh, xã Kỳ Châu và một phần quy mô dân số của xã Kỳ Lợi thành phường mới có tên gọi "
        "là phường Sông Trí.",
    )
    rows += parse_clause(
        doc,
        64,
        "Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của các phường Kỳ Nam, Kỳ Phương, "
        "Kỳ Liên và phần quy mô dân số còn lại của xã Kỳ Lợi sau khi sắp xếp theo quy định tại "
        "khoản 63 Điều này thành phường mới có tên gọi là phường Hoành Sơn.",
    )
    assert [u for u in units(rows) if u[1] == "Kỳ Lợi"] == [
        ("xa", "Kỳ Lợi", "", "part", "Vũng Áng"),
        ("xa", "Kỳ Lợi", "", "part", "Sông Trí"),
        ("xa", "Kỳ Lợi", "", "rest", "Hoành Sơn"),
    ]
    assert rows[-1].rest_after_clauses == "63"


def test_boundary_adjustment_keeps_the_commune() -> None:
    # 1679/NQ-UBTVQH15 (Quảng Ninh), Điều 1, khoản 3.
    rows = parse_clause(
        "1679/NQ-UBTVQH15",
        3,
        "Điều chỉnh một phần diện tích tự nhiên của xã Hải Hòa để nhập vào xã Hải Lạng.",
    )
    assert units(rows) == [("xa", "Hải Hòa", "", "part", "Hải Hòa")]


def test_rename() -> None:
    # 1660/NQ-UBTVQH15 (Đắk Lắk), Điều 1, khoản 96.
    rows = parse_clause("1660/NQ-UBTVQH15", 96, "Đổi tên xã Krông Na thành xã Buôn Đôn.")
    assert units(rows) == [("xa", "Krông Na", "", "renamed", "Buôn Đôn")]
    assert rows[0].mapping_type == "renamed"


def test_words_run_together() -> None:
    # 1669/NQ-UBTVQH15 (Hải Phòng), Điều 1, khoản 17: "phườngNgọc Sơn".
    rows = parse_clause(
        "1669/NQ-UBTVQH15",
        17,
        "Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của phường Bắc Hà, phườngNgọc Sơn, "
        "một phần diện tích tự nhiên của thị trấn Trường Sơn và phần còn lại của các phường Nam "
        "Sơn (quận Kiến An), Đồng Hòa, Bắc Sơn, Trần Thành Ngọ, Văn Đẩu sau khi sắp xếp theo "
        "quy định tại khoản 16 Điều này thành phường mới có tên gọi là phường Phù Liễn.",
    )
    assert [(r.old_type, r.old_name, r.share) for r in rows[:3]] == [
        ("phuong", "Bắc Hà", "full"),
        ("phuong", "Ngọc Sơn", "full"),
        ("thi_tran", "Trường Sơn", "part"),
    ]
    assert len(rows) == 8


def test_comma_inside_the_district_qualifier() -> None:
    # 1687/NQ-UBTVQH15 (Vĩnh Long), Điều 1, khoản 34.
    rows = parse_clause(
        "1687/NQ-UBTVQH15",
        34,
        "Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của thị trấn Châu Thành (huyện Châu "
        "Thành, tỉnh Trà Vinh) và các xã Mỹ Chánh (huyện Châu Thành), Thanh Mỹ, Đa Lộc thành xã "
        "mới có tên gọi là xã Châu Thành.",
    )
    assert [(r.old_type, r.old_name, r.old_qualifier) for r in rows] == [
        ("thi_tran", "Châu Thành", "huyện Châu Thành, tỉnh Trà Vinh"),
        ("xa", "Mỹ Chánh", "huyện Châu Thành"),
        ("xa", "Thanh Mỹ", ""),
        ("xa", "Đa Lộc", ""),
    ]


def test_unit_named_after_a_reference_belongs_to_the_whole_list() -> None:
    # 1684/NQ-UBTVQH15 (Tuyên Quang), Điều 1, khoản 111.
    rows = parse_clause(
        "1684/NQ-UBTVQH15",
        111,
        "Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của các phường Ngọc Hà, Trần Phú, "
        "Minh Khai, phần còn lại của phường Quang Trung sau khi sắp xếp theo quy định tại khoản "
        "110 Điều này và xã Phong Quang thành phường mới có tên gọi là phường Hà Giang 2.",
    )
    assert [(r.old_type, r.old_name, r.share) for r in rows] == [
        ("phuong", "Ngọc Hà", "full"),
        ("phuong", "Trần Phú", "full"),
        ("phuong", "Minh Khai", "full"),
        ("phuong", "Quang Trung", "rest"),
        ("xa", "Phong Quang", "full"),
    ]
