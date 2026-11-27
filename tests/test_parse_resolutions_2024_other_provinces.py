"""Parser tests for wordings met in the 2019-2021 and 2023-2025 resolutions of the other
provinces. Each text is copied verbatim from the Official Gazette (Công báo) copy of the
resolution named in the test, line breaks kept and page markers ("[page 2]") left out, as
pipeline.parse_resolutions_2024.main passes it to parse(). Where lines in between are left out,
the test says so."""

from pipeline.parse_resolutions_2024 import Row, parse


def moves(rows: list[Row]) -> list[tuple[str, str, str, str, str]]:
    return [(r.old_district, r.district, r.old_name, r.new_name, r.share) for r in rows]


def test_group_heading_ending_with_a_colon() -> None:
    # 768/NQ-UBTVQH14 (Hải Dương), Điều 1, khoản 1 and khoản 2, điểm a-b; the boundary
    # descriptions after điểm a ("Địa giới hành chính phường An Lưu: ...") are left out.
    text = """QUYẾT NGHỊ:
Điều 1. Thành lập thị xã Kinh Môn và các phường, xã thuộc thị xã
Kinh Môn, tỉnh Hải Dương
1. Thành lập thị xã Kinh Môn trên cơ sở toàn bộ 165,33 km2 diện tích tự nhiên
và quy mô dân số 203.638 người của huyện Kinh Môn, tỉnh Hải Dương.
2. Thành lập 14 phường, 01 xã thuộc thị xã Kinh Môn:
a) Thành lập phường An Lưu trên cơ sở toàn bộ 3,72 km2 diện tích tự nhiên và
quy mô dân số 11.726 người của thị trấn Kinh Môn.
b) Thành lập phường An Phụ trên cơ sở toàn bộ 8,11 km2 diện tích tự nhiên và
quy mô dân số 9.455 người của xã An Phụ.
"""
    rows, _, unread = parse("768/NQ-UBTVQH14", text)
    assert unread == []
    assert [(r.district, r.old_name, r.new_name, r.share) for r in rows] == [
        ("thị xã Kinh Môn", "Kinh Môn", "Kinh Môn", "district_merge"),
        ("thị xã Kinh Môn", "Kinh Môn", "An Lưu", "renamed"),
        ("thị xã Kinh Môn", "An Phụ", "An Phụ", "renamed"),
    ]


def test_heading_with_the_province_and_an_article_title() -> None:
    # 1191/NQ-UBTVQH14 (Bắc Ninh), Điều 1, khoản 1, điểm a-b; the boundary sentences
    # ("Phường Hương Mạc giáp ...") are left out.
    text = """QUYẾT NGHỊ:
Điều 1. Thành lập các phường thuộc thị xã Từ Sơn, tỉnh Bắc Ninh
1. Thành lập các phường thuộc thị xã Từ Sơn, tỉnh Bắc Ninh:
a) Thành lập phường Hương Mạc trên cơ sở toàn bộ 5,58 km2 diện tích tự
nhiên và quy mô dân số 19.576 người của xã Hương Mạc.
b) Thành lập phường Phù Chẩn trên cơ sở toàn bộ 5,98 km² diện tích tự nhiên
và quy mô dân số 19.656 người của xã Phù Chẩn.
"""
    rows, _, _ = parse("1191/NQ-UBTVQH14", text)
    assert [(r.district, r.old_name, r.share) for r in rows] == [
        ("thị xã Từ Sơn", "Hương Mạc", "renamed"),
        ("thị xã Từ Sơn", "Phù Chẩn", "renamed"),
    ]


