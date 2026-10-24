"""Thin, testable wrapper over google-play-scraper.

Rules for this module:
- No Django imports. Pure functions + one rate limiter object. This is
  what VCR.py records, and what moves to Celery unchanged later.
- Every Play call goes through RateLimiter.wait() and retries with
  exponential backoff on transient failures.
- Output is normalised to plain dicts with a fixed field set so a
  Play-side format change surfaces as a KeyError/assertion in tests
  rather than silently producing None everywhere.
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Any, Iterable

import google_play_scraper as gps
from django.conf import settings

logger = logging.getLogger(__name__)


class ScrapeError(RuntimeError):
    """Raised when Play returns something we cannot use after retries."""


class RateLimiter:
    """Enforces a minimum interval between calls, with jitter.

    A single process-wide instance is used by the service layer. Not
    thread-safe by design -- if we ever go concurrent, swap for a lock
    or move the pacing into the Celery worker.
    """

    def __init__(self, min_interval: float | None = None) -> None:
        self.min_interval = (
            settings.SCRAPE_MIN_INTERVAL if min_interval is None else min_interval
        )
        self._last: float = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last
        remaining = self.min_interval - elapsed
        if remaining > 0:
            # Jitter so a burst of app fetches does not look like a clock.
            time.sleep(remaining + random.uniform(0, 0.25))
        self._last = time.monotonic()


_limiter = RateLimiter()


def _with_retries(label: str, fn, *args, **kwargs):
    """Call fn, retrying transient errors with exponential backoff."""
    last_exc: Exception | None = None
    attempts = max(1, settings.SCRAPE_MAX_RETRIES)
    for attempt in range(1, attempts + 1):
        _limiter.wait()
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - Play raises many types
            last_exc = exc
            if attempt == attempts:
                break
            delay = settings.SCRAPE_BACKOFF_BASE ** attempt
            delay += random.uniform(0, 1.0)
            logger.warning(
                "%s failed (attempt %s/%s): %s; retrying in %.1fs",
                label, attempt, attempts, exc, delay,
            )
            time.sleep(delay)
    raise ScrapeError(f"{label} failed after {attempts} attempts: {last_exc}") from last_exc


# --- Normalisers --------------------------------------------------------
# Each takes the raw library dict and returns our fixed shape. If Play
# changes a key, these raise KeyError immediately -- which is exactly what
# the VCR tests assert against.

_REQUIRED_SEARCH_KEYS = ("appId", "title", "developer", "score", "icon")


def _normalise_search_hit(raw: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in _REQUIRED_SEARCH_KEYS if k not in raw]
    if missing:
        raise ScrapeError(f"search hit missing keys {missing}: {sorted(raw)}")
    return {
        "app_id": raw["appId"],
        "title": raw.get("title") or "",
        "developer": raw.get("developer") or "",
        "score": raw.get("score"),
        "icon": raw.get("icon") or "",
    }


_REQUIRED_APP_KEYS = ("appId", "title", "description", "histogram", "genre")


def _normalise_app(raw: dict[str, Any]) -> dict[str, Any]:
    missing = [k for k in _REQUIRED_APP_KEYS if k not in raw]
    if missing:
        raise ScrapeError(f"app detail missing keys {missing}: {sorted(raw)}")
    histogram = raw.get("histogram") or []
    if len(histogram) != 5:
        raise ScrapeError(
            f"histogram for {raw['appId']} has {len(histogram)} buckets, expected 5"
        )
    return {
        "app_id": raw["appId"],
        "title": raw.get("title") or "",
        "developer": raw.get("developer") or "",
        "description": raw.get("description") or "",
        "summary": raw.get("summary") or "",
        "category": raw.get("genre") or "",
        "icon": raw.get("icon") or "",
        "score": raw.get("score"),
        "ratings_count": raw.get("ratings"),
        "reviews_count": raw.get("reviews"),
        "installs": raw.get("installs") or "",
        "min_installs": raw.get("minInstalls"),
        "histogram": [int(x) for x in histogram],
    }


_REQUIRED_REVIEW_KEYS = ("reviewId", "content", "score", "at")


def _normalise_review(raw: dict[str, Any], app_id: str) -> dict[str, Any]:
    missing = [k for k in _REQUIRED_REVIEW_KEYS if k not in raw]
    if missing:
        raise ScrapeError(f"review missing keys {missing}: {sorted(raw)}")
    at = raw["at"]
    if isinstance(at, str):
        at = datetime.fromisoformat(at)
    return {
        "review_id": raw["reviewId"],
        "app_id": app_id,
        "content": raw.get("content") or "",
        "score": int(raw["score"]),
        "at": at,
        "thumbs_up": int(raw.get("thumbsUpCount") or 0),
        "app_version": raw.get("appVersion") or "",
        "review_created_version": raw.get("reviewCreatedVersion") or "",
        "reply_content": raw.get("replyContent") or "",
        "replied_at": raw.get("repliedAt"),
        "user_name": raw.get("userName") or "",
    }


# --- Public API ---------------------------------------------------------

def search_apps(query: str, n_hits: int | None = None) -> list[dict[str, Any]]:
    """Raw Play search. Returns candidate apps, not a similarity verdict."""
    hits = n_hits if n_hits is not None else settings.SEARCH_N_HITS
    raw = _with_retries(
        f"search({query!r})",
        gps.search,
        query,
        n_hits=hits,
        lang=settings.PLAY_LANG,
        country=settings.PLAY_COUNTRY,
    )
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw or []:
        norm = _normalise_search_hit(item)
        if norm["app_id"] in seen:
            continue
        seen.add(norm["app_id"])
        out.append(norm)
    return out


def fetch_app_details(app_id: str) -> dict[str, Any]:
    raw = _with_retries(
        f"app({app_id})",
        gps.app,
        app_id,
        lang=settings.PLAY_LANG,
        country=settings.PLAY_COUNTRY,
    )
    return _normalise_app(raw)


def fetch_reviews(
    app_id: str,
    target_count: int | None = None,
) -> list[dict[str, Any]]:
    """Page through reviews until target_count or Play runs dry.

    sort=NEWEST on purpose: Play's default (MOST_RELEVANT) is a
    curator-ranked subset, which biases theme extraction. NEWEST is the
    most chronological/complete slice the public endpoint offers.
    """
    target = target_count if target_count is not None else settings.REVIEWS_PER_APP
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    token = None
    page_size = 200

    while len(collected) < target:
        want = min(page_size, target - len(collected))
        page, token = _with_retries(
            f"reviews({app_id}, want={want})",
            gps.reviews,
            app_id,
            lang=settings.PLAY_LANG,
            country=settings.PLAY_COUNTRY,
            sort=gps.Sort.NEWEST,
            count=want,
            continuation_token=token,
        )
        if not page:
            break
        for item in page:
            norm = _normalise_review(item, app_id)
            if norm["review_id"] in seen:
                continue
            seen.add(norm["review_id"])
            collected.append(norm)
        if token is None:
            break

    return collected[:target]


def iter_reviews(app_id: str, target_count: int) -> Iterable[dict[str, Any]]:
    """Convenience wrapper so callers do not need to know about paging."""
    yield from fetch_reviews(app_id, target_count)
