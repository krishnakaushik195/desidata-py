"""HTTP and cache layer. Everything network-facing lives here.

The package is deliberately dependency-free: only the standard library is
used, so `pip install desidata` works instantly everywhere. pandas stays an
optional import in the public API layer.
"""
from __future__ import annotations

import os
import json
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

__version__ = "0.1.1"

DEFAULT_BASE_URL = "https://www.desidata.in"
DEFAULT_TIMEOUT = 60.0
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60

_USER_AGENT = f"desidata-py/{__version__} (+https://www.desidata.in)"
_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class DesiDataError(Exception):
    """Base class for every error raised by this package."""


class DesiDataConnectionError(DesiDataError):
    """desidata.in could not be reached (network, DNS or timeout failure)."""


class DesiDataNotFound(DesiDataError):
    """The requested dataset does not exist (HTTP 404)."""


class DesiDataServerError(DesiDataError):
    """The server responded with an unexpected error."""


class DesiDataAuthenticationError(DesiDataError):
    """DD_TOKEN is missing, invalid or revoked."""


class DesiDataPermissionError(DesiDataError):
    """The token does not have permission to download this dataset."""


class DesiDataResponseError(DesiDataServerError):
    """The download API returned an invalid response."""


class DesiDataSignedUrlError(DesiDataError):
    """The storage link expired or was rejected; retry with refresh=True."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # urllib can forward Authorization across hosts. Reject redirects on both
    # requests, including HTTPS downgrades and redirects to the API itself.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _download_request(url: str, timeout_value: float, token: Optional[str] = None) -> bytes:
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/json" if token else "text/csv"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        # A new opener also avoids process-global cookie/auth handlers.
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=timeout_value) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        if token and status == 401:
            raise DesiDataAuthenticationError("DD_TOKEN is invalid or revoked. Create a new token in DesiData Profile & settings.") from None
        if token and status == 403:
            raise DesiDataPermissionError("DD_TOKEN does not have permission to download this dataset.") from None
        if token and status == 404:
            raise DesiDataNotFound("Dataset not found.") from None
        if not token and status in (400, 401, 403, 404, 410):
            raise DesiDataSignedUrlError("The signed download URL expired or was rejected. Retry with refresh=True to obtain a new link.") from None
        raise DesiDataServerError(f"{'Download API' if token else 'File storage'} returned HTTP {status}. Redirects are not followed.") from None
    except (urllib.error.URLError, OSError, ValueError):
        # Never include the URL, response body or underlying exception: storage
        # URLs are credentials and transport exceptions can contain them.
        raise DesiDataConnectionError("Could not complete the download request. Check your connection and retry.") from None


def _fetch_authenticated_csv(normalised: str, timeout_value: float) -> bytes:
    token = os.environ.get("DD_TOKEN", "").strip()
    if not token:
        raise DesiDataAuthenticationError("DD_TOKEN is missing. Create a free token in DesiData Profile & settings and set it in your environment or Colab Secrets.")
    if not re.fullmatch(r"dd_live_[A-Za-z0-9_-]{40,80}", token):
        raise DesiDataAuthenticationError("DD_TOKEN has an invalid format. Use a token from DesiData Profile & settings.")
    # Never trust DESIDATA_BASE_URL with a bearer credential. Catalogue-only
    # development overrides remain supported, but downloads use this origin.
    if base_url() != DEFAULT_BASE_URL:
        raise DesiDataAuthenticationError("Authenticated downloads require https://www.desidata.in. Unset DESIDATA_BASE_URL.")
    payload = _download_request(f"{DEFAULT_BASE_URL}/api/datasets/{normalised}/download", timeout_value, token)
    try:
        result = json.loads(payload)
        url = result.get("download_url") if isinstance(result, dict) else None
        if not isinstance(url, str) or not url or any(c.isspace() or ord(c) < 32 for c in url):
            raise ValueError()
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
        _ = parsed.port
    except (ValueError, UnicodeError):
        raise DesiDataResponseError("Download API returned malformed JSON or an invalid HTTPS download_url.") from None
    return _download_request(url, timeout_value)


def base_url() -> str:
    """API root, overridable with DESIDATA_BASE_URL (used by tests and dev)."""
    return (os.environ.get("DESIDATA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def cache_directory() -> Path:
    """Cache location, overridable with DESIDATA_CACHE_DIR."""
    directory = Path(os.environ.get("DESIDATA_CACHE_DIR") or Path.home() / ".desidata" / "cache")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def clear_cache() -> int:
    """Deletes every cached CSV. Returns the number of files removed."""
    removed = 0
    for path in cache_directory().glob("*.csv"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def _timeout(timeout: Optional[float]) -> float:
    if timeout is not None:
        return float(timeout)
    env = os.environ.get("DESIDATA_TIMEOUT")
    return float(env) if env else DEFAULT_TIMEOUT


def _normalise_slug(slug: str) -> str:
    """Accepts a slug, a dataset URL or a path and returns the bare slug.

    Students paste full URLs constantly, so 'https://www.desidata.in/datasets/
    crop-prices' and 'crop-prices' both work.
    """
    value = slug.strip()
    if ".." in value:
        raise ValueError(f"Invalid dataset slug: {slug!r}.")
    if "://" in value:
        value = value.split("://", 1)[1]
    if "/" in value:
        value = value.rstrip("/").rsplit("/", 1)[-1]
    value = value.strip().lower()
    if not _SLUG_PATTERN.match(value):
        raise ValueError(
            f"Invalid dataset slug: {slug!r}. Slugs look like 'crop-prices-2021' "
            "(lowercase letters, digits and dashes)."
        )
    return value


def _open(url: str, timeout_value: float, accept: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=timeout_value) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise DesiDataNotFound(f"Not found: {url}") from error
        raise DesiDataServerError(f"desidata.in returned HTTP {error.code} for {url}") from error
    except urllib.error.URLError as error:
        raise DesiDataConnectionError(f"Could not reach {url}: {error.reason}") from error


def _get_json(path: str, timeout: Optional[float]) -> Dict[str, Any]:
    payload = _open(f"{base_url()}{path}", _timeout(timeout), "application/json")
    import json

    return json.loads(payload.decode("utf-8"))


def fetch_info(slug: str, timeout: Optional[float] = None) -> Dict[str, Any]:
    """Metadata for one dataset: name, description, format, size, downloads, tags."""
    return _get_json(f"/api/datasets/{_normalise_slug(slug)}", timeout)


def fetch_catalog(
    category: Optional[str] = None,
    language: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Every published dataset, optionally filtered by category and language."""
    params = []
    if category:
        params.append(f"category={urllib.parse.quote(category)}")
    if language:
        params.append(f"language={urllib.parse.quote(language)}")
    path = "/api/datasets" + ("?" + "&".join(params) if params else "")
    response = _get_json(path, timeout)
    return response.get("datasets", [])


def search_datasets(query: str, timeout: Optional[float] = None) -> List[Dict[str, Any]]:
    """Catalogue search over titles and descriptions."""
    params = f"?query={urllib.parse.quote(query)}"
    response = _get_json(f"/api/datasets{params}", timeout)
    return response.get("datasets", [])


def fetch_csv_bytes(
    slug: str,
    refresh: bool = False,
    timeout: Optional[float] = None,
) -> bytes:
    """Raw CSV bytes for a dataset, served from the local cache when fresh.

    The cache lives in ~/.desidata/cache and entries expire after 24 hours.
    `refresh=True` bypasses and replaces the cached copy.
    """
    normalised = _normalise_slug(slug)
    path = cache_directory() / f"{normalised}.csv"

    if not refresh and path.exists():
        age = time.time() - path.stat().st_mtime
        if age < CACHE_MAX_AGE_SECONDS:
            return path.read_bytes()

    data = _fetch_authenticated_csv(normalised, _timeout(timeout))

    # Caching is best-effort: a read-only home directory must not break loads.
    try:
        fd, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    except OSError:
        pass

    return data