def test_article_title_naming_several_districts_names_none() -> None:
    # 1107/NQ-UBTVQH14 (An Giang), Điều 1 and khoản 1-2; the boundary sentences ("Thị trấn
    # Vĩnh Thạnh Trung giáp ...") are left out.
    text = """QUYẾT NGHỊ:
Điều 1. Thành lập thị trấn Vĩnh Thạnh Trung thuộc huyện Châu Phú, thị
trấn Cô Tô thuộc huyện Tri Tôn và thị trấn Vĩnh Bình thuộc huyện Châu
Thành, tỉnh An Giang
1. Thành lập thị trấn Vĩnh Thạnh Trung trên cơ sở toàn bộ 28,43 km2 diện tích
tự nhiên và quy mô dân số 29.528 người của xã Vĩnh Thạnh Trung thuộc huyện
Châu Phú, tỉnh An Giang.
2. Thành lập thị trấn Cô Tô trên cơ sở toàn bộ 42,45 km2 diện tích tự nhiên và
quy mô dân số 9.567 người của xã Cô Tô thuộc huyện Tri Tôn, tỉnh An Giang.
"""
    rows, _, _ = parse("1107/NQ-UBTVQH14", text)
    assert [(r.district, r.old_district, r.old_name, r.share) for r in rows] == [
        ("", "huyện Châu Phú", "Vĩnh Thạnh Trung", "renamed"),
        ("", "huyện Tri Tôn", "Cô Tô", "renamed"),
    ]


def test_article_title_repeating_its_clauses_is_not_parsed() -> None:
    # 939/NQ-UBTVQH15 (Thanh Hóa), Điều 1, khoản 1-3, điểm a; the boundary sentences
    # ("Thị trấn Thiệu Hóa giáp ...") are left out.
    text = """QUYẾT NGHỊ:
Điều 1. Nhập xã Thiệu Phú vào thị trấn Thiệu Hóa và thành lập thị trấn
Hậu Hiền thuộc huyện Thiệu Hóa, tỉnh Thanh Hóa
1. Nhập xã Thiệu Phú với toàn bộ diện tích tự nhiên là 6,53 km2 và quy mô dân
số là 9.175 người vào thị trấn Thiệu Hóa. Sau khi nhập, thị trấn Thiệu Hóa có
diện tích tự nhiên là 17,21 km2 và quy mô dân số là 28.352 người.
2. Thành lập thị trấn Hậu Hiền trên cơ sở toàn bộ diện tích tự nhiên là 10,41 km2
và quy mô dân số là 12.061 người của xã Minh Tâm.
3. Sau khi nhập xã Thiệu Phú vào thị trấn Thiệu Hóa và thành lập thị trấn
Hậu Hiền:
a) Huyện Thiệu Hóa có 24 đơn vị hành chính cấp xã, gồm 22 xã và 02 thị trấn;
"""
    rows, _, _ = parse("939/NQ-UBTVQH15", text)
    assert [(r.district, r.old_name, r.new_name, r.share) for r in rows] == [
        ("huyện Thiệu Hóa", "Thiệu Phú", "Thiệu Hóa", "full"),
        ("huyện Thiệu Hóa", "Thiệu Hóa", "Thiệu Hóa", "absorbing"),
        ("huyện Thiệu Hóa", "Minh Tâm", "Hậu Hiền", "renamed"),
    ]


def test_district_taken_from_the_only_summary_of_the_article() -> None:
    # 838/NQ-UBTVQH14 (Đồng Tháp), Điều 1; the boundary sentence ("Xã Thường Lạc giáp ...")
    # is left out.
    text = """QUYẾT NGHỊ:
Điều 1. Sắp xếp các đơn vị hành chính cấp xã thuộc tỉnh Đồng Tháp
1. Nhập toàn bộ 14,40 km2 diện tích tự nhiên và 7.898 người của xã Thường
Thới Hậu B vào xã Thường Lạc. Sau khi nhập, xã Thường Lạc có 22,88 km2 diện
tích tự nhiên và quy mô dân số 11.131 người.
2. Sau khi sắp xếp, huyện Hồng Ngự có 10 đơn vị hành chính cấp xã, gồm 09
xã và 01 thị trấn.
Điều 2. Hiệu lực thi hành
1. Nghị quyết này có hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2020.
"""
    rows, stated, _ = parse("838/NQ-UBTVQH14", text)
    assert stated == {"huyện Hồng Ngự": 10}
    assert [(r.district, r.old_name, r.new_name, r.share) for r in rows] == [
        ("huyện Hồng Ngự", "Thường Thới Hậu B", "Thường Lạc", "full"),
        ("huyện Hồng Ngự", "Thường Lạc", "Thường Lạc", "absorbing"),
    ]


