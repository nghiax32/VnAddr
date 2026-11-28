"""Tests for the cross-table checks (pipeline.validate).

The rows are verbatim from data/interim/parsed/crosswalk.csv and ward_new.csv (the Statistics
Office conversion table and Decision 19/2025) and data/reports/crosscheck_crosswalk.csv; only
the columns the checks read are kept."""

from pipeline.validate import check_new_communes, check_old_communes, check_totals, mark


def cw(
    province: str, new_code: str, new_name: str, old_code: str, old_name: str, share: str
) -> dict[str, str]:
    return {
        "new_province_code": province,
        "new_ward_code": new_code,
        "new_ward_name": new_name,
        "old_ward_code": old_code,
        "old_ward_name": old_name,
        "share": share,
    }


TRUC_BACH = cw("01", "00004", "Phường Ba Đình", "00004", "Phường Trúc Bạch", "full")
DANG_XA = cw("01", "00541", "Xã Phù Đổng", "00556", "Xã Đặng Xá", "part")
HONG_QUANG = cw("04", "01636", "Xã Bế Văn Đàn", "01615", "Xã Hồng Quang", "full")
MY_HUNG = cw("04", "01648", "Xã Phục Hòa", "01615", "Xã Mỹ Hưng", "full")
KY_LOI = [
    cw("42", "18754", "Phường Sông Trí", "18796", "Xã Kỳ Lợi", "part"),
    cw("42", "18823", "Phường Vũng Áng", "18796", "Xã Kỳ Lợi", "full"),
    cw("42", "18832", "Phường Hoành Sơn", "18796", "Xã Kỳ Lợi", "part"),
]
BA_DINH = {"code": "00004", "name": "Ba Đình", "type": "phuong", "province_code": "01"}
BACH_LONG_VI = {"code": "11948", "name": "Bạch Long Vĩ", "type": "dac_khu", "province_code": "31"}


def test_an_old_commune_moved_whole_once_is_fine() -> None:
    assert check_old_communes([TRUC_BACH]) == []


def test_one_old_code_for_two_communes_is_found() -> None:
    [found] = check_old_communes([HONG_QUANG, MY_HUNG])
    assert found["item"] == "01615 Xã Hồng Quang / Xã Mỹ Hưng"
    assert found["detail"].startswith("one code for 2 communes")


def test_a_split_with_one_part_is_found() -> None:
    [found] = check_old_communes([DANG_XA])
    assert found["detail"] == "split, but only one part is listed: Xã Phù Đổng (part)"


def test_a_commune_moved_whole_and_split_is_found() -> None:
    [found] = check_old_communes(KY_LOI)
    assert found["detail"].startswith("moved whole and also elsewhere")


def test_a_new_commune_without_a_crosswalk_row_is_found() -> None:
    [found] = check_new_communes([BA_DINH, BACH_LONG_VI], [TRUC_BACH])
    assert (found["province"], found["item"]) == ("31", "Bạch Long Vĩ")


def test_totals_are_compared_with_the_resolution() -> None:
    assert check_totals([BA_DINH], {"01": 1}) == []
    [found] = check_totals([BA_DINH], {"01": 126})
    assert found["detail"] == "1 communes, resolution states 126"


def test_problems_listed_by_the_crosscheck_are_recorded() -> None:
    crosscheck = [
        {"province": "42", "new": "Vũng Áng"},
        {"province": "31", "new": "Bạch Long Vĩ"},
    ]
    found = check_old_communes([*KY_LOI, HONG_QUANG, MY_HUNG])
    found += check_new_communes([BACH_LONG_VI], [])
    mark(found, [*KY_LOI, HONG_QUANG, MY_HUNG], crosscheck)
    assert [p["status"] for p in found] == ["open", "recorded", "recorded"]
