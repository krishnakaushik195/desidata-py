"""desidata — load Indian datasets from desidata.in in one line.

    import desidata

    df = desidata.load("gender-policy-of-nabard-question-and-answer-dataset")
    results = desidata.search("census")

The core install is dependency-free; `load()` needs pandas and raises a
helpful error telling you to install it if it is missing.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .client import (  # noqa: F401  (re-exports are the public API)
    DEFAULT_BASE_URL,
    __version__,
    base_url,
    cache_directory,
    clear_cache,
    fetch_catalog,
    fetch_csv_bytes,
    fetch_info,
    search_datasets,
)
from .client import (  # noqa: F401
    DesiDataConnectionError,
    DesiDataError,
    DesiDataNotFound,
    DesiDataServerError,
    DesiDataAuthenticationError,
    DesiDataPermissionError,
    DesiDataResponseError,
    DesiDataSignedUrlError,
)

__all__ = [
    "load",
    "download",
    "info",
    "search",
    "catalog",
    "clear_cache",
    "base_url",
    "cache_directory",
    "DEFAULT_BASE_URL",
    "__version__",
    "DesiDataError",
    "DesiDataConnectionError",
    "DesiDataNotFound",
    "DesiDataServerError",
    "DesiDataAuthenticationError",
    "DesiDataPermissionError",
    "DesiDataResponseError",
    "DesiDataSignedUrlError",
]


def load(
    slug: str,
    refresh: bool = False,
    timeout: Optional[float] = None,
    **pandas_kwargs: Any,
):
    """Load a dataset as a pandas DataFrame.

    `slug` may be a bare slug or a full desidata.in dataset URL. Extra keyword
    arguments pass straight through to `pandas.read_csv` (e.g. `dtype=`,
    `parse_dates=`). Loads are cached for 24 hours; pass `refresh=True` to
    re-download.
    """
    try:
        import pandas
    except ImportError as error:  # pragma: no cover - depends on environment
        raise ImportError(
            "desidata.load() needs pandas. Install it with: pip install pandas"
        ) from error

    data = fetch_csv_bytes(slug, refresh=refresh, timeout=timeout)
    return pandas.read_csv(io.BytesIO(data), **pandas_kwargs)


def download(
    slug: str,
    path: Optional[Union[str, Path]] = None,
    refresh: bool = False,
    timeout: Optional[float] = None,
) -> Union[bytes, Path]:
    """Download the raw CSV.

    With `path`, writes the file there and returns the Path; without it,
    returns the CSV bytes. Uses the same 24-hour cache as `load()`.
    """
    data = fetch_csv_bytes(slug, refresh=refresh, timeout=timeout)
    if path is None:
        return data
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return destination


def info(slug: str, timeout: Optional[float] = None) -> Dict[str, Any]:
    """Metadata for one dataset: name, description, format, size, downloads, tags."""
    return fetch_info(slug, timeout=timeout)


def search(query: str, timeout: Optional[float] = None) -> List[Dict[str, Any]]:
    """Search dataset titles and descriptions."""
    return search_datasets(query, timeout=timeout)


def catalog(
    category: Optional[str] = None,
    language: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """List every published dataset, optionally filtered."""
    return fetch_catalog(category=category, language=language, timeout=timeout)
