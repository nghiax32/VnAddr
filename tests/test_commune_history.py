"""Tests for following communes through the rounds (pipeline.commune_history), on rows parsed
from the Official Gazette (Công báo) text of 838/NQ-UBTVQH14 (Đồng Tháp), line breaks kept and
page markers left out."""

from pipeline.commune_history import apply, district_key
from pipeline.parse_resolutions_2024 import parse

# 838/NQ-UBTVQH14, Điều 1; the boundary sentence ("Xã Thường Lạc giáp ...") is left out.
TEXT_838 = """QUYẾT NGHỊ:
Điều 1. Sắp xếp các đơn vị hành chính cấp xã thuộc tỉnh Đồng Tháp
1. Nhập toàn bộ 14,40 km2 diện tích tự nhiên và 7.898 người của xã Thường
Thới Hậu B vào xã Thường Lạc. Sau khi nhập, xã Thường Lạc có 22,88 km2 diện
tích tự nhiên và quy mô dân số 11.131 người.
2. Sau khi sắp xếp, huyện Hồng Ngự có 10 đơn vị hành chính cấp xã, gồm 09
xã và 01 thị trấn.
Điều 2. Hiệu lực thi hành
1. Nghị quyết này có hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2020.
"""


def test_district_key_keeps_the_type() -> None:
    assert district_key("Huyện Hồng Ngự") == "huyện hồng ngự"
    assert district_key("Thành phố Hồng Ngự") == "thành phố hồng ngự"
    assert district_key("huyện Yên Định, tỉnh Thanh Hóa") == "huyện yên định"


def test_a_change_applies_to_its_own_district_only() -> None:
    rows, _, _ = parse("838/NQ-UBTVQH14", TEXT_838)
    # Xã Thường Thới Hậu B of huyện Hồng Ngự goes into xã Thường Lạc.
    [(district, commune, step)] = apply(rows, "huyện hồng ngự", "xa thường thới hậu b")
    assert (district, commune, step["share"]) == ("huyện hồng ngự", "xa thường lạc", "full")
    # A commune of that name in thành phố Hồng Ngự, another district, stays as it is.
    assert apply(rows, "thành phố hồng ngự", "xa thường thới hậu b") == [
        ("thành phố hồng ngự", "xa thường thới hậu b", {})
    ]
