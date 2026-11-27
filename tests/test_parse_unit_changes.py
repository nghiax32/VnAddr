"""Tests for the resolutions that change units after 1 July 2025 (pipeline.parse_unit_changes)
and for applying them to the units of Decision 19/2025 (pipeline.build_entities.apply_changes).

The texts are verbatim from the signed scans as read from the page images: 237/NQ-UBTVQH16
(Đồng Nai), Điều 1 khoản 1 điểm a and b, khoản 2 and Điều 2, with the boundary sentences left
out; 30/2026/QH16, Điều 1 and Điều 2."""

from pipeline.build_entities import apply_changes
from pipeline.parse_unit_changes import correct, parse

TEXT_237 = """Điều 1. Thành lập 10 phường thuộc tỉnh Đồng Nai
1. Thành lập 10 phường thuộc tỉnh Đồng Nai như sau:
a) Thành lập phường Trảng Bom trên cơ sở nguyên trạng diện tích tự
nhiên và quy mô dân số của xã Trảng Bom.
b) Thành lập phường Long Thành trên cơ sở nguyên trạng diện tích tự
nhiên và quy mô dân số của xã Long Thành.
2. Sau khi thành lập các phường, tỉnh Đồng Nai có 95 đơn vị hành chính
cấp xã, gồm 33 phường và 62 xã.
Điều 2. Hiệu lực thi hành
Nghị quyết này có hiệu lực thi hành từ ngày 30 tháng 4 năm 2026.
"""

TEXT_30 = """Điều 1. Thành lập thành phố Đồng Nai
Thành lập thành phố Đồng Nai trên cơ sở toàn bộ diện tích tự nhiên và
quy mô dân số của tỉnh Đồng Nai.
Điều 2. Hiệu lực thi hành
Nghị quyết này có hiệu lực thi hành từ ngày 30 tháng 4 năm 2026.
"""


def test_communes_made_wards_are_read() -> None:
    changes, totals, problems = parse("237/NQ-UBTVQH16", TEXT_237)
    assert problems == []
    assert changes[0] == {
        "source_doc": "237/NQ-UBTVQH16",
        "clause": "Điều 1, khoản 1, điểm a",
        "effective": "2026-04-30",
        "level": "commune",
        "province": "Đồng Nai",
        "old_type": "xã",
        "old_name": "Trảng Bom",
        "new_type": "phường",
        "new_name": "Trảng Bom",
    }
    assert [c["clause"][-1] for c in changes] == ["a", "b"]
    assert totals == [
        {
            "source_doc": "237/NQ-UBTVQH16",
            "effective": "2026-04-30",
            "province": "Đồng Nai",
            "total": "95",
            "phuong": "33",
            "xa": "62",
        }
    ]


def test_a_province_made_a_city_is_read() -> None:
    [change], totals, problems = parse("30/2026/QH16", TEXT_30)
    assert problems == [] and totals == []
    assert (change["level"], change["clause"], change["old_type"], change["new_type"]) == (
        "province",
        "Điều 1",
        "tỉnh",
        "thành phố",
    )
    assert change["new_name"] == "Đồng Nai"


def test_a_misread_clause_letter_is_reported() -> None:
    # The OCR read the letter of điểm g as "ø"; a letter misread that way is reported.
    text = TEXT_237.replace("b) Thành lập", "ø) Thành lập")
    changes, _, problems = parse("237/NQ-UBTVQH16", text)
    assert len(changes) == 2
    assert problems == ["237/NQ-UBTVQH16: clause letters out of order: a ø"]


def test_an_image_reading_replaces_the_ocr_text_once() -> None:
    pages = ["quy mô dân số của xã Bế Hạ."]
    reading = {"doc_id": "388/NQ-UBTVQH16", "page": "1", "ocr": "của xã Bế Hạ.", "image": ""}
    reading["image"] = "của xã Bố Hạ."
    assert correct("388/NQ-UBTVQH16", pages, [reading]) == []
    assert pages == ["quy mô dân số của xã Bố Hạ."]
    # Once the OCR text is gone the reading is reported, not applied again.
    assert correct("388/NQ-UBTVQH16", pages, [reading]) == [
        "388/NQ-UBTVQH16 page 1: 'của xã Bế Hạ.' not found once"
    ]


def test_changes_keep_the_code_and_are_recorded() -> None:
    # Units as Decision 19/2025 lists them (Phụ lục I, row 27; Phụ lục II, tỉnh Đồng Nai).
    provinces = [{"code": "75", "name": "Đồng Nai", "type": "tinh"}]
    wards = [
        {"code": "26248", "name": "Trảng Bom", "type": "xa", "province_code": "75"},
        {"code": "26368", "name": "Long Thành", "type": "xa", "province_code": "75"},
    ]
    changes = parse("237/NQ-UBTVQH16", TEXT_237)[0] + parse("30/2026/QH16", TEXT_30)[0]
    applied, problems = apply_changes(provinces, wards, changes, [])
    assert problems == []
    assert provinces == [{"code": "75", "name": "Đồng Nai", "type": "thanh_pho"}]
    assert [w["type"] for w in wards] == ["phuong", "phuong"]
    assert applied[0] == {
        "level": "commune",
        "code": "26248",
        "effective": "2026-04-30",
        "old_type": "xa",
        "old_name": "Trảng Bom",
        "new_type": "phuong",
        "new_name": "Trảng Bom",
        "source_doc": "237/NQ-UBTVQH16",
        "source_clause": "Điều 1, khoản 1, điểm a",
    }
    # Applied again, the communes are already wards: nothing matches, and that is reported.
    _, again = apply_changes(provinces, wards, changes, [])
    assert (
        "237/NQ-UBTVQH16 Điều 1, khoản 1, điểm a: xã Trảng Bom (Đồng Nai) matches 0 units" in again
    )
