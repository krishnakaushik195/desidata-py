"""Live integration tests against the real desidata.in.

Skipped unless RUN_LIVE=1, so `pytest` stays offline-friendly:
    RUN_LIVE=1 pytest tests/test_live.py -v
"""
from __future__ import annotations

import os

import pytest

import desidata
from desidata import client

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE") != "1",
    reason="live tests are opt-in (RUN_LIVE=1)",
)

NABARD = "gender-policy-of-nabard-question-and-answer-dataset"


def test_live_info():
    metadata = desidata.info(NABARD)
    assert metadata["slug"] == NABARD
    assert metadata["format"].lower() == "csv"
    assert "download_url" in metadata


def test_live_catalog_is_large():
    datasets = desidata.catalog()
    assert len(datasets) > 100
    sample = datasets[0]
    for key in ("slug", "title", "category", "url"):
        assert key in sample


def test_live_search():
    results = desidata.search("nabard")
    assert any("nabard" in row["slug"] for row in results)


def test_live_load_dataframe():
    df = desidata.load(NABARD)
    assert df.shape[0] > 0
    assert "question" in df.columns


def test_live_download_bytes():
    data = desidata.download(NABARD)
    assert data[:4] in (b"ques", b"\"que")  # header starts with the question column
    assert b"," in data


def test_live_not_found():
    with pytest.raises(client.DesiDataNotFound):
        desidata.info("this-dataset-does-not-exist-12345")
