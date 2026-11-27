"""Parse the 2023-2025 (and 2019-2021) district/commune rearrangement resolutions.

Run with: uv run python -m pipeline.parse_resolutions_2024

These resolutions use a different wording from the 2025 ones:

    a) Thành lập phường Nam Phong trên cơ sở toàn bộ diện tích tự nhiên là 6,58 km2 và quy mô
       dân số là 9.160 người của xã Nam Phong.
    d) Nhập toàn bộ diện tích tự nhiên là 3,33 km2, quy mô dân số là 7.674 người của xã Lộc An
       và toàn bộ ... của phường Văn Miếu vào phường Trường Thi. Sau khi nhập, ...
    c) Sau khi sắp xếp, huyện Vụ Bản có 14 đơn vị hành chính cấp xã, gồm 13 xã và 01 thị trấn.

The district of each clause comes from the heading it sits under ("1. Sắp xếp các đơn vị hành
chính cấp xã thuộc huyện Vụ Bản như sau:"). A commune that receives others ("vào phường
Trường Thi") keeps existing and is recorded as absorbing.

Output: data/interim/parsed/<scope>.csv and data/reports/parse_2024_summary.json, which checks
each district's commune count against the official conversion table (the state just before
1 July 2025, which is the state these resolutions produced).
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from pipeline.extract import TEXT_DIR
from pipeline.fetch import MANIFEST
from pipeline.parse_resolutions import PARSED_DIR, REPORTS_DIR
from pipeline.registry import slug

# (text folder, old province code, round). The 2019-2021 round is checked against the state
# the 2023-2025 round started from.
SCOPES = (
    ("nam-dinh-2024", "36", "2024"),
    ("ha-nam-2024", "35", "2024"),
    ("ninh-binh-2024", "37", "2024"),
    ("nam-dinh-2020", "36", "2020"),
    ("ha-nam-2020", "35", "2020"),
    ("ninh-binh-2020", "37", "2020"),
)
COMMUNE = r"phường|xã|thị trấn"
DISTRICT = r"huyện|thành phố|thị xã|quận|Quận"  # "Quận 3"
ITEM = re.compile(r"^(?P<num>\d+\.|[a-zđ]\))\s+(?P<text>.*)$")
ARTICLE = re.compile(r"^Điều (?P<num>\d+)\.\s*(?P<text>.*)$")
# "1. Sắp xếp các đơn vị hành chính cấp xã thuộc huyện Vụ Bản như sau:" and
# "2. Thành lập các phường thuộc thị xã Kim Bảng như sau:".
# Also "Điều chỉnh địa giới ... các xã, thị trấn thuộc huyện Duy Tiên như sau" and "Thành lập
# các phường thuộc thị xã Duy Tiên sau khi điều chỉnh địa giới ... khoản 1 Điều này như sau".
HEADING = re.compile(
    rf"thuộc (?P<type>{DISTRICT}) (?P<name>[^,;:]+?)(?:,\s*tỉnh\b[^:]*?)?"
    r"(?:\s+sau khi[^:]*?)?(?:\s+như sau|\s*:\s*$)"
)
# An article title names the district without a colon: "Điều 3. Thành lập các phường thuộc
# thành phố Huế, tỉnh Thừa Thiên Huế".
ARTICLE_HEADING = re.compile(
    rf"thuộc (?P<type>{DISTRICT}) (?P<name>[^,;:.]+?)(?:,\s*tỉnh\b[^:.]*)?$"
)


def article_district(title: str) -> str | None:
    """District named by an article title; "" when it names several ("Thành lập thị trấn Vĩnh
    Thạnh Trung thuộc huyện Châu Phú, thị trấn Cô Tô thuộc huyện Tri Tôn và ..."), None when
    it names none."""
    if len(re.findall(rf"thuộc (?:{DISTRICT}) ", title)) > 1 or re.search(
        rf"thuộc (?:{DISTRICT}) [^,;:.]+? và (?:{DISTRICT}) ", title
    ):
        return ""  # "... thuộc thị xã Hồng Ngự và thành phố Hồng Ngự thuộc tỉnh Đồng Tháp"
    if h := ARTICLE_HEADING.search(title):
        return without_province(f"{h['type']} {h['name']}")
    return None


SUMMARY = re.compile(
    rf"^Sau khi (?:sắp xếp|thành lập), (?P<type>{DISTRICT}) (?P<name>.+?) có (?P<n>\d+) "
    r"(?:đơn vị hành chính cấp xã|phường|xã)"  # "thành phố Sóc Trăng có 09 phường"
)
# Both orders occur: "diện tích tự nhiên là 6,58 km2" (2024) and "5,01 km2 diện tích tự nhiên,
# 3.695 người" (2019-2021).
MEASURE = re.compile(
    r"(diện tích tự nhiên|quy mô dân số)(\s+là)?\s+[\d.,]+\s*(km2|km²|người)"
    r"|[\d.,]+\s*(km2|km²)\s+diện tích tự nhiên|((quy mô\s+)?dân số\s+)?[\d.,]+\s+người",
    re.IGNORECASE,
)
# "Điều chỉnh 1,33 km2 ... của xã Yên Mật vào xã Kim Chính": part of a commune moves.
ADJUST = re.compile(rf"^Điều chỉnh (?P<body>.+?) vào (?P<ntype>{COMMUNE}) (?P<nname>.+)$")
# Whole communes moved to another district: "Điều chỉnh toàn bộ ... của xã Thủy Vân và toàn
# bộ ... của xã Thủy Bằng thuộc thị xã Hương Thủy vào thành phố Huế" (1264/NQ-UBTVQH14).
DISTRICT_MOVE = re.compile(
    rf"^Điều chỉnh (?P<body>.+?) vào (?P<ntype>{DISTRICT}) (?P<nname>[^,;.]+?)(?:,\s*tỉnh .*)?$"
)
REMAINDER = " (phần còn lại)"
FOUND = re.compile(
    rf"^Thành lập (?P<ntype>{COMMUNE}) (?P<nname>.+?) trên cơ sở (?P<merge>nhập )?(?P<body>.+)$"
)
INTO = re.compile(rf"^Nhập (?P<body>.+?) vào (?P<ntype>{COMMUNE}) (?P<nname>.+)$")
RENAME = re.compile(
    rf"^Đổi tên (?P<otype>{COMMUNE}) (?P<oname>.+?) thành (?P<ntype>{COMMUNE}) (?P<nname>.+)$"
)
PART = re.compile(
    rf"(?P<share>toàn bộ|một phần)[^;]*?\bcủa\s+(?P<type>{COMMUNE})\s+(?P<name>.+?)"
    rf"(?=\s*(?:,|;|và)\s*(?:toàn bộ|một phần)|\s*$)"
)
TYPE_CODES = {"phường": "phuong", "xã": "xa", "thị trấn": "thi_tran"}
# A district formed from listed communes, or a city split by listing each new district's
# wards: "Thành lập thị xã Chũ trên cơ sở ... của10 đơn vị hành chính cấp xã thuộc huyện Lục
# Ngạn, gồm thị trấn Chũ và các xã: Hồng Giang, ..." and "Quận Phú Xuân có 13 phường, gồm:
# An Hòa, Đông Ba, ...".
NEW_DISTRICT = rf"{DISTRICT}|Huyện|Thị xã|Thành phố"
FORMED_FROM = re.compile(
    rf"^Thành lập (?P<ntype>{DISTRICT}) (?P<nname>[^,]+?) trên cơ sở .*?của\s*\d+ đơn vị hành "
    rf"chính cấp xã thuộc (?P<otype>{DISTRICT}) (?P<oname>[^,]+?),\s*gồm:?\s*(?P<list>[^.]+)"
)
MEMBERS = re.compile(
    rf"(?:^|\.\s+)(?P<ntype>{NEW_DISTRICT}) (?P<nname>[^,.:]+?) có \d+ (?P<kind>{COMMUNE}|đơn vị "
    r"hành chính cấp xã)[^:.]*?,\s*gồm:?\s*(?P<list>[^.]+)"
)
# Communes moved to another district by name: "Điều chỉnh một phần diện tích tự nhiên ... của
# huyện Thạch Hà, tương ứng với toàn bộ ... của 11 xã, gồm: Đỉnh Bàn, ..., Thạch Văn và Tượng
# Sơn, để nhập vào thành phố Hà Tĩnh".
TRANSFER = re.compile(
    rf"^Điều chỉnh .*?của (?P<otype>{DISTRICT}) (?P<oname>[^,]+?), tương ứng với toàn bộ .*?"
    rf"của \d+ (?:{COMMUNE}|đơn vị hành chính cấp xã)[^:]*?,?\s*gồm:?\s*(?P<list>.+?),?\s+"
    rf"để nhập vào (?P<ntype>{DISTRICT}) (?P<nname>[^,;.]+)"
)
SPLIT_FROM = re.compile(rf"\bcủa (?P<otype>{DISTRICT}) (?P<oname>[^,.]+?)(?:,|\s+sau\b|$)")
# A commune named with its district: "Thủy Triều, huyện Thủy Nguyên", "Lộc Sơn thuộc huyện
# Phú Lộc".
QUALIFIED = re.compile(rf"^(?P<name>.+?)(?:,\s*|\s+thuộc\s+)(?P<district>(?:{DISTRICT})\s+.+)$")
# "Hoà"/"Hòa", "Thuỵ"/"Thụy": the two accent placements are the same name.
ACCENT_STYLE = {
    "oà": "òa",
    "oá": "óa",
    "oả": "ỏa",
    "oã": "õa",
    "oạ": "ọa",
    "uỳ": "ùy",
    "uý": "úy",
    "uỷ": "ủy",
    "uỹ": "ũy",
    "uỵ": "ụy",
}


def spelling(text: str) -> str:
    """Lower case, one accent style, "Phan Rang - Tháp Chàm" = "Phan Rang-Tháp Chàm"."""
    text = text.lower().strip().replace("\u2019", "'")  # "Đắk R\u2019la" = "Đắk R'la"
    for old, new in ACCENT_STYLE.items():
        # Only at the end of a syllable: "hoà" -> "hòa", but "hoàng" stays.
        text = re.sub(rf"{old}(?![a-zà-ỹđ])", new, text)
    return re.sub(r"\s*-\s*", "-", re.sub(r"\s+", " ", text))


# Names a resolution spells differently from the Statistics Office table, each one reviewed:
# the table's spelling is kept. District and commune names are separate (huyện Đakrông
# is "Huyện Đa Krông" in the table, but xã Đakrông keeps its spelling in both).
NAME_ALIASES = Path(__file__).parent / "name_aliases.csv"


def read_aliases() -> dict[str, dict[str, str]]:
    """kind ("district" | "commune") -> {resolution spelling: table spelling}, normalised."""
    out: dict[str, dict[str, str]] = {"district": {}, "commune": {}}
    if NAME_ALIASES.exists():
        with NAME_ALIASES.open(encoding="utf-8") as handle:
            for r in csv.DictReader(handle):
                out[r["kind"]][spelling(r["resolution_name"])] = spelling(r["table_name"])
    return out


ALIASES = read_aliases()
DISTRICT_TYPE = re.compile(r"^(huyện|thị xã|thành phố|quận) (.+)$")


def plain_key(text: str) -> str:
    """spelling(), with a district named with its type in the table's spelling."""
    text = spelling(text)
    if (m := DISTRICT_TYPE.match(text)) and m[2] in ALIASES["district"]:
        return f"{m[1]} {ALIASES['district'][m[2]]}"
    return text


def without_province(district: str) -> str:
    """ "huyện Cai Lậy, tỉnh Tiền Giang", "thị xã Gò Công thuộc tỉnh Tiền Giang": the district."""
    return re.sub(r"(?:,|\s+thuộc)\s+tỉnh\b.*$", "", district).strip()


def qualified(name: str) -> tuple[str, str]:
    """(name, district) of a commune written with its district, else (name, "")."""
    if m := QUALIFIED.match(name.strip()):
        return m["name"].strip(), without_province(m["district"])
    return name.strip(), ""


# District level: "Nhập toàn bộ ... của huyện Mỹ Lộc vào thành phố Nam Định" and
# "Thành lập thành phố Hoa Lư trên cơ sở nhập toàn bộ ... của thành phố Ninh Bình và huyện Hoa Lư".
DISTRICT_PART = re.compile(
    rf"toàn bộ[^;]*?\bcủa\s+(?P<type>{DISTRICT})\s+(?P<name>.+?)"
    rf"(?=\s*(?:,|;|và)\s*toàn bộ|\s+vào\s+|\s*$)"
)
DISTRICT_INTO = re.compile(rf"^Nhập (?P<body>.+?) vào (?P<ntype>{DISTRICT}) (?P<nname>.+)$")
DISTRICT_FOUND = re.compile(
    rf"^Thành lập (?P<ntype>{DISTRICT}) (?P<nname>.+?) trên cơ sở (?:nhập )?(?P<body>.+)$"
)


@dataclass
class Row:
    doc_id: str
    district: str
    clause: str
    new_type: str
    new_name: str
    old_type: str
    old_name: str
    share: str  # full | part | absorbing | renamed
    effective: str
    source_text: str
    # District of the old commune when the text names one ("xã Thủy Triều, huyện Thủy
    # Nguyên"): a commune moved from another district. Empty: the clause's district.
    old_district: str = ""


def first_sentence(text: str) -> str:
    for match in re.finditer(r"\.\s+(\S)", text):
        if match.group(1).isupper():
            return text[: match.start()]
    return text.rstrip(".;")


def clean(sentence: str) -> str:
    # Numbered wards are written "Phường 9", without a lower-case type word.
    sentence = re.sub(r"\bPhường (?=\d)", "phường ", sentence)
    sentence = re.sub(r"\s+để nhập\s+vào\s+", " vào ", sentence)  # "Điều chỉnh ... để nhập vào"
    # "Điều chỉnh 11,10 km2 ... của xã Sa Pả về xã Trung Chải" (896/NQ-UBTVQH14).
    sentence = re.sub(rf"\s+về\s+(?=(?:{COMMUNE})\s)", " vào ", sentence)
    # "Điều chỉnh 1,86 ha diện tích tự nhiên tổ dân phố số 28 do phường Mai Dịch ... quản lý
    # hành chính đang thuộc địa giới hành chính của phường Mỹ Đình 2, quận Nam Từ Liêm vào
    # phường Mai Dịch" (1263/NQ-UBTVQH14): part of the commune whose territory it was.
    sentence = re.sub(
        r"^Điều chỉnh .*?\bđang thuộc địa giới hành chính của\s+",
        "Điều chỉnh một phần diện tích tự nhiên của ",
        sentence,
    )
    # "Nhập xã Thiệu Phú với toàn bộ diện tích tự nhiên ... vào thị trấn Thiệu Hóa"
    # (939/NQ-UBTVQH15).
    sentence = re.sub(
        rf"^Nhập (?P<unit>(?:{COMMUNE}) [^,;]+?) với (?P<share>toàn bộ|một phần)"
        r" (?P<what>.+?) vào ",
        r"Nhập \g<share> \g<what> của \g<unit> vào ",
        sentence,
    )
    # "của xã Yên Mật sau khi điều chỉnh địa giới ... quy định tại điểm b khoản này": the rest
    # of a commune that lost part of its area in an earlier point.
    text = re.sub(
        r"\s+sau khi điều chỉnh (?:địa giới|theo quy định).*?(?:khoản|Điều) này",
        REMAINDER,
        sentence,
    )
    text = MEASURE.sub("", text)
    # Removing the measures leaves empty list slots: "của xã Tân Lang, , của xã Trùng Quán" and
    # "toàn bộ , của". Commas between units stay; the one after a share word goes.
    text = re.sub(r"\s*[,;](?:\s*,)+", ",", text)
    text = re.sub(r"\b(toàn bộ|một phần|cơ sở|nhập|Nhập|Điều chỉnh|và)\s*,\s*", r"\1 ", text)
    text = re.sub(r"\b(toàn bộ|một phần)\s+(và\s+)?(?=của\b)", r"\1 ", text)
    # "... và điều chỉnh một phần của phường Tân Phong": one more part in the same list.
    text = re.sub(r"(?:\s+và|,)\s+điều chỉnh một phần\s+(?=của\b)", ", một phần ", text)
    # The boundary sentence run into the clause: "..., Phường Thạch Hạ giáp các phường ...".
    text = re.sub(r",?\s+(?:Phường|Xã|Thị trấn)\s+[^,;]+?\s+giáp\b.*$", "", text)
    return re.sub(r"\s+", " ", text).strip(" ,.;")


def parts(body: str) -> list[tuple[str, str, str]]:
    # Lists also use ";" and a shared "toàn bộ": "của phường Ngô Quyền và của phường Trần
    # Quang Khải" means "toàn bộ ... của phường Ngô Quyền và toàn bộ ... của phường ...".
    body = body.replace(";", ",")
    # An amount with no "toàn bộ" ("trên cơ sở 4,67 km2 ... của xã Tân Lang", "Điều chỉnh ... của
    # xã X") is part of the commune; "... còn lại của phường Phú Thuận" is its remainder.
    body = re.sub(r"\bcòn lại\s+(?=của\s)", "", body.replace("toàn bộ còn lại", "một phần"))
    if body.startswith("của "):
        body = "một phần " + body

    def shared(m: re.Match[str]) -> str:
        before = re.findall(r"toàn bộ|một phần", body[: m.start()])
        return f" {m[1]} {before[-1] if before else 'một phần'} "

    body = re.sub(r"\s*(,|và)\s+(?=của\s)", shared, body)
    out = []
    for m in PART.finditer(body):
        name, share = m["name"].strip(), "full" if m["share"] == "toàn bộ" else "part"
        if name.endswith(REMAINDER):
            name, share = name[: -len(REMAINDER)].strip(), "part"
        out.append((share, TYPE_CODES[m["type"]], name))
    return out


def items(text: str) -> list[tuple[str, str, str]]:
    """(clause path, district, item text) for every item of the operative articles."""
    body = text.split("QUYẾT NGHỊ", 1)[-1]
    out: list[list[str]] = []
    article = number = ""
    district = ""
    for line in body.splitlines():
        line = line.strip()
        if a := ARTICLE.match(line):
            if "Hiệu lực" in a["text"]:
                break
            article, number = a["num"], ""
            # A new article starts without the district of the one before it.
            district = article_district(a["text"]) or ""
            out.append([f"Điều {article}", district, a["text"]])
            continue
        if m := ITEM.match(line):
            label = m["num"].rstrip(".)")
            if m["num"].endswith("."):
                number = label
                path = f"Điều {article}, khoản {number}"
            else:
                path = f"Điều {article}, khoản {number}, điểm {label}"
            out.append([path, district, m["text"]])
        elif out and line:
            out[-1][2] += " " + line
        if out and (h := HEADING.search(out[-1][2])):
            district = without_province(f"{h['type']} {h['name']}")
            out[-1][1] = district
        elif (
            out
            and out[-1][0].count(",") == 0
            and (named := article_district(out[-1][2])) is not None
        ):
            district = out[-1][1] = named
    return [(p, d, re.sub(r"\s+", " ", t)) for p, d, t in out]


def moved(
    olds: list[tuple[str, str, str]], target: str, base: dict[str, str], rows: list[Row]
) -> bool:
    """Rows for whole communes moved into the district target; the district written once,
    after the last commune ("... của xã Nghi Phong thuộc huyện Nghi Lộc"), is every
    commune's. False when one is only part of a commune (into no commune: not understood)."""
    _, from_district = qualified(olds[-1][2])
    if any(share != "full" for share, _, _ in olds):
        return False
    for _, old_type, old_name in olds:
        name, own = qualified(old_name)
        rows.append(
            Row(
                **{**base, "district": target},
                new_type=old_type,
                new_name=name,
                old_type=old_type,
                old_name=name,
                share="moved",
                old_district=without_province(own or from_district),
            )
        )
    return True


def parse_sentence(
    sentence: str,
    path: str,
    district: str,
    item: str,
    effective: str,
    doc_id: str,
    rows: list[Row],
    unread: list[str],
) -> None:
    """Append the rows of one sentence of a clause; sentences that change communes but are
    not understood go to unread. "Giải thể xã X" gives no row: X was shared out by the
    adjustments before it."""
    if sentence.startswith("Giải thể "):
        return
    base = {
        "doc_id": doc_id,
        "district": district,
        "clause": path,
        "effective": effective,
        "source_text": item[:400],
    }
    district_match = DISTRICT_INTO.match(sentence) or DISTRICT_FOUND.match(sentence)
    district_olds = (
        [
            (d["type"], re.sub(r",\s*tỉnh .+$", "", d["name"]).strip())
            for d in DISTRICT_PART.finditer(district_match["body"])
        ]
        if district_match
        else []
    )
    if district_match and district_olds:
        target = (district_match["ntype"], district_match["nname"].strip())
        if DISTRICT_INTO.match(sentence):
            district_olds.append(target)  # the receiving district continues
            # "Nhập toàn bộ ... của thị xã Cửa Lò và toàn bộ ... của xã Nghi Xuân, ... xã Nghi
            # Phong thuộc huyện Nghi Lộc vào thành phố Vinh" (1243/NQ-UBTVQH15).
            communes = parts(district_match["body"])
            if communes and not moved(communes, " ".join(target), base, rows):
                unread.append(f"{path}: {item[:200]}")
        for old_type, old_name in district_olds:
            rows.append(
                Row(
                    **base,
                    new_type=target[0],
                    new_name=target[1],
                    old_type=old_type,
                    old_name=old_name,
                    share="district_merge",
                )
            )
    elif m := FOUND.match(sentence):
        new_type, new_name = TYPE_CODES[m["ntype"]], m["nname"].strip()
        olds = parts(m["body"])
        single = len(olds) == 1 and not m["merge"] and olds[0][0] == "full"
        for share, old_type, old_name in olds:
            rows.append(
                Row(
                    **base,
                    new_type=new_type,
                    new_name=new_name,
                    old_type=old_type,
                    old_name=old_name,
                    share="renamed" if single else share,
                )
            )
        if not olds:
            unread.append(f"{path}: {item[:200]}")
    elif (m := DISTRICT_MOVE.match(sentence)) and (olds := parts(m["body"])):
        if not moved(olds, f"{m['ntype']} {m['nname'].strip()}", base, rows):
            unread.append(f"{path}: {item[:200]}")
    elif m := INTO.match(sentence) or ADJUST.match(sentence):
        new_type, new_name = TYPE_CODES[m["ntype"]], m["nname"].strip()
        olds = parts(m["body"])
        for share, old_type, old_name in olds:
            rows.append(
                Row(
                    **base,
                    new_type=new_type,
                    new_name=new_name,
                    old_type=old_type,
                    old_name=old_name,
                    share=share,
                )
            )
        rows.append(
            Row(
                **base,
                new_type=new_type,
                new_name=new_name,
                old_type=new_type,
                old_name=new_name,
                share="absorbing",
            )
        )
        if not olds:
            unread.append(f"{path}: {item[:200]}")
    elif m := RENAME.match(sentence):
        rows.append(
            Row(
                **base,
                new_type=TYPE_CODES[m["ntype"]],
                new_name=m["nname"].strip(),
                old_type=TYPE_CODES[m["otype"]],
                old_name=m["oname"].strip(),
                share="renamed",
            )
        )
    elif re.match(
        r"^(Thành lập|Nhập|Đổi tên|Giải thể|Điều chỉnh) .*(phường|xã|thị trấn)\b", sentence
    ) and (
        not re.search(rf"\b({DISTRICT}) \S", sentence.split(" trên cơ sở")[0].split(" vào ")[-1])
    ):
        unread.append(f"{path}: {item[:200]}")


def members(item: str, district: str) -> tuple[str, str, bool, list[tuple[str, str]]] | None:
    """(new district, old district, names are the ones before the round, [(type, name)]) of an
    item listing a district's communes."""
    if m := FORMED_FROM.match(item) or TRANSFER.match(item):
        old = f"{m['otype']} {m['oname'].strip()}"
        before = True
        kind = "xã"
    elif m := MEMBERS.search(item):
        # Only the list of a district this item creates: "a) Thành lập quận Phú Xuân trên cơ sở
        # một phần ... của thành phố Huế ... Quận Phú Xuân có 13 phường, gồm: ...".
        found = re.match(
            rf"^Thành lập {m['ntype'].lower()} {re.escape(m['nname'].strip())} trên cơ sở (.*)",
            first_sentence(item),
        )
        split = SPLIT_FROM.search(found[1]) if found else None
        if not split:
            return None
        old = f"{split['otype']} {split['oname'].strip()}"
        before = False
        kind = m["kind"] if m["kind"] in TYPE_CODES else "xã"
    else:
        return None
    units = []
    for piece in re.split(r",\s*|\s+và\s+", m["list"].strip().rstrip(".;")):
        if t := re.match(rf"^(?:các\s+)?({COMMUNE}):?\s*", piece):
            kind, piece = t[1], piece[t.end() :]
        if piece.strip():
            units.append((TYPE_CODES[kind], piece.strip()))
    if any(name[0].isdigit() for _, name in units):
        return None  # a count ("gồm 11 xã và 02 thị trấn"), not a list of names
    return f"{m['ntype'].lower()} {m['nname'].strip()}", old, before, units


def move_members(
    rows: list[Row], groups: list[tuple[Row, str, str, bool, list[tuple[str, str]]]]
) -> None:
    """Put the listed communes in their new district: a row already naming the commune gets
    the new district; a commune with no row moves unchanged ("moved"). A list of the communes
    before the round (thị xã Chũ) only names the old communes of the new district's rows; part
    of one may stay behind ("một phần ... của xã Thanh Hải" into xã Biên Sơn, huyện Lục Ngạn)."""
    for base, new, old, before, units in groups:
        for unit_type, name in units:
            key = name_key(name)
            named = [
                r
                for r in rows
                if r.share != "district_merge"
                and r.doc_id == base.doc_id
                and key == name_key(r.old_name if before else r.new_name)
                and plain_key(r.district)
                in ((plain_key(new),) if before else (plain_key(new), plain_key(old), ""))
            ]
            for r in named:
                if plain_key(r.district) != plain_key(new):
                    r.old_district = r.old_district or r.district or old
                    r.district = new
                elif not r.old_district:
                    r.old_district = old
            if not named:
                rows.append(
                    Row(
                        doc_id=base.doc_id,
                        district=new,
                        clause=base.clause,
                        new_type=unit_type,
                        new_name=name,
                        old_type=unit_type,
                        old_name=name,
                        share="moved",
                        effective=base.effective,
                        source_text=base.source_text,
                        old_district=old,
                    )
                )


def parse(doc_id: str, text: str) -> tuple[list[Row], dict[str, int], list[str]]:
    effective = ""
    if m := re.search(
        r"hiệu lực(?: thi hành)?(?: kể)? từ ngày (\d{1,2}) tháng (\d{1,2}) năm (\d{4})", text
    ):
        effective = f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    rows: list[Row] = []
    stated: dict[str, int] = {}
    unread: list[str] = []
    groups = []
    summarised: dict[str, list[str]] = defaultdict(list)
    listed = items(text)
    for path, district, item in listed:
        if "," not in path and any(p.startswith(f"{path},") for p, _, _ in listed):
            continue  # the title of an article with numbered clauses repeats them
        if g := members(item, district):
            here = Row(doc_id, district, path, "", "", "", "", "", effective, item[:400])
            groups.append((here, *g))
        if s := SUMMARY.match(item):
            stated[f"{s['type']} {s['name']}"] = int(s["n"])
            summarised[path.split(",")[0]].append(f"{s['type']} {s['name']}")
            continue
        if re.fullmatch(r"[^.]*:", item.rstrip()):
            continue  # only a heading ("3. Thành lập 06 xã ... thuộc thị xã Sa Pa:")
        # "Điều chỉnh ... vào phường Tây Lộc và nhập toàn bộ ... vào phường Thuận Hòa": two
        # operations in one sentence.
        # "1. Sắp xếp đơn vị hành chính cấp xã thuộc huyện Tân Phước như sau: Nhập toàn bộ ...":
        # a clause with a single operation, written after its heading (870/NQ-UBTVQH14).
        body = re.sub(r"^[^.]*?\bnhư sau:\s+(?=\S)", "", item)
        sentences = re.split(
            r"(?:,?\s+và|;|,)\s+(?=(?:nhập|điều chỉnh)\s)", clean(first_sentence(body))
        )
        # "Nhập toàn bộ ... của xã Tô Hiệu và điều chỉnh ... của xã Hoàng Văn Thụ vào thị trấn
        # Bình Gia": both go into the commune the last one names.
        for i, sentence in enumerate(sentences):
            if " vào " not in sentence:
                later = next((t for t in sentences[i + 1 :] if " vào " in t), "")
                if target := re.search(rf"\svào (?:{COMMUNE}) .+$", later):
                    sentences[i] = sentence + target[0]
        for sentence in sentences:
            sentence = sentence[:1].upper() + sentence[1:]
            parse_sentence(sentence, path, district, item, effective, doc_id, rows, unread)
    for r in rows:
        # "Điều 1. Sắp xếp các đơn vị hành chính cấp xã thuộc tỉnh Đồng Tháp" names no district;
        # "2. Sau khi sắp xếp, huyện Hồng Ngự có 10 đơn vị ..." does, when it is the only one.
        if not r.district and len(set(summarised[r.clause.split(",")[0]])) == 1:
            r.district = summarised[r.clause.split(",")[0]][0]
    for r in rows:
        if r.share == "district_merge":
            # "Thành lập thị xã Chơn Thành thuộc tỉnh Bình Phước trên cơ sở ..."
            r.new_name, r.old_name = without_province(r.new_name), without_province(r.old_name)
            r.district = without_province(r.district)
            continue
        r.old_name, own_district = qualified(r.old_name)
        r.old_district = own_district or r.old_district  # a "moved" row has it already
        r.new_name, new_district = qualified(r.new_name)
        if new_district:  # the new commune belongs to another district than the heading's
            r.old_district = r.old_district or r.district
            r.district = new_district
    move_members(rows, groups)
    # Each operation of a sentence names the receiving commune: keep it once.
    unique = list({tuple(asdict(r).values()): r for r in rows}.values())
    return unique, stated, unread


def name_key(name: str) -> str:
    key = re.sub(rf"^({COMMUNE}) ", "", spelling(name)).strip()
    return ALIASES["commune"].get(key, key)


def unit_key(unit_type: str, name: str) -> str:
    """A commune by type and name: thị trấn Đầm Hà and xã Đầm Hà of huyện Đầm Hà are two
    communes ("thi_tran đầm hà", "xa đầm hà")."""
    return f"{unit_type} {name_key(name)}"


def same_name(key: str, other: str) -> bool:
    """Two unit_key()s with the same name, whatever the type."""
    return key.split(" ", 1)[-1] == other.split(" ", 1)[-1]


def table_key(name: str) -> str:
    """unit_key() of a commune as the Statistics Office table writes it ("Thị trấn Đầm Hà")."""
    m = re.match(rf"^({COMMUNE}) ", spelling(name))
    return unit_key(TYPE_CODES[m[1]] if m else "", name)


def district_of(row: Row) -> str:
    """Normalised district of the old commune of a row."""
    return plain_key(row.old_district or row.district)


def state_before_2024(
    crosswalk: list[dict[str, str]], province: str, rows_2024: list[Row]
) -> set[tuple[str, str]]:
    """(district, commune) pairs that existed when the 2023-2025 round started: the official
    table's pre-2025 communes, with each 2024 change undone."""
    state = {
        (plain_key(c["old_district_name"]), table_key(c["old_ward_name"]))
        for c in crosswalk
        if c["old_province_code"] == province and not c["old_ward_name"].startswith("Khu vực")
    }
    return undo(state, rows_2024)


def stages(rows: list[Row]) -> list[list[Row]]:
    """The rows of a round grouped by effective date, document and article, in that order: a
    later document of the same round may change a commune again (Thanh Hóa: xã Hải Hòa into
    thị trấn Tĩnh Gia in December 2019, thị trấn Tĩnh Gia into phường Hải Hòa of thị xã Nghi Sơn
    in June 2020), and so may a later article of the same one (829/NQ-UBTVQH14, Hà Nam: Điều 1
    forms thị trấn Đồng Văn, Điều 2 makes it phường Đồng Văn of thị xã Duy Tiên)."""

    def order(r: Row) -> tuple[str, int, int]:
        doc = re.match(r"\d+", r.doc_id)
        article = re.match(r"Điều (\d+)", r.clause)
        return r.effective, int(doc[0]) if doc else 0, int(article[1]) if article else 0

    by_stage: dict[tuple[str, int, int], list[Row]] = defaultdict(list)
    for r in rows:
        by_stage[order(r)].append(r)
    return [by_stage[k] for k in sorted(by_stage)]


def undo(state: set[tuple[str, str]], rows: list[Row]) -> set[tuple[str, str]]:
    """The (district, commune) pairs before a round, from the pairs after it: each stage is
    undone, latest first. A commune whose district was renamed or merged by the same document
    goes back to the old district (thị xã Nghi Sơn back to huyện Tĩnh Gia). Districts are
    compared with their type: huyện Hồng Ngự and thị xã Hồng Ngự are two districts."""
    merged: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))  # new -> olds
    into: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))  # old -> news
    for r in rows:
        if r.share == "district_merge":
            old = plain_key(f"{r.old_type} {r.old_name}".replace(" (phần còn lại)", ""))
            new = plain_key(f"{r.new_type} {r.new_name}")
            merged[r.doc_id][new].add(old)
            into[r.doc_id][old].add(new)
    state = set(state)
    for stage in reversed(stages(rows)):
        doc = stage[0].doc_id
        # The new commune is in the table under its district's name after the document, which
        # may differ from the clause's ("thị xã Đông Triều" in the text, "Thành phố Đông Triều"
        # in the table, renamed by the same document).
        gone = set()
        for r in stage:
            if r.share != "district_merge":
                district = plain_key(r.district)
                for d in {district, *into[doc].get(district, ())}:
                    gone.add((d, unit_key(r.new_type, r.new_name)))
        # The table may give another type than the resolutions (xã Tiên Sơn, thị xã Duy Tiên,
        # is "Phường Tiên Sơn" there): a commune of the same name, alone in its district, is it.
        for d, c in gone - state:
            same = {(d2, c2) for d2, c2 in state if d2 == d and same_name(c2, c)}
            if len(same) == 1:
                gone |= same
        state -= gone
        # A district renamed or retyped from a single one in this stage (thị xã Đông Triều to
        # thành phố Đông Triều): its unchanged communes go back under the old name too.
        renamed = {
            plain_key(f"{r.new_type} {r.new_name}"): olds
            for r in stage
            if r.share == "district_merge"
            and len(olds := merged[doc][plain_key(f"{r.new_type} {r.new_name}")]) == 1
        }
        state = {(next(iter(renamed[d])) if d in renamed else d, c) for d, c in state}
        # A commune moved or renamed earlier in the stage, then changed again (1232/NQ-UBTVQH15:
        # xã Đại Bản moved from huyện An Dương to quận Hồng Bàng, then made phường Đại Bản),
        # did not exist before it: only the first step's old commune goes back.
        passed = {
            (plain_key(r.district), unit_key(r.new_type, r.new_name))
            for r in stage
            if r.share in ("moved", "renamed")
        }
        for r in stage:
            if r.share == "district_merge":
                continue
            district = district_of(r)
            olds = merged[doc].get(district, set())
            if not r.old_district and len(olds) == 1:
                district = next(iter(olds))
            old = unit_key(r.old_type, r.old_name)
            if (plain_key(r.district), old) in passed and r.share not in ("moved", "renamed"):
                continue
            if (district, old) in passed and r.share in ("moved", "renamed"):
                continue
            state.add((district, old))
    return state