def test_district_formed_from_listed_communes() -> None:
    # 1191/NQ-UBTVQH15 (Bắc Giang), Điều 2, khoản 2, 3 and khoản 4, điểm a; the boundary
    # sentences ("Xã Biên Sơn giáp ...", "Phường Chũ giáp ...") are left out.
    text = """QUYẾT NGHỊ:
Điều 2. Sắp xếp huyện Lục Ngạn, huyện Sơn Động và các đơn vị hành
chính cấp xã trực thuộc; thành lập thị xã Chũ thuộc tỉnh Bắc Giang và các
phường trực thuộc
2. Điều chỉnh một phần diện tích tự nhiên là 11,98 km2, quy mô dân số là 520 người
của xã Thanh Hải để nhập vào xã Biên Sơn, huyện Lục Ngạn. Sau khi điều chỉnh,
xã Biên Sơn có diện tích tự nhiên là 32,65 km2 và quy mô dân số là 9.737 người;
xã Thanh Hải có diện tích tự nhiên là 17,09 km2 và quy mô dân số là 17.413 người.
3. Thành lập thị xã Chũ trên cơ sở diện tích tự nhiên là 251,55 km2 và quy mô
dân số là 127.881 người của10 đơn vị hành chính cấp xã thuộc huyện Lục Ngạn,
gồm thị trấn Chũ và các xã: Hồng Giang, Kiên Lao, Kiên Thành, Mỹ An, Nam
Dương, Quý Sơn, Phượng Sơn, Thanh Hải, Trù Hựu.
4. Thành lập các phường thuộc thị xã Chũ như sau:
a) Thành lập phường Chũ trên cơ sở toàn bộ diện tích tự nhiên là 12,84 km2 và
quy mô dân số là 17.059 người của thị trấn Chũ.
"""
    rows, _, _ = parse("1191/NQ-UBTVQH15", text)
    by_name = {(r.old_name, r.new_name): r for r in rows}
    # Part of Thanh Hải stays in huyện Lục Ngạn, inside xã Biên Sơn.
    assert by_name[("Thanh Hải", "Biên Sơn")].district == "huyện Lục Ngạn"
    assert by_name[("Thanh Hải", "Biên Sơn")].old_district == ""
    # Thị trấn Chũ leaves huyện Lục Ngạn as phường Chũ of thị xã Chũ.
    assert moves([by_name[("Chũ", "Chũ")]]) == [
        ("huyện Lục Ngạn", "thị xã Chũ", "Chũ", "Chũ", "renamed")
    ]
    # Listed communes with no clause of their own move unchanged.
    assert [
        (r.old_district, r.district, r.old_type, r.old_name) for r in rows if r.share == "moved"
    ] == [
        ("huyện Lục Ngạn", "thị xã Chũ", "xa", name)
        for name in (
            "Hồng Giang",
            "Kiên Lao",
            "Kiên Thành",
            "Mỹ An",
            "Nam Dương",
            "Quý Sơn",
            "Phượng Sơn",
            "Thanh Hải",
            "Trù Hựu",
        )
    ]


