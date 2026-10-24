import io
import re

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from apps.models import App, Review
from apps.pdf import build_reviews_pdf
from apps.scraper.service import run_search


@ensure_csrf_cookie
def index(request):
    """Single-page UI: search box, results, reviews."""
    return render(request, "apps/index.html")


@require_POST
def api_search(request):
    import json

    try:
        body = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid JSON"}, status=400)

    query = (body.get("query") or "").strip()
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)

    force = bool(body.get("force"))
    try:
        result = run_search(query, force=force)
    except Exception as exc:  # surface scrape errors to the UI
        return JsonResponse({"error": str(exc)}, status=500)

    return JsonResponse(result)


@require_GET
def api_reviews_bulk(request):
    """Reviews for several apps at once (comma-separated app_ids), merged."""
    raw = request.GET.get("app_ids") or ""
    app_ids = [a for a in (x.strip() for x in raw.split(",")) if a]
    if not app_ids:
        return JsonResponse({"error": "app_ids is required"}, status=400)
    return _reviews_response(request, app_ids)


@require_GET
def api_reviews(request, app_id):
    """Filtered reviews for one app: min/max star, optional date range."""
    return _reviews_response(request, [app_id])


def _filtered_reviews(request, app_ids):
    """Reviews for the given apps, narrowed by the request's filter params."""
    qs = Review.objects.filter(app_id__in=app_ids).select_related("app")

    def _num(name, default=None):
        # Stars may be fractional (2.1), so parse as float, not int.
        raw = request.GET.get(name)
        if raw in (None, ""):
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    min_star = _num("min_star", 1)
    max_star = _num("max_star", 5)
    if min_star is not None:
        qs = qs.filter(score__gte=min_star)
    if max_star is not None:
        qs = qs.filter(score__lte=max_star)

    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    if date_from:
        qs = qs.filter(at__date__gte=date_from)
    if date_to:
        qs = qs.filter(at__date__lte=date_to)

    app_version = request.GET.get("app_version")
    if app_version:
        qs = qs.filter(app_version=app_version)

    return qs.order_by("-at")


def _int_param(request, name, default=None):
    raw = request.GET.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _reviews_response(request, app_ids):
    """JSON payload of filtered reviews for one or more apps."""
    qs = _filtered_reviews(request, app_ids)
    total = qs.count()

    limit = min(_int_param(request, "limit", 100) or 100, 500)
    rows = [
        {
            "review_id": r.review_id,
            "app_id": r.app_id,
            "app_title": r.app.title,
            "score": r.score,
            "content": r.content,
            "at": r.at.isoformat() if r.at else None,
            "thumbs_up": r.thumbs_up,
            "app_version": r.app_version,
            "reply_content": r.reply_content,
        }
        for r in qs[:limit]
    ]

    return JsonResponse({
        "app_id": app_ids[0] if len(app_ids) == 1 else None,
        "app_ids": app_ids,
        "total": total,
        "returned": len(rows),
        "reviews": rows,
    })


@require_GET
def api_report_pdf(request):
    """PDF report of the reviews currently shown for the selected apps."""
    raw = request.GET.get("app_ids") or ""
    app_ids = [a for a in (x.strip() for x in raw.split(",")) if a]
    if not app_ids:
        return JsonResponse({"error": "app_ids is required"}, status=400)

    rows = list(_filtered_reviews(request, app_ids)[:5000])
    buf = build_reviews_pdf(request, app_ids, rows)
    resp = HttpResponse(buf.getvalue(), content_type="application/pdf")
    filename = _report_filename(request)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def _report_filename(request):
    """Slug of the user's search query, e.g. "Sober Tracker" -> sober_tracker_app_report.pdf.

    The query is attacker-controlled, so it is reduced to [a-z0-9_] and never
    interpolated into the header unsanitized.
    """
    query = (request.GET.get("query") or "").strip()
    slug = re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")
    if not slug:
        return "app_report.pdf"
    return f"{slug[:60]}_app_report.pdf"
