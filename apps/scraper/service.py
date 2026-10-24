"""Search orchestration: scrape -> persist -> rank by similarity.

This is the one place that knows about both Django and the network.
The Phase-B API view calls `run_search()`; Phase C's theme builder reads
Review rows straight from the DB.

Similarity rule (documented because the user asked for the rule):
  1. Candidate set = raw Play search hits for the query. Play's ranking
     is a relevance prior, not our answer.
  2. Embed each candidate's `title. summary description` (capped length).
  3. Also embed the query string, but the centroid is computed over the
     candidates: `centroid = normalize(mean(candidate_embeddings))`.
     Rationale: a short query like "sober tracker" embeds poorly; the
     mean of what Play thinks matches it is a much better anchor, and
     it naturally penalises apps that only matched on one keyword.
  4. similarity = cosine(candidate, centroid), clamped to [0, 1].
  5. Keep candidates >= SIMILAR_MIN_SCORE, sort desc, cap at
     SIMILAR_MAX_APPS. The first hit (Play's top result) is always kept
     so the user never gets an empty screen from a quirky query.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.models import App, Review

from .play import ScrapeError, fetch_app_details, fetch_reviews, search_apps

logger = logging.getLogger(__name__)


class Embedder:
    """Lazy fastembed wrapper. Imported lazily so scraper tests don't need ONNX."""

    _model = None

    @classmethod
    def model(cls):
        if cls._model is None:
            from fastembed import TextEmbedding

            cls._model = TextEmbedding(model_name=settings.EMBED_MODEL)
        return cls._model

    @classmethod
    def embed(cls, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [list(map(float, v)) for v in cls.model().embed(texts)]


def _cosine(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _centroid(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    n = len(vectors)
    dim = len(vectors[0])
    acc = [0.0] * dim
    for v in vectors:
        for i in range(dim):
            acc[i] += v[i]
    return [x / n for x in acc]


def _doc_text(title: str, summary: str, description: str) -> str:
    # Title and summary are the highest-signal fields; description is
    # long and drifts into marketing. Truncate so one verbose listing
    # cannot dominate the centroid.
    return "\n".join(p for p in (title, summary, description[:1200]) if p)


def rank_by_similarity(query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach `similarity` to each candidate and return sorted+filtered."""
    if not candidates:
        return []
    docs = [
        _doc_text(c.get("title", ""), c.get("summary", ""), c.get("description", ""))
        for c in candidates
    ]
    vecs = Embedder.embed(docs)
    centre = _centroid(vecs)

    scored: list[dict[str, Any]] = []
    for cand, vec in zip(candidates, vecs):
        sim = max(0.0, min(1.0, _cosine(vec, centre)))
        scored.append({**cand, "similarity": round(sim, 4)})

    scored.sort(key=lambda c: c["similarity"], reverse=True)

    top_id = scored[0]["app_id"]
    kept = [c for c in scored if c["similarity"] >= settings.SIMILAR_MIN_SCORE]
    if not any(c["app_id"] == top_id for c in kept):
        kept.append(scored[0])
    return kept[: settings.SIMILAR_MAX_APPS]


def _is_fresh(app: App) -> bool:
    ttl = timedelta(seconds=settings.SCRAPE_TTL_SECONDS)
    return app.metadata_scraped_at >= timezone.now() - ttl


@transaction.atomic
def _persist_app(meta: dict[str, Any], similarity: float | None) -> App:
    app, _ = App.objects.update_or_create(
        app_id=meta["app_id"],
        defaults={
            "title": meta["title"],
            "developer": meta["developer"],
            "description": meta["description"],
            "summary": meta["summary"],
            "category": meta["category"],
            "icon": meta["icon"],
            "score": meta["score"],
            "ratings_count": meta["ratings_count"],
            "reviews_count": meta["reviews_count"],
            "installs": meta["installs"],
            "min_installs": meta["min_installs"],
            "histogram": meta["histogram"],
            "similarity": similarity,
            "metadata_scraped_at": timezone.now(),
        },
    )
    return app


def _persist_reviews(app: App, rows: list[dict[str, Any]]) -> int:
    objs = []
    for r in rows:
        objs.append(
            Review(
                review_id=r["review_id"],
                app=app,
                content=r["content"],
                score=r["score"],
                at=r["at"],
                thumbs_up=r["thumbs_up"],
                app_version=r["app_version"],
                review_created_version=r["review_created_version"],
                reply_content=r["reply_content"],
                replied_at=r["replied_at"],
                user_name=r["user_name"],
                scraped_at=timezone.now(),
            )
        )
    Review.objects.bulk_create(objs, ignore_conflicts=True, batch_size=500)
    return len(objs)


def run_search(query: str, *, force: bool = False) -> dict[str, Any]:
    """Full pipeline for one query. Returns a serialisable summary.

    Caching: if every app for this query was scraped within TTL, no
    network calls happen (force=True bypasses). Similarity is recomputed
    each time only when new candidates appear, because it is cheap
    relative to network I/O and the centroid can shift.
    """
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")

    hits = search_apps(query)
    if not hits:
        return {"query": query, "apps": [], "warnings": ["No Play Store results."]}

    # Enrich: search hits lack description/summary/histogram.
    enriched: list[dict[str, Any]] = []
    warnings: list[str] = []
    for hit in hits:
        existing = App.objects.filter(app_id=hit["app_id"]).first()
        if existing and _is_fresh(existing) and not force:
            enriched.append(
                {
                    "app_id": existing.app_id,
                    "title": existing.title,
                    "developer": existing.developer,
                    "description": existing.description,
                    "summary": existing.summary,
                    "category": existing.category,
                    "icon": existing.icon,
                    "score": existing.score,
                    "ratings_count": existing.ratings_count,
                    "reviews_count": existing.reviews_count,
                    "installs": existing.installs,
                    "min_installs": existing.min_installs,
                    "histogram": existing.histogram,
                }
            )
            continue
        try:
            enriched.append(fetch_app_details(hit["app_id"]))
        except ScrapeError as exc:
            warnings.append(f"Skipped {hit['app_id']}: {exc}")
            logger.warning("detail scrape failed for %s: %s", hit["app_id"], exc)

    ranked = rank_by_similarity(query, enriched)

    saved: list[App] = []
    for cand in ranked:
        app = _persist_app(cand, cand.get("similarity"))
        saved.append(app)

        # Reviews: only scrape when stale or empty.
        fresh = (
            not force
            and _is_fresh(app)
            and app.reviews.exists()
        )
        if fresh:
            continue
        try:
            rows = fetch_reviews(app.app_id)
        except ScrapeError as exc:
            warnings.append(f"Reviews failed for {app.app_id}: {exc}")
            continue
        n = _persist_reviews(app, rows)
        logger.info("stored %s reviews for %s", n, app.app_id)

    return {
        "query": query,
        "apps": [
            {
                "app_id": a.app_id,
                "title": a.title,
                "developer": a.developer,
                "category": a.category,
                "icon": a.icon,
                "score": a.score,
                "ratings_count": a.ratings_count,
                "installs": a.installs,
                "histogram": a.histogram,
                "similarity": a.similarity,
                "review_count": a.reviews.count(),
                "metadata_scraped_at": a.metadata_scraped_at.isoformat(),
            }
            for a in saved
        ],
        "warnings": warnings,
    }