def test_communes_moved_by_name_to_another_district() -> None:
    # 1283/NQ-UBTVQH15 (Hà Tĩnh), Điều 1, khoản 1, điểm a.
    text = """QUYẾT NGHỊ:
Điều 1. Sắp xếp thành phố Hà Tĩnh, huyện Cẩm Xuyên, huyện Lộc Hà,
huyện Thạch Hà và các đơn vị hành chính cấp xã trực thuộc
1. Sắp xếp thành phố Hà Tĩnh, huyện Cẩm Xuyên, huyện Lộc Hà và huyện
Thạch Hà như sau:
a) Điều chỉnh một phần diện tích tự nhiên là 138,71 km2, quy mô dân số là
81.620 người của huyện Thạch Hà, tương ứng với toàn bộ diện tích tự nhiên và
quy mô dân số của 11 xã, gồm: Đỉnh Bàn, Tân Lâm Hương, Thạch Đài, Thạch
Hải, Thạch Hội, Thạch Khê, Thạch Lạc, Thạch Thắng, Thạch Trị, Thạch Văn và
Tượng Sơn, để nhập vào thành phố Hà Tĩnh;
"""
    rows, _, _ = parse("1283/NQ-UBTVQH15", text)
    moved = [r for r in rows if r.share == "moved"]
    assert {(r.old_district, r.district) for r in moved} == {
        ("huyện Thạch Hà", "thành phố Hà Tĩnh")
    }
    assert [r.old_name for r in moved] == [
        "Đỉnh Bàn",
        "Tân Lâm Hương",
        "Thạch Đài",
        "Thạch Hải",
        "Thạch Hội",
        "Thạch Khê",
        "Thạch Lạc",
        "Thạch Thắng",
        "Thạch Trị",
        "Thạch Văn",
        "Tượng Sơn",
    ]


def test_city_split_by_listing_the_wards_of_each_new_district() -> None:
    # 1314/NQ-UBTVQH15 (Huế), Điều 1, khoản 1, điểm a and khoản 2, điểm a: the heading of
    # khoản 1, its điểm a and khoản 2 with its điểm a; the boundary sentences and điểm b-đ of
    # khoản 1 are left out.
    text = """QUYẾT NGHỊ:
Điều 1. Thành lập các quận thuộc thành phố Huế
1. Sắp xếp các đơn vị hành chính cấp xã thuộc thành phố Huế, tỉnh Thừa Thiên
Huế để làm cơ sở thành lập các quận thuộc thành phố Huế như sau:
a) Thành lập phường Long Hồ trên cơ sở nhập toàn bộ diện tích tự nhiên là
46,91 km2, quy mô dân số là 5.554 người của xã Hương Thọ và toàn bộ diện tích tự
nhiên là 33,53 km2, quy mô dân số là 10.670 người của phường Hương Hồ. Sau khi
thành lập, phường Long Hồ có diện tích tự nhiên là 80,44 km2 và quy mô dân số là
16.224 người.
2. Thành lập các quận thuộc thành phố Huế như sau:
a) Thành lập quận Phú Xuân trên cơ sở một phần diện tích tự nhiên là 127,05 km2
và quy mô dân số là 203.142 người của thành phố Huế, tỉnh Thừa Thiên Huế.
Quận Phú Xuân có 13 phường, gồm: An Hòa, Đông Ba, Gia Hội, Hương
An, Hương Long, Hương Sơ, Hương Vinh, Kim Long, Long Hồ, Phú Hậu, Tây
Lộc, Thuận Hòa và Thuận Lộc.
"""
    rows, _, _ = parse("1314/NQ-UBTVQH15", text)
    # The ward formed in khoản 1 belongs to the new district.
    assert moves([r for r in rows if r.new_name == "Long Hồ"]) == [
        ("thành phố Huế", "quận Phú Xuân", "Hương Thọ", "Long Hồ", "full"),
        ("thành phố Huế", "quận Phú Xuân", "Hương Hồ", "Long Hồ", "full"),
    ]
    moved = [r for r in rows if r.share == "moved"]
    assert {(r.old_district, r.district, r.old_type) for r in moved} == {
        ("thành phố Huế", "quận Phú Xuân", "phuong")
    }
    assert len(moved) == 12 and "Long Hồ" not in {r.old_name for r in moved}