# Old provinces whose name in the 2019-2021 titles differs from the conversion table's.
OLD_NAMES = {"thua-thien-hue": "hue"}


def other_scopes(crosswalk: list[dict[str, str]]) -> list[tuple[str, str, str]]:
    """The earlier rounds of every old province in the manifest, after the pilot ones: 2024
    first, since each 2020 folder is checked against the state its 2024 folder starts from.
    The folder ("bac-giang-2024") gives the old province, whose code the conversion table has."""
    codes = {
        slug(re.sub(r"^(Tỉnh|Thành phố)\s+", "", c["old_province_name"])): c["old_province_code"]
        for c in crosswalk
    }
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    known = {scope for scope, _, _ in SCOPES}
    out = []
    for round_ in ("2024", "2020"):
        kind = f"ward_resolution_{round_}"
        folders = sorted({e["scope"] for e in manifest.values() if e["kind"] == kind} - known)
        for f in folders:
            name = f.removesuffix(f"-{round_}")
            out.append((f, codes[OLD_NAMES.get(name, name)], round_))
    return out


def document_order(doc_id: str, text: str, effective: str = "") -> tuple[str, int]:
    """(effective date, number) of a document, the order stages() applies it in."""
    if not effective and (
        m := re.search(
            r"hiệu lực(?: thi hành)?(?: kể)? từ ngày (\d{1,2}) tháng (\d{1,2}) năm (\d{4})", text
        )
    ):
        effective = f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    number = re.match(r"\d+", doc_id)
    return effective, int(number[0]) if number else 0


