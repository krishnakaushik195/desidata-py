"""CLI tests with API calls stubbed at the client boundary."""
from __future__ import annotations

import json

import pytest

from desidata import cli, client


@pytest.fixture()
def runner(capsys):
    def run(*argv):
        code = cli.main(list(argv))
        return code, capsys.readouterr().out

    return run


def test_cli_version_flag(runner):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0


def test_cli_info_prints_fields(runner, monkeypatch):
    monkeypatch.setattr(
        cli, "fetch_info", lambda slug: {"slug": slug, "name": "Prices", "downloads": 7}
    )
    code, out = runner("info", "prices")
    assert code == 0
    assert "prices" in out and "Prices" in out and "7" in out


def test_cli_search_prints_table(runner, monkeypatch):
    monkeypatch.setattr(
        cli,
        "search_datasets",
        lambda query: [{"slug": "crop-prices", "category": "Agriculture", "rows": 100, "title": "Crop"}],
    )
    code, out = runner("search", "crop")
    assert code == 0
    assert "crop-prices" in out and "Agriculture" in out


def test_cli_catalog_category_passthrough(runner, monkeypatch):
    seen = {}

    def fake_catalog(category=None):
        seen["category"] = category
        return []

    monkeypatch.setattr(cli, "fetch_catalog", fake_catalog)
    code, out = runner("catalog", "--category", "Economy")
    assert code == 0
    assert seen["category"] == "Economy"
    assert "No datasets found." in out


def test_cli_download_writes_file(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "fetch_csv_bytes", lambda slug, refresh=False: b"a,b\n1,2\n")
    output = tmp_path / "out.csv"
    code, out = runner("download", "some-slug", "-o", str(output))
    assert code == 0
    assert output.read_bytes() == b"a,b\n1,2\n"
    assert "8 bytes" in out


def test_cli_error_returns_1(runner, monkeypatch):
    def boom(slug):
        raise client.DesiDataNotFound("Not found: x")

    monkeypatch.setattr(cli, "fetch_info", boom)
    code, _ = runner("info", "x")
    assert code == 1


def test_cli_clear_cache(runner, monkeypatch):
    monkeypatch.setattr(cli, "clear_cache", lambda: 3)
    code, out = runner("clear-cache")
    assert code == 0
    assert "3" in out