def test_two_operations_share_the_receiving_commune() -> None:
    # 818/NQ-UBTVQH14 (Lạng Sơn), Điều 1, khoản 8 (heading) and điểm a; the boundary sentence
    # ("Thị trấn Bình Gia giáp ...") is left out.
    text = """QUYẾT NGHỊ:
Điều 1. Sắp xếp các đơn vị hành chính cấp xã thuộc tỉnh Lạng Sơn
8. Sắp xếp các đơn vị hành chính cấp xã thuộc huyện Bình Gia như sau:
a) Nhập toàn bộ 26,42 km2 diện tích tự nhiên, 4.519 người của xã Tô Hiệu và
điều chỉnh 7,77 km2 diện tích tự nhiên, 733 người của xã Hoàng Văn Thụ vào thị
trấn Bình Gia. Sau khi sắp xếp, thị trấn Bình Gia có 37,34 km2 diện tích tự nhiên
và quy mô dân số 8.521 người; xã Hoàng Văn Thụ có 33,10 km2 diện tích tự nhiên
và quy mô dân số 2.516 người.
"""
    rows, _, unread = parse("818/NQ-UBTVQH14", text)
    assert unread == []
    assert [(r.district, r.old_name, r.new_name, r.share) for r in rows] == [
        ("huyện Bình Gia", "Tô Hiệu", "Bình Gia", "full"),
        ("huyện Bình Gia", "Bình Gia", "Bình Gia", "absorbing"),
        ("huyện Bình Gia", "Hoàng Văn Thụ", "Bình Gia", "part"),
    ]


def test_land_of_a_residential_group_moved_between_wards() -> None:
    # 1263/NQ-UBTVQH14 (Hà Nội), Điều 1, khoản 1 up to its first sentence.
    text = """QUYẾT NGHỊ:
Điều 1. Điều chỉnh địa giới đơn vị hành chính giữa các quận Cầu Giấy,
Bắc Từ Liêm và Nam Từ Liêm thuộc thành phố Hà Nội
1. Điều chỉnh 10,32 ha diện tích tự nhiên khu vực 08 tổ dân phố Bắc Nghĩa
Tân do phường Nghĩa Tân, quận Cầu Giấy quản lý hành chính (bao gồm các tổ dân
phố số 25, 26, 27, 28, 29, 30, 31, 32) đang thuộc địa giới hành chính của phường
Cổ Nhuế 1, quận Bắc Từ Liêm vào phường Nghĩa Tân, quận Cầu Giấy. Sau khi
điều chỉnh địa giới hành chính:
"""
    rows, _, unread = parse("1263/NQ-UBTVQH14", text)
    assert unread == []
    assert moves(rows) == [
        ("quận Bắc Từ Liêm", "quận Cầu Giấy", "Cổ Nhuế 1", "Nghĩa Tân", "part"),
        ("quận Cầu Giấy", "quận Cầu Giấy", "Nghĩa Tân", "Nghĩa Tân", "absorbing"),
    ]


def test_communes_moved_whole_to_another_district() -> None:
    # 1264/NQ-UBTVQH14 (Thừa Thiên Huế), Điều 2 and khoản 1 up to its first sentence.
    text = """QUYẾT NGHỊ:
Điều 2. Điều chỉnh địa giới hành chính của thị xã Hương Thủy, thị xã
Hương Trà, huyện Phú Vang và thành phố Huế, tỉnh Thừa Thiên Huế
1. Điều chỉnh toàn bộ 4,92 km2 diện tích tự nhiên, quy mô dân số 7.932 người
của xã Thủy Vân và toàn bộ 22,77 km2 diện tích tự nhiên, quy mô dân số 9.179 người
của xã Thủy Bằng thuộc thị xã Hương Thủy vào thành phố Huế.
"""
    rows, _, unread = parse("1264/NQ-UBTVQH14", text)
    assert unread == []
    assert moves(rows) == [
        ("thị xã Hương Thủy", "thành phố Huế", "Thủy Vân", "Thủy Vân", "moved"),
        ("thị xã Hương Thủy", "thành phố Huế", "Thủy Bằng", "Thủy Bằng", "moved"),
    ]


