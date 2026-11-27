"""Rules for reading the OCR'd appendix of Resolution 63/2021/NQ-HĐND (Nam Định). The inputs
are the OCR output and page text of rows checked against the page images."""

from pipeline.parse_village_tables import PARTIAL, fix_numbers, old_units, split_type


def test_an_le_row() -> None:
    assert old_units("Sáp nhập thôn An Lễ với thôn Trung Nghĩa") == [
        ("thôn", "An Lễ"),
        ("thôn", "Trung Nghĩa"),
    ]
    assert split_type("Thôn Nhất Giáp") == ("thôn", "Nhất Giáp")


def test_comma_between_types_qualifies_a_unit() -> None:
    assert old_units("Sáp nhập xóm Trung, thôn Đại Đê với xóm Thượng, thôn Đại Đê") == [
        ("xóm", "Trung, thôn Đại Đê"),
        ("xóm", "Thượng, thôn Đại Đê"),
    ]


def test_comma_list_without_type_inherits_it() -> None:
    assert old_units("Sáp nhập thôn Ngọc Minh với thôn Thượng Đồng, Phú Thọ và Thanh Trung") == [
        ("thôn", "Ngọc Minh"),
        ("thôn", "Thượng Đồng"),
        ("thôn", "Phú Thọ"),
        ("thôn", "Thanh Trung"),
    ]


def test_ocr_digit_lookalikes_are_repaired() -> None:
    assert old_units("Sáp nhập TDP 15 với TDP 1ó, TDP 17, TDP.18") == [
        ("TDP", "15"),
        ("TDP", "16"),
        ("TDP", "17"),
        ("TDP", "18"),
    ]
    assert old_units("Sáp nhập xóm ] với xóm 2") == [("xóm", "1"), ("xóm", "2")]
    assert split_type("TDP số I") == ("TDP", "số 1")


def test_roman_numerals_inside_names_are_kept() -> None:
    assert fix_numbers("Thanh Thủy II") == "Thanh Thủy II"
    assert fix_numbers("I1") == "11"


def test_part_of_a_village_is_recognised() -> None:
    names = [
        name
        for _, name in old_units(
            "Sáp nhập xóm 2 Phú lễ với xóm 3 Phú Lễ với 16 hộ gia đình thuộc xóm 1 Phú Lễ"
        )
    ]
    assert [bool(PARTIAL.search(n)) for n in names] == [False, False, True]
