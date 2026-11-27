"""Parser tests on clauses copied verbatim from the Official Gazette (Công báo) text of
Resolutions 1685/NQ-UBTVQH15 (Ho Chi Minh City) and 1674/NQ-UBTVQH15 (Ninh Bình)."""

from pipeline.parse_resolutions import parse_clause

HCM = "1685/NQ-UBTVQH15"
NB = "1674/NQ-UBTVQH15"


def units(rows: list) -> list[tuple[str, str, str, str]]:  # type: ignore[type-arg]
    return [(r.old_type, r.old_name, r.old_qualifier, r.share) for r in rows]


def test_whole_and_part_of_a_list() -> None:
    rows = parse_clause(
        HCM,
        1,
        "Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của phường Bến Nghé và một phần "
        "diện tích tự nhiên, quy mô dân số của phường Đa Kao, phường Nguyễn Thái Bình thành "
        "phường mới có tên gọi là phường Sài Gòn.",
    )
    assert {(r.new_type, r.new_name) for r in rows} == {("phuong", "Sài Gòn")}
    assert units(rows) == [
        ("phuong", "Bến Nghé", "", "full"),
        ("phuong", "Đa Kao", "", "part"),
        ("phuong", "Nguyễn Thái Bình", "", "part"),
    ]
    assert [r.mapping_type for r in rows] == ["merged_full", "split_partial", "split_partial"]


def test_numbered_wards_take_the_district_written_after_the_list() -> None:
    rows = parse_clause(
        HCM,
        5,
        "Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của Phường 1, Phường 2, Phường 3, "
        "Phường 5 và một phần diện tích tự nhiên, quy mô dân số của Phường 4 (Quận 3) thành "
        "phường mới có tên gọi là phường Bàn Cờ.",
    )
    assert units(rows) == [
        ("phuong", "1", "Quận 3", "full"),
        ("phuong", "2", "Quận 3", "full"),
        ("phuong", "3", "Quận 3", "full"),
        ("phuong", "5", "Quận 3", "full"),
        ("phuong", "4", "Quận 3", "part"),
    ]
    assert [r.qualifier_inferred for r in rows] == [True, True, True, True, False]


def test_rest_of_a_unit_split_by_an_earlier_clause() -> None:
    rows = parse_clause(
        HCM,
        61,
        "Sắp xếp phần còn lại của Phường 15 (quận Tân Bình) sau khi sắp xếp theo quy định tại "
        "khoản 60 Điều này thành phường mới có tên gọi là phường Tân Sơn.",
    )
    assert units(rows) == [("phuong", "15", "quận Tân Bình", "rest")]
    assert rows[0].rest_after_clauses == "60"


def test_nhap_and_mixed_unit_types() -> None:
    rows = parse_clause(
        HCM,
        122,
        "Nhập toàn bộ diện tích tự nhiên, quy mô dân số của xã Long Hòa (huyện Cần Giờ) và "
        "thị trấn Cần Thạnh thành xã mới có tên gọi là xã Cần Giờ.",
    )
    assert units(rows) == [
        ("xa", "Long Hòa", "huyện Cần Giờ", "full"),
        ("thi_tran", "Cần Thạnh", "", "full"),
    ]


def test_district_becomes_a_special_zone() -> None:
    rows = parse_clause(
        HCM,
        163,
        "Sắp xếp toàn bộ diện tích tự nhiên, quy mô dân số của huyện Côn Đảo thành đặc khu "
        "có tên gọi là đặc khu Côn Đảo.",
    )
    assert [(r.new_type, r.new_name) for r in rows] == [("dac_khu", "Côn Đảo")]
    assert units(rows) == [("huyen", "Côn Đảo", "", "full")]


def test_missing_comma_and_type_carried_over_a_list() -> None:
    rows = parse_clause(
        NB,
        1,
        "Sắp xếp toàn bộ diện tích tự nhiên quy mô dân số của các xã Bình Nghĩa, Tràng An và "
        "Đồng Du thành xã mới có tên gọi là xã Bình Lục.",
    )
    assert units(rows) == [
        ("xa", "Bình Nghĩa", "", "full"),
        ("xa", "Tràng An", "", "full"),
        ("xa", "Đồng Du", "", "full"),
    ]
