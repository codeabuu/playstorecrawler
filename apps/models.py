"""Data model.

Deliberately small: two tables. App is a cache of store metadata;
Review is the raw scrape. Everything the UI needs at query time lives
here, with scrape timestamps so staleness is a DB question, not a
memory question.

SQLite is used now. The only thing that would change on PostgreSQL is
JSONField internals (both support it natively) and index tuning.
"""

from django.db import models
from django.utils import timezone


class App(models.Model):
    """One Google Play app, keyed by its package id."""

    app_id = models.CharField(max_length=255, primary_key=True)
    title = models.CharField(max_length=512, blank=True, default="")
    developer = models.CharField(max_length=512, blank=True, default="")
    description = models.TextField(blank=True, default="")
    summary = models.TextField(blank=True, default="")
    category = models.CharField(max_length=128, blank=True, default="")
    icon = models.URLField(max_length=1024, blank=True, default="")

    score = models.FloatField(null=True, blank=True)
    ratings_count = models.IntegerField(null=True, blank=True)
    reviews_count = models.IntegerField(null=True, blank=True)
    installs = models.CharField(max_length=64, blank=True, default="")
    min_installs = models.IntegerField(null=True, blank=True)

    # Store-published 1..5 star histogram: index 0 is 1 star.
    histogram = models.JSONField(default=list, blank=True)

    # Cosine similarity to the search query's centroid (Phase A part 2).
    similarity = models.FloatField(null=True, blank=True)

    first_scraped_at = models.DateTimeField(default=timezone.now)
    metadata_scraped_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-similarity", "-ratings_count"]
        indexes = [models.Index(fields=["category"])]

    def __str__(self):
        return f"{self.title} ({self.app_id})"

    @property
    def histogram_total(self):
        return sum(self.histogram or [])


class Review(models.Model):
    """A single Play Store review record, raw.

    review_id comes from Play and is stable, so it is the primary key and
    re-scrapes are idempotent upserts.
    """

    review_id = models.CharField(max_length=128, primary_key=True)
    app = models.ForeignKey(App, on_delete=models.CASCADE, related_name="reviews")

    content = models.TextField(blank=True, default="")
    score = models.PositiveSmallIntegerField()  # 1..5
    at = models.DateTimeField()  # when the user posted it
    thumbs_up = models.IntegerField(default=0)
    app_version = models.CharField(max_length=64, blank=True, default="")
    review_created_version = models.CharField(max_length=64, blank=True, default="")

    reply_content = models.TextField(blank=True, default="")
    replied_at = models.DateTimeField(null=True, blank=True)

    user_name = models.CharField(max_length=255, blank=True, default="")

    scraped_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-at"]
        indexes = [
            # The hot path: filter by app + star range, order by date.
            models.Index(fields=["app", "score", "at"]),
            models.Index(fields=["app", "app_version"]),
        ]

    def __str__(self):
        return f"{self.app_id} {self.score}* {self.at:%Y-%m-%d}"
