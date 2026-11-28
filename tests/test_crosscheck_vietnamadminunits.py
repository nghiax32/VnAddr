"""Tests for the comparison with vietnamadminunits (pipeline.crosscheck_vietnamadminunits).

Rows marked "ours" are verbatim from data/interim/parsed/ (ward_new.csv, entity_changes.csv,
crosswalk.csv); rows marked "theirs" are verbatim from vietnamadminunits 1.0.4 (dataset.db and
converter_2025.json). Only the columns the comparison reads are kept."""

from pipeline.crosscheck_vietnamadminunits import (
    SPELLING,
    compare_mapping,
    compare_new,
    compare_old,
    their_mapping,
)

# ours
TRANG_BOM = {"code": "26248", "name": "Trảng Bom", "type": "phuong", "province_code": "75"}
CU_MGAR = {"code": "24280", "name": "Cư M\u2019gar", "type": "xa", "province_code": "66"}
DAO_THANH = {"code": "28249", "name": "Đạo Thạnh", "type": "phuong", "province_code": "82"}
CAO_LANH = {"code": "29869", "name": "Cao Lãnh", "type": "phuong", "province_code": "82"}
TRANG_BOM_CHANGE = {
    "level": "commune",
    "code": "26248",
    "effective": "2026-04-30",
    "old_type": "xa",
    "new_type": "phuong",
    "source_doc": "237/NQ-UBTVQH16",
    "source_clause": "Điều 1, khoản 1, điểm a",
}


def crosswalk(
    province: str, new_code: str, old_code: str, old_name: str, district: str, old_province: str
) -> dict[str, str]:
    return {
        "new_province_code": province,
        "new_ward_code": new_code,
        "old_ward_code": old_code,
        "old_ward_name": old_name,
        "old_district_name": district,
        "old_province_code": old_province,
        "correction": "",
    }


DAK_HA = crosswalk("51", "23500", "23500", "Thị trấn Đăk Hà", "Huyện Đắk Hà", "62")
PHUONG_IV = crosswalk("80", "25459", "25462", "Phường IV", "Thành phố Tây Ninh", "72")
PHUONG_4_MY_THO = crosswalk("82", "28249", "28252", "Phường 4", "Thành phố Mỹ Tho", "82")


# theirs
def new(
    code: str, name: str, kind: str, province: str, key: str = "", ward_key: str = ""
) -> dict[str, str]:
    return {
        "wardCode": code,
        "wardShort": name,
        "wardType": kind,
        "provinceCode": province,
        "provinceKey": key,
        "wardKey": ward_key,
    }


def legacy(
    code: str, name: str, district: str, province: str, keys: tuple[str, str, str]
) -> dict[str, str]:
    return {
        "wardCode": code,
        "ward": name,
        "district": district,
        "provinceCode": province,
        "provinceKey": keys[0],
        "districtKey": keys[1],
        "wardKey": keys[2],
    }


def test_a_type_changed_after_2025_is_noted_with_its_document() -> None:
    theirs = [new("26248", "Trảng Bom", "Xã", "75"), new("24280", "Cư M'gar", "Xã", "66")]
    [found] = compare_new([TRANG_BOM, CU_MGAR], theirs, [TRANG_BOM_CHANGE])
    assert (found["field"], found["ours"], found["theirs"]) == ("type", "phuong", "xa")
    assert found["note"] == "237/NQ-UBTVQH16, Điều 1, khoản 1, điểm a, from 2026-04-30"


def test_old_units_differing_in_spelling_are_noted() -> None:
    theirs = [
        legacy("23500", "Thị trấn Đăk Hà", "Huyện Đăk Hà", "62", ("", "", "")),
        legacy("25462", "Phường 4", "Thành phố Tây Ninh", "72", ("", "", "")),
    ]
    district, name = compare_old([DAK_HA, PHUONG_IV], theirs)
    assert (district["field"], district["note"]) == ("district", SPELLING)
    assert (name["field"], name["ours"], name["theirs"], name["note"]) == (
        "name",
        "Phường IV",
        "Phường 4",
        "",
    )


def test_their_name_keys_are_turned_into_codes() -> None:
    converter = {
        "DICT_PROVINCE_WARD_NO_DIVIDED": {},
        "DICT_PROVINCE_WARD_DIVIDED": {
            "tinhdongthap": {
                "tinhtiengiang_thanhphomytho_phuong4": [
                    {"newWardKey": "phuongcaolanh", "isDefaultNewWard": False},
                    {"newWardKey": "phuongdaothanh", "isDefaultNewWard": True},
                ]
            }
        },
    }
    theirs_new = [
        new("28249", "Đạo Thạnh", "Phường", "82", "tinhdongthap", "phuongdaothanh"),
        new("29869", "Cao Lãnh", "Phường", "82", "tinhdongthap", "phuongcaolanh"),
    ]
    theirs_old = [
        legacy(
            "28252",
            "Phường 4",
            "Thành phố Mỹ Tho",
            "82",
            ("tinhtiengiang", "thanhphomytho", "phuong4"),
        )
    ]
    mapping = their_mapping(converter, theirs_new, theirs_old)  # type: ignore[arg-type]
    assert mapping == {"28252": {"28249", "29869"}}
    [found] = compare_mapping([PHUONG_4_MY_THO], [DAO_THANH, CAO_LANH], mapping)
    assert found["ours"] == "Đạo Thạnh (28249)"
    assert found["theirs"] == "Đạo Thạnh (28249); Cao Lãnh (29869)"
