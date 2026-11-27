"""Pilot: find the 2026 village rearrangement resolutions of every commune in Ninh Bình.

Run with: uv run python -m pipeline.villages_ninh_binh [discover|search|download|all]

In 2026 villages (thôn, xóm, tổ dân phố) were rearranged by resolutions of each commune's
People's Council (Nghị định 185/2026/NĐ-CP; Kế hoạch 181/KH-UBND of Ninh Bình). Each commune
publishes its documents on its own portal, <slug>.ninhbinh.gov.vn. This script:

1. discover: lists the 129 communes from Decision 19/2025 (Công báo text) and checks which
   portal platform each one runs;
2. search:   searches each portal's document list for village rearrangement documents;
3. download: saves the attached files of the matching documents.

Requests are spaced by DELAY seconds and every HTML page is cached under data/raw/villages/,
so the script can be stopped and re-run. It stops at the first sign of being blocked.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from pipeline.extract import TEXT_DIR
from pipeline.fetch import USER_AGENT, ssl_context

PROVINCE_CODE = "37"
OUT_DIR = Path("data/raw/villages/ninh-binh")
STATE = OUT_DIR / "state.json"
DELAY = 1.0
SEARCH_TERMS = (
    "tổ chức lại thôn",
    "tổ chức lại các thôn",
    "tổ chức lại xóm",
    "tổ chức lại tổ dân phố",
    "sắp xếp thôn",
    "sáp nhập thôn",
)
# \b keeps "thôn" from matching inside "thông".
TITLE_MATCH = re.compile(
    r"(sắp xếp|tổ chức lại|sáp nhập|hợp nhất|kết thúc hoạt động).*\b(thôn|xóm|tổ dân phố)\b",
    re.IGNORECASE,
)


class Blocked(RuntimeError):
    pass


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFD", name.replace("đ", "d").replace("Đ", "D"))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def communes() -> list[dict[str, str]]:
    """Communes of Ninh Bình as listed in Phụ lục II of Decision 19/2025."""
    text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((TEXT_DIR / "national").glob("*.txt"))
    )
    text = re.sub(r"\f\[page \d+\]\n", "", text).split("Phụ lục II", 1)[1]
    rows: list[dict[str, str]] = []
    inside = False
    for line in text.splitlines():
        if re.match(r"^\d{2}\.\s+(TỈNH|THÀNH PHỐ)\s", line):
            inside = line.startswith(f"{PROVINCE_CODE}.")
            continue
        match = re.match(r"^(\d{5})\s+(Phường|Xã|Đặc khu)\s+(.+)$", line.strip())
        if inside and match:
            rows.append(
                {"code": match[1], "type": match[2], "name": match[3], "slug": slugify(match[3])}
            )
    return rows


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=40,
            verify=ssl_context(),
        )
        self.last = 0.0

    def get(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        wait = DELAY - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        response = self.http.get(url, params=params)
        if response.status_code in (403, 429):
            raise Blocked(f"{response.status_code} on {response.url}")
        return response

    def post(self, url: str, data: dict[str, str]) -> str:
        wait = DELAY - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        response = self.http.post(url, data=data)
        if response.status_code in (403, 429):
            raise Blocked(f"{response.status_code} on {response.url}")
        return response.text if response.status_code == 200 else ""

    def page(self, url: str, params: dict[str, str] | None = None) -> str:
        key = hashlib.sha256(f"{url}?{json.dumps(params, sort_keys=True)}".encode()).hexdigest()
        cache = OUT_DIR / "html" / f"{key[:20]}.html"
        if cache.exists():
            return cache.read_text(encoding="utf-8")
        response = self.get(url, params)
        cache.parent.mkdir(parents=True, exist_ok=True)
        text = response.text if response.status_code == 200 else ""
        cache.write_text(text, encoding="utf-8")
        return text


def platform(html: str) -> str:
    if not html:
        return "unreachable"
    if re.search(r"/van-ban-dieu-hanh/\d+", html):
        return "van-ban-dieu-hanh"
    if re.search(r"/van-?ban/chitietvb-\d+\.html", html):
        return "vanban"
    if "storage-vnportal.vnpt.vn" in html:
        return "vnpt"
    return "unknown"


def discover(client: Client, state: dict[str, dict[str, object]]) -> None:
    for commune in communes():
        entry = state.setdefault(commune["code"], dict(commune))
        if "platform" in entry:
            continue
        base = f"https://{commune['slug']}.ninhbinh.gov.vn/"
        try:
            html = client.page(base)
        except httpx.HTTPError as exc:
            html = ""
            entry["error"] = str(exc)
        entry["base"] = base
        entry["platform"] = platform(html)
        print(f"{commune['code']} {commune['type']:<7} {commune['name']:<20} {entry['platform']}")


def search_van_ban_dieu_hanh(client: Client, base: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for term in SEARCH_TERMS:
        for page in (1, 2, 3, 4, 5):
            html = client.page(
                urljoin(base, "van-ban-dieu-hanh"), {"search": term, "page": str(page)}
            )
            soup = BeautifulSoup(html, "html.parser")
            new = 0
            for link in soup.find_all("a", href=True):
                href = str(link["href"])
                title = " ".join(link.get_text().split())
                if re.search(r"/van-ban-dieu-hanh/\d+$", href) and len(title) > 12:
                    if href not in found:
                        new += 1
                    found.setdefault(urljoin(base, href), title)
            if not new:
                break
    return {url: title for url, title in found.items() if TITLE_MATCH.search(title)}


def search_vanban(client: Client, base: str) -> dict[str, str]:
    """This platform's search returns HTTP 500, but its document index (/vanban or
    /van-ban) lists every document on one page, so the index is filtered by title."""
    found: dict[str, str] = {}
    for index in ("vanban", "van-ban"):
        soup = BeautifulSoup(client.page(urljoin(base, index)), "html.parser")
        for link in soup.find_all("a", href=True):
            href = urljoin(base, str(link["href"]))
            title = " ".join(link.get_text().split())
            if "chitietvb" in href and len(title) > 12 and TITLE_MATCH.search(title):
                found.setdefault(href, title)
    return found


VNPT_SEARCH_TERMS = (
    "tổ chức lại thôn",
    "tổ chức lại tổ dân phố",
    "tổ chức lại xóm",
    "sắp xếp thôn",
    "sáp nhập thôn",
)


def search_vnpt(client: Client, base: str) -> dict[str, str]:
    """VNPT portals (ASP.NET WebForms): the document page has a search form keyed by the
    summary field (…$txtTrichYeu). The form is submitted as a browser would, with the hidden
    __VIEWSTATE fields it carries."""
    home = BeautifulSoup(client.page(base), "html.parser")
    index = next(
        (
            urljoin(base, str(a["href"]))
            for a in home.find_all("a", href=True)
            if str(a["href"]).rstrip("/").endswith(("he-thong-van-ban", "van-ban-tai-lieu"))
        ),
        urljoin(base, "he-thong-van-ban"),
    )
    found: dict[str, str] = {}
    for term in VNPT_SEARCH_TERMS:
        form = BeautifulSoup(client.page(index), "html.parser").find("form")
        if form is None:
            return found
        data = {
            str(i["name"]): str(i.get("value", ""))
            for i in form.find_all("input")
            if i.get("name") and i.get("type") not in ("submit", "button")
        }
        box = next((k for k in data if k.endswith("txtTrichYeu")), None)
        button = next(
            (
                str(i["name"])
                for i in form.find_all("input")
                if str(i.get("name", "")).endswith("btnSearch")
            ),
            None,
        )
        if not box or not button:
            return found
        for select in form.find_all("select"):
            option = select.find("option", selected=True) or select.find("option")
            data[str(select["name"])] = str(option.get("value", "")) if option else ""
        data[box], data[button] = term, "Tìm kiếm"
        result = BeautifulSoup(client.post(index, data), "html.parser")
        for link in result.find_all("a", href=True):
            title = " ".join(link.get_text().split())
            if "p_steering=" in str(link["href"]) and TITLE_MATCH.search(title):
                found.setdefault(urljoin(base, str(link["href"])), title)
    return found


def search(client: Client, state: dict[str, dict[str, object]]) -> None:
    for code, entry in sorted(state.items()):
        if "documents" in entry or entry.get("platform") not in (
            "van-ban-dieu-hanh",
            "vanban",
            "vnpt",
        ):
            continue
        base = str(entry["base"])
        if entry["platform"] == "van-ban-dieu-hanh":
            docs = search_van_ban_dieu_hanh(client, base)
        elif entry["platform"] == "vnpt":
            docs = search_vnpt(client, base)
        else:
            docs = search_vanban(client, base)
        entry["documents"] = [{"url": u, "title": t} for u, t in sorted(docs.items())]
        print(f"{code} {entry['name']:<20} {len(docs)} matching documents")


def attachments(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for tag in soup.find_all(["a", "iframe", "embed"]):
        ref = tag.get("href") or tag.get("src") or ""
        # VNPT pages also list other recent documents through a viewer/handler wrapper;
        # the document's own attachment is the direct link.
        if re.search(r"FileEntry\.ashx|docs\.google", str(ref), re.IGNORECASE):
            continue
        if re.search(r"\.(pdf|docx?)(\?|$)", str(ref), re.IGNORECASE):
            urls.append(urljoin(page_url, str(ref)))
    return sorted(set(urls))


def download(client: Client, state: dict[str, dict[str, object]]) -> None:
    for code, entry in sorted(state.items()):
        for doc in entry.get("documents", []):  # type: ignore[attr-defined]
            if "files" in doc:
                continue
            html = client.page(doc["url"])
            doc["files"] = []
            for url in attachments(html, doc["url"]):
                name = re.sub(r"[^\w.\-]+", "_", Path(httpx.URL(url).path).name)
                path = OUT_DIR / code / name
                if not path.exists():
                    response = client.get(url)
                    if response.status_code != 200:
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(response.content)
                doc["files"].append(
                    {
                        "url": url,
                        "path": path.as_posix(),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
            print(f"{code} {entry['name']:<20} {len(doc['files'])} files  {doc['title'][:70]}")


def main() -> int:
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state: dict[str, dict[str, object]] = (
        json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    )
    client = Client()
    try:
        if step in ("discover", "all"):
            discover(client, state)
        if step in ("search", "all"):
            search(client, state)
        if step in ("download", "all"):
            download(client, state)
    except Blocked as exc:
        print(f"STOPPED, the site refused automated requests: {exc}", file=sys.stderr)
        return 2
    finally:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
