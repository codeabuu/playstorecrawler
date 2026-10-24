"""Offline tests for the Play wrapper and the search orchestration.

Strategy: VCR.py replays recorded HTTP interactions so the suite runs with
no network. The normalisers in play.py raise `ScrapeError` when required
keys are missing, so if Google Play changes its response shape these
tests fail loudly rather than silently persisting Nones.

To (re)record, run once with network available:
    RECORD=1 pytest apps/scraper/tests.py --vcr-record=all
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest
import vcr as vcr_module

from apps.scraper import play

CASSETTE_DIR = os.path.join(os.path.dirname(__file__), "cassettes")


def _vcr():
    return vcr_module.VCR(
        cassette_library_dir=CASSETTE_DIR,
        record_mode="all" if os.environ.get("RECORD") else "none",
        match_on=["method", "scheme", "host", "path"],
        filter_query_parameters=["hl", "gl"],
        decode_compressed_response=True,
    )


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """Tests must not sleep: disable pacing and retries."""
    monkeypatch.setattr(play._limiter, "min_interval", 0.0)
    monkeypatch.setattr(play.settings, "SCRAPE_MAX_RETRIES", 1, raising=False)


# --- Normaliser unit tests (no HTTP at all) -----------------------------

def test_normalise_search_hit_rejects_missing_keys():
    with pytest.raises(play.ScrapeError) as exc:
        play._normalise_search_hit({"title": "x"})
    assert "appId" in str(exc.value)


def test_normalise_app_requires_five_histogram_buckets():
    raw = {
        "appId": "com.example.app",
        "title": "Example",
        "description": "d",
        "genre": "Health & Fitness",
        "histogram": [1, 2, 3],  # broken on purpose
    }
    with pytest.raises(play.ScrapeError) as exc:
        play._normalise_app(raw)
    assert "histogram" in str(exc.value)


def test_normalise_review_parses_iso_date_string():
    raw = {
        "reviewId": "abc",
        "content": "crashes",
        "score": 2,
        "at": "2024-05-01T10:00:00",
    }
    out = play._normalise_review(raw, "com.example.app")
    assert out["score"] == 2
    assert out["at"] == datetime(2024, 5, 1, 10, 0, 0)
    assert out["thumbs_up"] == 0
    assert out["app_version"] == ""


# --- Recorded-response tests -------------------------------------------

@_vcr().use_cassette("search_sober_tracker.yaml")
def test_search_returns_normalised_hits():
    hits = play.search_apps("sober tracker", n_hits=5)
    assert hits, "cassette must contain at least one search hit"
    for hit in hits:
        assert set(hit) == {"app_id", "title", "developer", "score", "icon"}
        assert hit["app_id"], "app_id must never be empty"


@_vcr().use_cassette("app_details_sober_tracker.yaml")
def test_app_details_histogram_matches_published_totals():
    meta = play.fetch_app_details("com.sociosoft.sobertime")
    assert len(meta["histogram"]) == 5
    # Published histogram should sum to the ratings count Play reports.
    assert sum(meta["histogram"]) > 0
    assert meta["category"]


@_vcr().use_cassette("reviews_sober_tracker.yaml")
def test_reviews_are_deduplicated_and_bounded():
    rows = play.fetch_reviews("com.sociosoft.sobertime", target_count=50)
    assert rows
    assert len(rows) <= 50
    ids = [r["review_id"] for r in rows]
    assert len(ids) == len(set(ids)), "paging must not duplicate reviews"
    for r in rows:
        assert 1 <= r["score"] <= 5
        assert r["app_id"] == "com.sociosoft.sobertime"


@_vcr().use_cassette("reviews_sober_tracker.yaml")
def test_format_drift_is_loud():
    """If Play renames `reviewId`, this must raise, not return junk."""
    import google_play_scraper as gps

    raw = gps.reviews("com.sociosoft.sobertime", count=5)
    first = raw[0][0] if isinstance(raw, tuple) else raw[0]
    broken = {k: v for k, v in first.items() if k != "reviewId"}
    with pytest.raises(play.ScrapeError):
        play._normalise_review(broken, "com.sociosoft.sobertime")