def test_communes_merged_with_a_district_into_another() -> None:
    # 1243/NQ-UBTVQH15 (Nghệ An), Điều 1, khoản 1 up to its first sentence.
    text = """QUYẾT NGHỊ:
Điều 1. Sắp xếp thành phố Vinh, thị xã Cửa Lò, huyện Nghi Lộc và các đơn
vị hành chính cấp xã trực thuộc
1. Nhập toàn bộ diện tích tự nhiên là 29,09 km2, quy mô dân số là 77.813
người của thị xã Cửa Lò và toàn bộ diện tích tự nhiên là 6,17 km2, quy mô dân số
là 11.884 người của xã Nghi Xuân, toàn bộ diện tích tự nhiên là 6,12 km2, quy mô
dân số là 10.409 người của xã Phúc Thọ, toàn bộ diện tích tự nhiên là 9,50 km2,
quy mô dân số là 11.006 người của xã Nghi Thái và toàn bộ diện tích tự nhiên là
10,35 km2, quy mô dân số là 11.831 người của xã Nghi Phong thuộc huyện Nghi
Lộc vào thành phố Vinh.
"""
    rows, _, unread = parse("1243/NQ-UBTVQH15", text)
    assert unread == []
    assert [(r.old_type, r.old_name, r.new_name) for r in rows if r.share == "district_merge"] == [
        ("thị xã", "Cửa Lò", "Vinh"),
        ("thành phố", "Vinh", "Vinh"),
    ]
    assert [(r.old_district, r.district, r.old_name) for r in rows if r.share == "moved"] == [
        ("huyện Nghi Lộc", "thành phố Vinh", name)
        for name in ("Nghi Xuân", "Phúc Thọ", "Nghi Thái", "Nghi Phong")
    ]


def test_operation_written_after_the_heading_of_its_clause() -> None:
    # 870/NQ-UBTVQH14 (Tiền Giang), Điều 1, khoản 1 up to its first sentence and khoản 2.
    text = """QUYẾT NGHỊ:
Điều 1. Sắp xếp các đơn vị hành chính cấp xã thuộc tỉnh Tiền Giang
1. Sắp xếp đơn vị hành chính cấp xã thuộc huyện Tân Phước như sau:
Nhập toàn bộ 37,43 km2 diện tích tự nhiên, 3.384 người của xã Mỹ Phước vào
thị trấn Mỹ Phước. Sau khi nhập, thị trấn Mỹ Phước có 40,28 km2 diện tích tự
nhiên và quy mô dân số 6.678 người.
2. Sau khi sắp xếp, huyện Tân Phước có 12 đơn vị hành chính cấp xã, gồm 11 xã
và 01 thị trấn.
"""
    rows, _, unread = parse("870/NQ-UBTVQH14", text)
    assert unread == []
    assert [
        (r.district, r.old_type, r.old_name, r.new_type, r.new_name, r.share) for r in rows
    ] == [
        ("huyện Tân Phước", "xa", "Mỹ Phước", "thi_tran", "Mỹ Phước", "full"),
        ("huyện Tân Phước", "thi_tran", "Mỹ Phước", "thi_tran", "Mỹ Phước", "absorbing"),
    ]


def test_adjustment_written_with_ve() -> None:
    # 767/NQ-UBTVQH14 (Lào Cai), Điều 1, khoản 3 (heading) and điểm g up to its first sentence.
    text = """QUYẾT NGHỊ:
Điều 1. Thành lập thị xã Sa Pa và các phường, xã thuộc thị xã Sa Pa, tỉnh
Lào Cai
3. Thành lập 06 xã và điều chỉnh địa giới đơn vị hành chính 01 xã thuộc thị xã
Sa Pa:
g) Điều chỉnh 11,10 km2 diện tích tự nhiên và 1.225 người của xã Sa Pả về xã
Trung Chải. Sau khi điều chỉnh, xã Trung Chải có 50,04 km2 diện tích tự nhiên và
quy mô dân số 5.086 người.
"""
    rows, _, unread = parse("767/NQ-UBTVQH14", text)
    assert unread == []
    assert [(r.district, r.old_name, r.new_name, r.share) for r in rows] == [
        ("thị xã Sa Pa", "Sa Pả", "Trung Chải", "part"),
        ("thị xã Sa Pa", "Trung Chải", "Trung Chải", "absorbing"),
    ]
