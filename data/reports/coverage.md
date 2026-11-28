# Coverage

Written by `pipeline.validate` from the tables in `data/interim/parsed/`.

## Checks

| Check | Problems | Recorded for review | Open |
|---|---:|---:|---:|
| units | 0 | 0 | 0 |
| totals | 0 | 0 | 0 |
| new communes | 5 | 5 | 0 |
| old communes | 5 | 1 | 4 |
| history | 0 | 0 | 0 |

## Problems

| Check | Province | Item | Detail | Status |
|---|---|---|---|---|
| new communes | 31 | Bạch Long Vĩ | 11948 has no row in the crosswalk | recorded |
| new communes | 44 | Cồn Cỏ | 19742 has no row in the crosswalk | recorded |
| new communes | 48 | Hoàng Sa | 20333 has no row in the crosswalk | recorded |
| new communes | 51 | Lý Sơn | 21548 has no row in the crosswalk | recorded |
| new communes | 79 | Côn Đảo | 26732 has no row in the crosswalk | recorded |
| old communes | 01 | 00553 Xã Cổ Bi / Xã Đặng Xá | one code for 2 communes: Phường Phúc Lợi (part); Xã Phù Đổng (part); Xã Thuận An (part); Xã Gia Lâm (part) | open |
| old communes | 01 | 00556 Xã Đặng Xá | split, but only one part is listed: Xã Phù Đổng (part) | open |
| old communes | 04 | 01615 Xã Hồng Quang / Xã Mỹ Hưng | one code for 2 communes: Xã Bế Văn Đàn (full); Xã Phục Hòa (full) | open |
| old communes | 08 | 02485 Xã Công Đa / Xã Phú Thịnh | one code for 2 communes: Xã Trung Sơn (full); Xã Thái Bình (full) | open |
| old communes | 42 | 18796 Xã Kỳ Lợi | moved whole and also elsewhere: Phường Sông Trí (part); Phường Vũng Áng (full); Phường Hoành Sơn (part) | recorded |

## Accepted discrepancies

Reviewed in `pipeline/accepted_discrepancies.csv`.

| Scope | Check | Computed | Stated | Reason |
|---|---|---:|---:|---|
| thai-nguyen-2020 | province_total | 177 | 178 | Tổng số xã cấp tỉnh lệch 1 so với câu tổng kết của nghị quyết: chưa tìm được nghị quyết 469/NQ-UBTVQH15 (thành lập thành phố Phổ Yên, 2022). Không có trên Công báo (dải id 29000-45600 đã quét đủ) và trên vanban.chinhphu.vn. Đã duyệt và chấp nhận ngày 27/11/2026. |
| binh-duong | not_followed | 4 | 0 | 4 xã của thị xã Tân Uyên (Hội Nghĩa, Phú Chánh, Tân Vĩnh Hiệp, Vĩnh Tân) chưa nối được tới 2025: chưa tìm được nghị quyết 725/NQ-UBTVQH15 (thành lập thành phố Tân Uyên, 2023), văn bản đổi các xã này thành phường. Không có trên Công báo (dải id 29000-45600 đã quét đủ), trên vanban.chinhphu.vn và trên cổng thông tin của tỉnh. Đã duyệt và chấp nhận ngày 27/11/2026. |

## By province

Communes: in `ward_new.csv`, and as stated by the 2025 resolution. Reached: communes with a row in the crosswalk. Old communes: codes of the crosswalk moved into the province. Communes of 2019: rows of `commune_history.csv` ending in the province.

| Code | Province | Communes | Stated | Reached | Old communes | Communes of 2019 | Villages |
|---|---|---:|---:|---:|---:|---:|---|
| 01 | Hà Nội | 126 | 126 | 126 | 526 | 583 | none |
| 04 | Cao Bằng | 56 | 56 | 56 | 160 | 210 | none |
| 08 | Tuyên Quang | 124 | 124 | 124 | 329 | 336 | none |
| 11 | Điện Biên | 45 | 45 | 45 | 129 | 131 | none |
| 12 | Lai Châu | 38 | 38 | 38 | 106 | 107 | none |
| 14 | Sơn La | 75 | 75 | 75 | 200 | 204 | none |
| 15 | Lào Cai | 99 | 99 | 99 | 319 | 341 | none |
| 19 | Thái Nguyên | 92 | 92 | 92 | 280 | 301 | none |
| 20 | Lạng Sơn | 65 | 65 | 65 | 194 | 223 | none |
| 22 | Quảng Ninh | 54 | 54 | 54 | 171 | 185 | none |
| 24 | Bắc Ninh | 99 | 99 | 99 | 313 | 354 | none |
| 25 | Phú Thọ | 148 | 148 | 148 | 479 | 623 | none |
| 31 | Hải Phòng | 114 | 114 | 113 | 374 | 487 | none |
| 33 | Hưng Yên | 104 | 104 | 104 | 381 | 447 | none |
| 37 | Ninh Bình | 129 | 129 | 129 | 399 | 490 | 2021 round (Nam Định): 195 old communes of 10 districts; 2026 round: 15 communes with a resolution, 4 more with a plan or another document only |
| 38 | Thanh Hóa | 166 | 166 | 166 | 547 | 636 | none |
| 40 | Nghệ An | 130 | 130 | 130 | 412 | 480 | none |
| 42 | Hà Tĩnh | 69 | 69 | 69 | 209 | 264 | none |
| 44 | Quảng Trị | 78 | 78 | 77 | 264 | 300 | none |
| 46 | Huế | 40 | 40 | 40 | 133 | 153 | none |
| 48 | Đà Nẵng | 94 | 94 | 93 | 280 | 301 | none |
| 51 | Quảng Ngãi | 96 | 96 | 95 | 272 | 283 | none |
| 52 | Gia Lai | 135 | 135 | 135 | 373 | 381 | none |
| 56 | Khánh Hòa | 65 | 65 | 65 | 194 | 205 | none |
| 66 | Đắk Lắk | 102 | 102 | 102 | 286 | 296 | none |
| 68 | Lâm Đồng | 124 | 124 | 124 | 329 | 344 | none |
| 75 | Đồng Nai | 95 | 95 | 95 | 270 | 282 | none |
| 79 | Hồ Chí Minh | 168 | 168 | 167 | 441 | 495 | none |
| 80 | Tây Ninh | 96 | 96 | 96 | 280 | 286 | none |
| 82 | Đồng Tháp | 102 | 102 | 102 | 305 | 314 | none |
| 86 | Vĩnh Long | 124 | 124 | 124 | 354 | 378 | none |
| 91 | An Giang | 102 | 102 | 102 | 298 | 300 | none |
| 92 | Cần Thơ | 103 | 103 | 103 | 263 | 267 | none |
| 96 | Cà Mau | 64 | 64 | 64 | 164 | 162 | none |
