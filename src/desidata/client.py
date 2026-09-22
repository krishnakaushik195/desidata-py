"""HTTP and cache layer. Everything network-facing lives here.

The package is deliberately dependency-free: only the standard library is
used, so `pip install desidata` works instantly everywhere. pandas stays an
optional import in the public API layer.
"""
from __future__ import annotations

import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

__version__ = "0.1.0"

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

    data = _open(f"{base_url()}/api/datasets/{normalised}/download", _timeout(timeout), "text/csv")

    # Caching is best-effort: a read-only home directory must not break loads.
    try:
        fd, temporary = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    except OSError:
        pass

    return data
