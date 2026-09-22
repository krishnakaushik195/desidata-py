"""Unit tests with the network fully mocked out."""
from __future__ import annotations

import json
import urllib.error

import pytest

from desidata import client


class FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture()
def cache_dir(tmp_path, monkeypatch):
    directory = tmp_path / "cache"
    directory.mkdir()
    monkeypatch.setenv("DESIDATA_CACHE_DIR", str(directory))
    return directory


def test_version_is_exported():
    assert client.__version__.count(".") == 2


def test_normalise_slug_accepts_bare_slug():
    assert client._normalise_slug("crop-prices-2021") == "crop-prices-2021"


def test_normalise_slug_accepts_full_url():
    url = "https://www.desidata.in/datasets/gender-policy-of-nabard-question-and-answer-dataset"
    assert client._normalise_slug(url) == "gender-policy-of-nabard-question-and-answer-dataset"


def test_normalise_slug_rejects_traversal():
    with pytest.raises(ValueError):
        client._normalise_slug("../../etc/passwd")


def test_fetch_info_parses_json(monkeypatch):
    payload = {"slug": "x", "name": "X", "downloads": 5}
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = client.fetch_info("x")

    assert result == payload
    assert calls == ["https://www.desidata.in/api/datasets/x"]


def test_fetch_info_404_raises_not_found(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", None, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(client.DesiDataNotFound):
        client.fetch_info("missing-slug")


def test_urlerror_maps_to_connection_error(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(client.DesiDataConnectionError):
        client.fetch_info("any-slug")


def test_fetch_catalog_builds_filter_url(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return FakeResponse(json.dumps({"count": 1, "datasets": [{"slug": "a"}]}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = client.fetch_catalog(category="Economy", language="English")

    assert result == [{"slug": "a"}]
    assert "category=Economy" in calls[0]
    assert "language=English" in calls[0]


def test_fetch_csv_bytes_caches(monkeypatch, cache_dir):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return FakeResponse(b"col1,col2\n1,2\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    first = client.fetch_csv_bytes("some-dataset")
    second = client.fetch_csv_bytes("some-dataset")

    assert first == second == b"col1,col2\n1,2\n"
    assert len(calls) == 1  # second call came from cache
    assert (cache_dir / "some-dataset.csv").exists()


def test_fetch_csv_bytes_refresh_bypasses_cache(monkeypatch, cache_dir):
    calls = []

    def fake_urlopen(request, timeout=None):
        calls.append(request.full_url)
        return FakeResponse(b"a\n1\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    client.fetch_csv_bytes("some-dataset")
    client.fetch_csv_bytes("some-dataset", refresh=True)

    assert len(calls) == 2


def test_clear_cache_counts_removals(monkeypatch, cache_dir):
    for slug in ("one", "two"):
        (cache_dir / f"{slug}.csv").write_bytes(b"a\n")
    assert client.clear_cache() == 2
    assert not list(cache_dir.glob("*.csv"))