def total_of(text: str) -> int | None:
    """The province's commune total a document states, last ("... tỉnh Bạc Liêu có 07 đơn vị
    hành chính cấp huyện, ...; 64 đơn vị hành chính cấp xã"), in Điều 1 or a later article."""
    totals = re.findall(
        # "có 11 đơn vị đơn vị hành chính" (Đồng Nai): a word repeated in the text.
        r"(?:tỉnh|[Tt]hành phố)\s+[^\d;]{2,40}?\s+(?:có\s+)?\d+\s+(?:đơn\s+vị\s+)?đơn\s+vị"
        r"\s+hành\s+chính"
        r"\s+cấp\s+huyện[^;]*?;\s*(\d+)\s+đơn\s+vị\s+hành\s+chính\s+cấp\s+xã",
        text.split("QUYẾT NGHỊ", 1)[-1],
    )
    return int(totals[-1]) if totals else None


# Count mismatches reviewed and accepted, with the reason: "province_total" (computed and
# stated commune totals, read here) and "not_followed" (communes of an old province not
# followed to 2025, against 0 expected, read by pipeline.commune_history). An entry only
# applies while both numbers stay as recorded, so a change in the data brings it back.
ACCEPTED = Path(__file__).parent / "accepted_discrepancies.csv"


def accepted() -> dict[tuple[str, str, int, int], str]:
    """(scope, check, computed, stated) -> reason."""
    if not ACCEPTED.exists():
        return {}
    with ACCEPTED.open(encoding="utf-8") as handle:
        return {
            (r["scope"], r["check"], int(r["computed"]), int(r["stated"])): r["reason"]
            for r in csv.DictReader(handle)
        }


