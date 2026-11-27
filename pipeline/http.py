"""HTTP access for the pipeline, following a four-tier download policy.

1. Official source, valid TLS.                                  tier 1, tls_verified True
2. Official source with a broken certificate, only for hosts      tier 2, tls_verified False
   listed in TLS_EXCEPTIONS, each one reviewed before it is added.
3. Internet Archive copy, when the official page is gone.        tier 3, evidence archived_official
4. Never: impersonating users to get past bot protection, solving CAPTCHAs, rotating proxies.
   A 403/429 or a CAPTCHA page raises Blocked and the caller must stop.

Every successful fetch returns its provenance so that it can be written to a manifest.
"""

from __future__ import annotations

import fnmatch
import hashlib
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import certifi
import httpx

USER_AGENT = "vn-addr-pipeline/0.1 (+research; legal documents only)"
INTERMEDIATES = Path(__file__).parent / "certs" / "globalsign-rsa-ov-ssl-ca-2018.pem"

# Hosts whose certificate may be invalid. The *.namdinh.gov.vn portals are served through a
# FortiGate that re-signs them with its own expired certificate (checked 2026-11-26).
TLS_EXCEPTIONS: tuple[str, ...] = ("namdinh.gov.vn", "*.namdinh.gov.vn")

WAYBACK_AVAILABLE = "https://archive.org/wayback/available"
WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
DELAY = 1.0


class Blocked(RuntimeError):
    """The site refused automated access: the fetch stops, and the document needs another
    source or a decision made by hand."""


class NotFound(RuntimeError):
    """No tier could provide the URL."""


@dataclass
class Fetched:
    url: str
    content: bytes
    content_type: str
    provenance: dict[str, object] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


def ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cafile=INTERMEDIATES)
    return context


def tls_exception(host: str) -> bool:
    return any(fnmatch.fnmatch(host, pattern) for pattern in TLS_EXCEPTIONS)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Http:
    def __init__(self, delay: float = DELAY, archive: bool = True) -> None:
        options: dict[str, object] = {
            "headers": {"User-Agent": USER_AGENT},
            "follow_redirects": True,
            "timeout": 60,
        }
        self.verified = httpx.Client(verify=ssl_context(), **options)  # type: ignore[arg-type]
        self.unverified = httpx.Client(verify=False, **options)  # type: ignore[arg-type]
        self.delay = delay
        self.archive = archive
        self.last = 0.0

    def _pace(self) -> None:
        wait = self.delay - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()

    def _get(self, client: httpx.Client, url: str, **kw: object) -> httpx.Response:
        for attempt in range(4):
            self._pace()
            response = client.get(url, **kw)  # type: ignore[arg-type]
            # The Internet Archive rate-limits with 429 and Retry-After: wait, as it asks.
            if (
                response.status_code == 429
                and response.url.host.endswith("archive.org")
                and attempt < 3
            ):
                time.sleep(min(int(response.headers.get("retry-after", "60")), 300))
                continue
            break
        if response.status_code in (403, 429) or b"captcha" in response.content[:5000].lower():
            raise Blocked(f"{response.status_code} on {response.url}")
        return response

    def get(self, url: str, params: dict[str, str] | None = None) -> Fetched:
        host = httpx.URL(url).host
        try:
            response = self._get(self.verified, url, params=params)
            if response.status_code == 200:
                return self._result(response, tier=1, tls_verified=True)
        except httpx.ConnectError as exc:
            if "CERTIFICATE_VERIFY_FAILED" in str(exc) and tls_exception(host):
                try:
                    response = self._get(self.unverified, url, params=params)
                    if response.status_code == 200:
                        return self._result(response, tier=2, tls_verified=False)
                except httpx.HTTPError:
                    pass
        except httpx.HTTPError:
            pass
        if self.archive and params is None:
            return self.from_archive(url)
        raise NotFound(url)

    def from_archive(self, url: str, timestamp: str = "") -> Fetched:
        self._pace()
        query = {"url": url, **({"timestamp": timestamp} if timestamp else {})}
        info = self.verified.get(WAYBACK_AVAILABLE, params=query).json()
        snapshot = info.get("archived_snapshots", {}).get("closest")
        if not snapshot or not snapshot.get("available"):
            raise NotFound(f"{url} (no Internet Archive copy)")
        stamp = snapshot["timestamp"]
        raw = f"https://web.archive.org/web/{stamp}id_/{url}"
        response = self._get(self.verified, raw)
        if response.status_code != 200:
            raise NotFound(f"{url} (archive returned {response.status_code})")
        result = self._result(response, tier=3, tls_verified=True)
        result.provenance.update(
            original_url=url,
            archive_url=f"https://web.archive.org/web/{stamp}/{url}",
            archived_at=datetime.strptime(stamp, "%Y%m%d%H%M%S")
            .replace(tzinfo=timezone.utc)
            .isoformat(),
            evidence="archived_official",
        )
        return result

    def archived_urls(self, prefix: str, mimetype: str = "", limit: int = 2000) -> list[str]:
        """Original URLs the Internet Archive holds under a prefix (CDX API)."""
        self._pace()
        params = {
            "url": prefix,
            "output": "json",
            "fl": "original,mimetype,statuscode",
            "collapse": "urlkey",
            "limit": str(limit),
        }
        rows = self.verified.get(WAYBACK_CDX, params=params, timeout=120).json()
        out = []
        for original, mime, status in rows[1:]:
            if status == "200" and (not mimetype or mime == mimetype):
                out.append(original)
        return out

    @staticmethod
    def _result(response: httpx.Response, tier: int, tls_verified: bool) -> Fetched:
        return Fetched(
            url=str(response.url),
            content=response.content,
            content_type=response.headers.get("content-type", ""),
            provenance={
                "tier": tier,
                "tls_verified": tls_verified,
                "url": str(response.url),
                "sha256": hashlib.sha256(response.content).hexdigest(),
                "bytes": len(response.content),
                "fetched_at": now(),
            },
        )
