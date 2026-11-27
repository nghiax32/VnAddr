"""Parser tests for the 2019-2021 and 2023-2025 rearrangement resolutions, on text copied from
the Official Gazette (Công báo) copies of Resolutions 861/NQ-UBTVQH14 (Ninh Bình),
829/NQ-UBTVQH14 (Hà Nam), 1104/NQ-UBTVQH15 (Nam Định) and 1288/NQ-UBTVQH15 (Hà Nam)."""

from pipeline.parse_resolutions_2024 import parse


def pairs(rows: list) -> list[tuple[str, str, str, str]]:  # type: ignore[type-arg]
    return [(r.district, r.old_name, r.new_name, r.share) for r in rows]


def test_2020_adjustment_and_remainder_are_partial() -> None:
    text = """QUYẾT NGHỊ:
Điều 1. Sắp xếp các đơn vị hành chính cấp xã thuộc tỉnh Ninh Bình
1. Sắp xếp các đơn vị hành chính cấp xã thuộc huyện Kim Sơn như sau:
a) Thành lập xã Xuân Chính trên cơ sở nhập toàn bộ 3,79 km2 diện tích tự
nhiên, 2.623 người của xã Xuân Thiện và toàn bộ 3,16 km2 diện tích tự nhiên,
3.019 người của xã Chính Tâm. Sau khi thành lập, xã Xuân Chính có 6,95 km2
diện tích tự nhiên và quy mô dân số 5.642 người;
b) Điều chỉnh 1,33 km2 diện tích tự nhiên, 1.335 người của xã Yên Mật vào xã
Kim Chính. Sau khi điều chỉnh, xã Kim Chính có 8,56 km2 diện tích tự nhiên và quy
mô dân số 8.698 người.
c) Nhập toàn bộ 0,90 km2 diện tích tự nhiên, 827 người của xã Yên Mật sau
khi điều chỉnh địa giới đơn vị hành chính quy định tại điểm b khoản này vào xã
Như Hòa. Sau khi nhập, xã Như Hòa có 6,09 km2 diện tích tự nhiên và quy mô
dân số 6.164 người.
2. Sau khi sắp xếp, huyện Kim Sơn có 25 đơn vị hành chính cấp xã, gồm 23 xã
và 02 thị trấn.
Điều 2. Hiệu lực thi hành
1. Nghị quyết này có hiệu lực thi hành kể từ ngày 01 tháng 02 năm 2020.
"""
    rows, stated, unread = parse("861/NQ-UBTVQH14", text)
    assert unread == []
    assert stated == {"huyện Kim Sơn": 25}
    assert pairs(rows) == [
        ("huyện Kim Sơn", "Xuân Thiện", "Xuân Chính", "full"),
        ("huyện Kim Sơn", "Chính Tâm", "Xuân Chính", "full"),
        ("huyện Kim Sơn", "Yên Mật", "Kim Chính", "part"),
        ("huyện Kim Sơn", "Kim Chính", "Kim Chính", "absorbing"),
        ("huyện Kim Sơn", "Yên Mật", "Như Hòa", "part"),
        ("huyện Kim Sơn", "Như Hòa", "Như Hòa", "absorbing"),
    ]
    assert {r.effective for r in rows} == {"2020-02-01"}
    assert {r.clause for r in rows if r.new_name == "Như Hòa"} == {"Điều 1, khoản 1, điểm c"}


def test_2024_district_merge_rename_and_shared_toan_bo() -> None:
    text = """QUYẾT NGHỊ:
Điều 1. Sắp xếp các đơn vị hành chính cấp huyện thuộc tỉnh Nam Định
1. Nhập toàn bộ diện tích tự nhiên là 74,49 km2, quy mô dân số là 84.045
người của huyện Mỹ Lộc vào thành phố Nam Định. Sau khi nhập, thành phố Nam
Định có diện tích tự nhiên là 120,90 km2 và quy mô dân số là 364.181 người.
2. Thành lập, sắp xếp các đơn vị hành chính cấp xã thuộc thành phố Nam Định
như sau:
a) Thành lập phường Nam Phong trên cơ sở toàn bộ diện tích tự nhiên là 6,58 km2
và quy mô dân số là 9.160 người của xã Nam Phong.
d) Nhập toàn bộ diện tích tự nhiên là 3,33 km2, quy mô dân số là 7.674 người
của xã Lộc An và toàn bộ diện tích tự nhiên là 0,43 km2, quy mô dân số là 11.967
người của phường Văn Miếu vào phường Trường Thi. Sau khi nhập, phường
Trường Thi có diện tích tự nhiên là 4,44 km2 và quy mô dân số là 37.409 người.
h) Nhập toàn bộ diện tích tự nhiên là 0,36 km2, quy mô dân số là 5.477 người của
phường Ngô Quyền và diện tích tự nhiên là 0,91 km2, quy mô dân số là 12.702 người
của phường Trần Quang Khải vào phường Năng Tĩnh. Sau khi nhập, phường Năng
Tĩnh có diện tích tự nhiên là 2,06 km2 và quy mô dân số là 31.126 người.
Điều 4. Hiệu lực thi hành
1. Nghị quyết này có hiệu lực thi hành từ ngày 01 tháng 9 năm 2024.
"""
    rows, _, unread = parse("1104/NQ-UBTVQH15", text)
    assert unread == []
    got = pairs(rows)
    assert ("", "Mỹ Lộc", "Nam Định", "district_merge") in got
    assert ("thành phố Nam Định", "Nam Phong", "Nam Phong", "renamed") in got
    assert ("thành phố Nam Định", "Lộc An", "Trường Thi", "full") in got
    assert ("thành phố Nam Định", "Văn Miếu", "Trường Thi", "full") in got
    assert ("thành phố Nam Định", "Trường Thi", "Trường Thi", "absorbing") in got
    assert ("thành phố Nam Định", "Ngô Quyền", "Năng Tĩnh", "full") in got
    assert ("thành phố Nam Định", "Trần Quang Khải", "Năng Tĩnh", "full") in got