def main() -> int:
    with (PARSED_DIR / "crosswalk.csv").open(encoding="utf-8") as handle:
        crosswalk = list(csv.DictReader(handle))
    reviewed = accepted()
    summary: dict[str, object] = {}
    parsed: dict[str, list[Row]] = {}
    for scope, province, round_ in [*SCOPES, *other_scopes(crosswalk)]:
        # A province can have several resolutions in one round (2019-2021: Thanh Hóa has 4).
        rows, unread = [], []
        # Each document's own counts: (when, district counts, province total).
        docs: list[tuple[tuple[str, int], dict[str, int], int | None]] = []
        for path in sorted((TEXT_DIR / scope).glob("*.txt")):
            text = re.sub(r"\f\[page \d+\]\n", "", path.read_text(encoding="utf-8"))
            doc_id = re.search(r"Số:\s*(\d+/NQ-UBTVQH1[45])", text)
            doc_rows, doc_stated, doc_unread = parse(doc_id[1] if doc_id else scope, text)
            rows += doc_rows
            unread += doc_unread
            docs.append(
                (document_order(doc_id[1] if doc_id else "", text), doc_stated, total_of(text))
            )
        docs.sort(key=lambda d: d[0])
        parsed[scope] = rows
        with (PARSED_DIR / f"{scope}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(Row.__dataclass_fields__))
            writer.writeheader()
            writer.writerows(asdict(r) for r in rows)

        # The state this round produced: just before 1 July 2025 for the 2023-2025 round
        # (official table), and the start of the 2023-2025 round for the 2019-2021 round.
        if round_ == "2024":
            after = {
                (plain_key(c["old_district_name"]), table_key(c["old_ward_name"]))
                for c in crosswalk
                if c["old_province_code"] == province
                and not c["old_ward_name"].startswith("Khu vực")
            }
        else:
            base = scope.removesuffix("-2020")
            later = parsed.get(f"{OLD_NAMES.get(base, base)}-2024", [])
            after = state_before_2024(crosswalk, province, later)
        # A document's counts hold just after it: undo the documents of the round after it
        # (Cao Bằng: huyện Phục Hòa counted in February 2020, merged into Quảng Hòa in March).
        counts: dict[str, dict[str, int]] = {}
        province_total: tuple[int, int] | None = None  # (stated, computed)
        for when, doc_stated, doc_total in docs:
            later = [r for r in rows if document_order(r.doc_id, "", r.effective) > when]
            state = undo(after, later)
            by_district: dict[str, set[str]] = defaultdict(set)
            for district, name in state:
                by_district[district].add(name)
            for d, n in doc_stated.items():
                counts[d] = {"stated": n, "computed": len(by_district.get(plain_key(d), set()))}
            if doc_total is not None:
                province_total = (doc_total, len(state))
        names = {name for _, name in after}
        # A commune a later article or document of the round changes again is passed on.
        passed_on = {
            unit_key(r.old_type, r.old_name)
            for r in rows
            if r.share not in ("district_merge", "absorbing")
        }
        missing = sorted(
            {
                f"{r.district} | {r.new_type} {r.new_name}"
                for r in rows
                if r.share != "district_merge"
                and unit_key(r.new_type, r.new_name) not in names | passed_on
            }
        )
        mismatches = {d: c for d, c in counts.items() if c["stated"] != c["computed"]}
        summary[scope] = {
            "rows": len(rows),
            "unread": unread,
            "province_total": {
                "stated": province_total[0] if province_total else None,
                "computed": province_total[1] if province_total else len(after),
            },
            "district_counts": counts,
            "count_mismatches": mismatches,
            "new_names_not_in_next_state": missing,
            # Old names should be single communes; a leftover "của" or ";" means two were joined.
            "suspicious_old_names": sorted(
                {r.old_name for r in rows if re.search(r"\bcủa\b|;|,| và ", r.old_name)}
            ),
        }
        total = summary[scope]["province_total"]  # type: ignore[index]
        key = (scope, "province_total", total["computed"], total["stated"])
        if total["stated"] is not None and key in reviewed:
            total["accepted"] = reviewed[key]
        print(
            f"{scope}: {len(rows)} rows, {len(unread)} unread, "
            f"{len(counts) - len(mismatches)}/{len(counts)} district counts match, "
            f"province {total['computed']}/{total['stated']}"
            f"{' (accepted)' if 'accepted' in total else ''}, "
            f"{len(missing)} new names not found in the next state"
        )
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "parse_2024_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
