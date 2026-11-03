"""Acquire the explicitly selected World Bank monthly workbook, unchanged."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


LANDING_URL = "https://www.worldbank.org/en/research/commodity-markets"
# Observed official Monthly prices link on the landing page, 2026-10-24.
MONTHLY_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)


def validate_official_url(url: str) -> None:
    """Reject non-HTTPS and non-World-Bank endpoints, including redirects."""
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"www.worldbank.org", "thedocs.worldbank.org"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise ValueError(f"Not an approved World Bank HTTPS endpoint: {url}")


class _OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str,
    ) -> Request | None:
        validate_official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download_monthly_snapshot(raw_root: Path, url: str = MONTHLY_URL) -> Path:
    """Download once per call into a new snapshot; never modify an old snapshot.

    The CLI calls this only with --download. Offline extraction never invokes it.
    The timestamp identifies retrieval, NOT historical publication/vintage dates.
    """
    validate_official_url(url)
    started = datetime.now(timezone.utc)
    request = Request(url, headers={"User-Agent": "FoodProcurementIntelligence/0.1"})
    with build_opener(_OfficialRedirects()).open(request, timeout=90) as response:
        final_url = response.geturl()
        validate_official_url(final_url)
        payload = response.read(20_000_001)
        headers = {
            key: response.headers.get(key)
            for key in ("Date", "Content-Type", "Content-Length", "Last-Modified", "ETag")
        }
        status = response.status
    retrieved = datetime.now(timezone.utc)
    if len(payload) > 20_000_000:
        raise ValueError("Workbook exceeds the 20 MB acquisition limit")
    if not payload.startswith(b"PK\x03\x04"):
        raise ValueError("Response is not an XLSX ZIP container; not saving as data")
    digest = hashlib.sha256(payload).hexdigest()
    snapshot_id = f"{retrieved:%Y%m%dT%H%M%S%fZ}_{digest[:12]}"
    directory = raw_root / snapshot_id
    directory.mkdir(parents=True, exist_ok=False)
    destination = directory / "CMO-Historical-Data-Monthly.xlsx"
    with destination.open("xb") as file:
        file.write(payload)
    manifest = {
        "snapshot_id": snapshot_id,
        "source": "World Bank Commodity Price Data (Pink Sheet)",
        "landing_url": LANDING_URL,
        "requested_url": url,
        "download_url": final_url,
        "filename": destination.name,
        "request_started_at_utc": started.isoformat(),
        "retrieved_at_utc": retrieved.isoformat(),
        "size_bytes": len(payload),
        "sha256": digest,
        "http_status": status,
        "response_headers": headers,
        "vintage_id": snapshot_id,
        "vintage_meaning": "retrieved snapshot, not original historical releases",
        "publication_timestamp": None,
        "license_url": "https://data.worldbank.org/summary-terms-of-use",
        "license_status": "World Bank default terms; workbook/provider notices must also be reviewed",
    }
    with (directory / "manifest.json").open("x", encoding="utf-8", newline="\n") as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return destination