def test_headings_without_cap_xa_wording() -> None:
    # Lines from 1288/NQ-UBTVQH15 (Kim Bảng) followed by lines from 829/NQ-UBTVQH14 (Duy Tiên),
    # each copied verbatim; only the two headings and one clause of each are kept.
    text = """QUYẾT NGHỊ:
Điều 1. Thành lập thị xã Kim Bảng, tỉnh Hà Nam và thành lập, sắp xếp các
phường thuộc thị xã Kim Bảng
2. Thành lập các phường thuộc thị xã Kim Bảng như sau:
b) Thành lập phường Ba Sao trên cơ sở toàn bộ diện tích tự nhiên là 31,42 km2 và
quy mô dân số là 5.866 người của thị trấn Ba Sao.
3. Sau khi thành lập, thị xã Kim Bảng có 17 đơn vị hành chính cấp xã, gồm 10
phường: Ba Sao, Đại Cương, Đồng Hóa, Lê Hồ, Ngọc Sơn, Quế, Tân Sơn, Tân
Tựu, Thi Sơn, Tượng Lĩnh và 07 xã: Hoàng Tây, Khả Phong, Liên Sơn, Nguyễn
3. Thành lập các phường thuộc thị xã Duy Tiên sau khi điều chỉnh địa giới đơn
vị hành chính quy định tại khoản 1 Điều này như sau:
a) Thành lập phường Bạch Thượng trên cơ sở toàn bộ 6,24 km2 diện tích tự
nhiên và quy mô dân số 11.960 người của xã Bạch Thượng.
Điều 4. Hiệu lực thi hành
"""
    rows, stated, unread = parse("1288/NQ-UBTVQH15", text)
    assert unread == []
    assert stated == {"thị xã Kim Bảng": 17}
    assert [r.old_type for r in rows] == ["thi_tran", "xa"]
    assert pairs(rows) == [
        ("thị xã Kim Bảng", "Ba Sao", "Ba Sao", "renamed"),
        ("thị xã Duy Tiên", "Bạch Thượng", "Bạch Thượng", "renamed"),
    ]


def test_amounts_without_toan_bo_are_parts() -> None:
    # Lines from 818/NQ-UBTVQH14 (Lạng Sơn), Điều 1, khoản 2, copied verbatim; only the
    # heading and point b are kept.
    text = """QUYẾT NGHỊ:
Điều 1. Sắp xếp các đơn vị hành chính cấp xã thuộc tỉnh Lạng Sơn
2. Sắp xếp các đơn vị hành chính cấp xã thuộc huyện Văn Lãng như sau:
b) Thành lập xã Bắc Hùng trên cơ sở 4,67 km2 diện tích tự nhiên, 325 người
của xã Tân Lang, 16,24 km2 diện tích tự nhiên, 1.201 người của xã Trùng Quán,
14,63 km2 diện tích tự nhiên, 714 người của xã Tân Việt và toàn bộ 17,74 km2
diện tích tự nhiên, 951 người của xã An Hùng. Sau khi thành lập, xã Bắc Hùng
có 53,28 km2 diện tích tự nhiên và quy mô dân số 3.191 người.
Điều 4. Hiệu lực thi hành
"""
    rows, _, unread = parse("818/NQ-UBTVQH14", text)
    assert unread == []
    assert pairs(rows) == [
        ("huyện Văn Lãng", "Tân Lang", "Bắc Hùng", "part"),
        ("huyện Văn Lãng", "Trùng Quán", "Bắc Hùng", "part"),
        ("huyện Văn Lãng", "Tân Việt", "Bắc Hùng", "part"),
        ("huyện Văn Lãng", "An Hùng", "Bắc Hùng", "full"),
    ]


def test_two_operations_in_one_sentence() -> None:
    # Lines from 1264/NQ-UBTVQH14 (Thừa Thiên Huế), Điều 1, khoản 4, copied verbatim; the
    # clauses between the article heading and khoản 4 are left out.
    text = """QUYẾT NGHỊ:
Điều 1. Sắp xếp các đơn vị hành chính cấp xã thuộc thành phố Huế, tỉnh
Thừa Thiên Huế
4. Điều chỉnh 0,46 km2 diện tích tự nhiên, dân số 7.548 người của phường
Phú Thuận vào phường Tây Lộc và nhập toàn bộ 0,80 km2 diện tích tự nhiên, dân
số 4.926 người còn lại của phường Phú Thuận vào phường Thuận Hòa. Sau khi
điều chỉnh, phường Tây Lộc có 1,80 km2 diện tích tự nhiên và quy mô dân số
30.781 người; phường Thuận Hòa có 1,84 km2 diện tích tự nhiên và quy mô dân
số 24.358 người.
Điều 4. Hiệu lực thi hành
"""
    rows, _, unread = parse("1264/NQ-UBTVQH14", text)
    assert unread == []
    assert [(r.old_name, r.new_name, r.share) for r in rows] == [
        ("Phú Thuận", "Tây Lộc", "part"),
        ("Tây Lộc", "Tây Lộc", "absorbing"),
        ("Phú Thuận", "Thuận Hòa", "part"),
        ("Thuận Hòa", "Thuận Hòa", "absorbing"),
    ]
