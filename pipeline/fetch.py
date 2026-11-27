"""Download the source documents into data/raw/ and record them in data/raw/manifest.json.

Run with: uv run python -m pipeline.fetch [kind ...]

With kinds (e.g. ward_resolution), only sources of those kinds are fetched. A document already
in the manifest whose files are all on disk is not downloaded again.

For each source this saves the signed PDF and every PDF/DOC file the Official Gazette page
offers for download. If a download fails (network blocked, site refusing automated clients),
the script reports it and asks for the file to be downloaded by hand. It never retries through
mirrors or proxies, and it never turns off TLS verification.

The gazette's download host (g7.cdnchinhphu.vn) does not send its intermediate certificate.
The intermediate, GlobalSign RSA OV SSL CA 2018, is taken from GlobalSign's own AIA URL and kept
in pipeline/certs/; it is added to the default trust store so the chain still has to verify up
to the GlobalSign root.
"""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import certifi
import httpx
from bs4 import BeautifulSoup

from pipeline.sources import Source, all_sources

RAW_DIR = Path("data/raw")
MANIFEST = RAW_DIR / "manifest.json"
INTERMEDIATES = Path(__file__).parent / "certs" / "globalsign-rsa-ov-ssl-ca-2018.pem"
USER_AGENT = "vn-addr-pipeline/0.0 (+research; legal documents only)"
GAZETTE_DOWNLOAD = re.compile(r"/api/download/stream\?")


def ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=INTERMEDIATES)
    return context


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name).strip("_")


def gazette_files(page_html: str) -> list[tuple[str, str]]:
    """Return (url, file name) for every download link on a Công báo document page."""
    soup = BeautifulSoup(page_html, "html.parser")
    found: dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        if GAZETTE_DOWNLOAD.search(href):
            name = httpx.URL(href).params.get("file_name", "")
            if name.lower().endswith((".pdf", ".doc", ".docx")):
                found[href] = safe_name(name)
    return sorted(found.items(), key=lambda item: item[1])


def save(client: httpx.Client, url: str, path: Path, role: str) -> dict[str, object]:
    time.sleep(1)  # one request a second
    response = client.get(url)
    response.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return {
        "role": role,
        "tier": 1,  # official source, TLS verified (download tiers: pipeline/http.py)
        "url": url,
        "path": path.as_posix(),
        "content_type": response.headers.get("content-type", ""),
        "bytes": len(response.content),
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fetch(source: Source, client: httpx.Client) -> dict[str, object]:
    folder = RAW_DIR / source.scope
    files = []
    if source.signed_pdf:
        files.append(
            save(
                client,
                source.signed_pdf,
                folder / Path(httpx.URL(source.signed_pdf).path).name,
                "signed_scan",
            )
        )
    if source.gazette_page:  # some documents are published only as a signed scan
        time.sleep(1)
        page = client.get(source.gazette_page)
        page.raise_for_status()
        links = gazette_files(page.text)
        if not links:
            raise httpx.HTTPError(f"no PDF/DOC download link found on {source.gazette_page}")
        for url, name in links:
            files.append(save(client, url, folder / f"gazette_{name}", "gazette_text"))
    return {
        "doc_id": source.doc_id,
        "kind": source.kind,
        "scope": source.scope,
        "title": source.title,
        "landing_page": source.landing_page,
        "gazette_page": source.gazette_page,
        "files": files,
    }


def main() -> int:
    manifest: dict[str, object] = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failed: list[tuple[Source, str]] = []
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=120,
        verify=ssl_context(),
    ) as client:
        kinds = set(sys.argv[1:])
        for source in all_sources():
            if kinds and source.kind not in kinds:
                continue
            done = manifest.get(source.doc_id)
            if done and all(Path(f["path"]).exists() for f in done["files"]):  # type: ignore[index]
                continue
            try:
                entry = fetch(source, client)
            except httpx.HTTPError as exc:
                failed.append((source, str(exc)))
                continue
            manifest[source.doc_id] = entry
            for file in entry["files"]:  # type: ignore[attr-defined]
                print(f"ok   {source.doc_id:<18} {file['bytes']:>9} B  {file['path']}")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for source, error in failed:
        print(f"FAIL {source.doc_id}: {error}", file=sys.stderr)
        print(f"     download by hand into {RAW_DIR / source.scope}/", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
