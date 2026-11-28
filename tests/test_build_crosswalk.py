"""Tests for the field corrections applied to the Cục Thống kê conversion table
(pipeline.build_crosswalk.correct), using pipeline/crosswalk_corrections.csv.

The rows are those of the table as published, before correction: the corrected rows, Phường 5
of thành phố Mỹ Tho, which keeps the province code 82 that one correction replaces, and the
communes whose code the table also gives to a corrected row (Hồng Quang, Công Đa, Cổ Bi)."""

import copy
import csv
import io

from pipeline.build_crosswalk import correct

PUBLISHED = """\
new_province_code,new_province_name,new_ward_code,new_ward_name,old_ward_code,old_ward_name,\
old_district_code,old_district_name,old_province_code,old_province_name,share,note,correction
37,Tỉnh Ninh Bình,13363,Phường Tiên Sơn,13369,Phường Tiên Sơn,349,Thị xã Duy Tiên,35,\
Tỉnh Hà Nam,full,Nhập toàn bộ,
80,Tỉnh Tây Ninh,27694,Phường Long An,27691,Phường 4,794,Thành phố Tân An,82,Tỉnh Tiền Giang,\
full,Nhập toàn bộ,
91,Tỉnh An Giang,30781,Xã Tiên Hải,30781,Xã Tiên Hải,900,Thành phố Hà Tiên,89,Tỉnh An Giang,\
unchanged,Giữ nguyên,
66,Tỉnh Đắk Lắk,24496,Xa Ea Kly,24493,Xã Krông Búk,654,Huyện Krông Pắc,66,Tỉnh Đắk Lắk,full,\
Nhập toàn bộ,
66,Tỉnh Đắk Lắk,24496,Xa Ea Kly,24496,Xã Ea Kly,654,Huyện Krông Pắc,66,Tỉnh Đắk Lắk,full,\
Nhập toàn bộ,
82,Tỉnh Đồng Tháp,28249,Phường Đạo Thạnh,28249,Phường 5,815,Thành phố Mỹ Tho,82,\
Tỉnh Tiền Giang,full,Nhập toàn bộ,
01,Thành phố Hà Nội,00136,Phường Phúc Lợi,00553,Xã Cổ Bi,018,Huyện Gia Lâm,01,Thành phố Hà Nội,\
part,Nhập một phần,
01,Thành phố Hà Nội,00562,Xã Thuận An,00553,Xã Đặng Xá,018,Huyện Gia Lâm,01,Thành phố Hà Nội,\
part,"Nhập một phần diện tích, toàn bộ dân số",
04,Tỉnh Cao Bằng,01636,Xã Bế Văn Đàn,01615,Xã Hồng Quang,049,Huyện Quảng Hòa,04,Tỉnh Cao Bằng,\
full,Nhập toàn bộ,
04,Tỉnh Cao Bằng,01648,Xã Phục Hòa,01615,Xã Mỹ Hưng,049,Huyện Quảng Hòa,04,Tỉnh Cao Bằng,\
full,Nhập toàn bộ,
08,Tỉnh Tuyên Quang,02458,Xã Trung Sơn,02485,Xã Công Đa,075,Huyện Yên Sơn,08,Tỉnh Tuyên Quang,\
full,Nhập toàn bộ,
08,Tỉnh Tuyên Quang,02494,Xã Thái Bình,02485,Xã Phú Thịnh,075,Huyện Yên Sơn,08,Tỉnh Tuyên Quang,\
full,Nhập toàn bộ,
"""


def published() -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(PUBLISHED)))


def by_code(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {r["old_ward_code"]: r for r in rows}


def test_corrections_apply_to_the_wrong_values() -> None:
    rows = published()
    assert correct(rows) == []
    row = by_code(rows)
    assert row["13369"]["old_ward_name"] == "Xã Tiên Sơn"
    assert (row["27691"]["old_province_code"], row["27691"]["old_province_name"]) == (
        "80",
        "Tỉnh Long An",
    )
    assert (row["30781"]["old_province_code"], row["30781"]["old_province_name"]) == (
        "91",
        "Tỉnh Kiên Giang",
    )
    assert row["24493"]["new_ward_name"] == row["24496"]["new_ward_name"] == "Xã Ea Kly"
    # Each corrected row names the field, both values and the source document.
    assert row["13369"]["correction"] == (
        "old_ward_name: Phường Tiên Sơn -> Xã Tiên Sơn (1674/NQ-UBTVQH15, Điều 1, khoản 102; "
        "829/NQ-UBTVQH14, Điều 1, khoản 4)"
    )
    assert row["27691"]["correction"].count("1682/NQ-UBTVQH15") == 2
    # A correction is tied to its ward code: another row with province code 82 is left as it is.
    assert row["28249"] == by_code(published())["28249"]
    # Where one code is given to two communes, only the named commune's row gets its own code.
    assert (row["01615"]["old_ward_name"], row["01651"]["old_ward_name"]) == (
        "Xã Hồng Quang",
        "Xã Mỹ Hưng",
    )
    assert (row["02485"]["old_ward_name"], row["02482"]["old_ward_name"]) == (
        "Xã Công Đa",
        "Xã Phú Thịnh",
    )
    assert [r["old_ward_name"] for r in rows if r["old_ward_code"] == "00553"] == ["Xã Cổ Bi"]
    assert [r["old_ward_name"] for r in rows if r["old_ward_code"] == "00556"] == ["Xã Đặng Xá"]


def test_a_value_already_changed_is_reported_and_left_alone() -> None:
    rows = published()
    correct(rows)
    again = copy.deepcopy(rows)
    # Once the wrong values are gone, every correction is reported as not applied and the rows,
    # including the correction column, stay as they are.
    missed = correct(again)
    assert again == rows
    assert len(missed) == 10
    assert "13369 old_ward_name: 'Phường Tiên Sơn' not in the table" in missed
