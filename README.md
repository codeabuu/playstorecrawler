# Play Store Gap Research Tool

A small Django app for competitor research on Google Play: search for apps by keyword, get back the ones that are semantically closest to your query, then dig through their reviews (single app or several at once) and export a PDF report.

## What it does

- **Search** — scrapes Play Store search results for a query, ranks candidates by embedding similarity against the query, and stores the top matches.
- **Reviews** — pulls up to `REVIEWS_PER_APP` reviews per app and lets you filter them by star rating, date range, and app version.
- **Combined view** — select several apps and read their reviews together with a merged star histogram.
- **PDF export** — download a report for one app or a multi-app selection.
- **Caching** — scraped data is persisted in SQLite and reused for `SCRAPE_TTL_SECONDS` (12h by default); the *Re-scrape* button bypasses the cache.

## Requirements

- Python 3.10+ (developed on 3.12)
- No external database — SQLite is used by default
- Network access to Google Play when scraping (first search downloads the embedding model too, ~130 MB)

## Setup

1. Clone the repo and enter the project directory.

2. Create and activate a virtual environment:

   


3. Install dependencies:

   


4. Apply migrations (creates the local SQLite database):

   


5. (Optional) Create an admin user for the Django admin at `/admin/`:

   


6. Start the dev server:

   


Open http://127.0.0.1:8000/ and search for something like `sober tracker`.

On the very first search, `fastembed` downloads the `BAAI/bge-small-en-v1.5` ONNX model into `~/.cache/fastembed` (or `FASTEMBED_CACHE_PATH`). This can take a minute or two; later runs are local.

## Environment variables

All are optional; defaults are fine for local use. Set them in your shell or a `.env`-style loader of your choice.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | dev key | Django secret key — set a real one outside local dev |
| `DJANGO_DEBUG` | `1` | `0` disables debug mode |
| `PLAY_LANG` | `en` | Play Store language for scraping |
| `PLAY_COUNTRY` | `us` | Play Store country for scraping |
| `SEARCH_N_HITS` | `30` | Raw search hits considered as similarity candidates |
| `SIMILAR_MAX_APPS` | `8` | How many similar apps are shown |
| `SIMILAR_MIN_SCORE` | `0.55` | Minimum cosine similarity (0–1) to count as similar |
| `REVIEWS_PER_APP` | `400` | Reviews pulled per app |
| `SCRAPE_TTL_SECONDS` | `43200` | Cache TTL for scraped apps/reviews |
| `SCRAPE_MIN_INTERVAL` | `1.0` | Minimum seconds between Play Store calls |
| `SCRAPE_MAX_RETRIES` | `4` | Retry attempts for failed Play Store calls |
| `SCRAPE_BACKOFF_BASE` | `2.0` | Exponential backoff base |
| `EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model used for ranking |

## HTTP API

The UI is a single page, but the endpoints are usable on their own:

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/api/search` | JSON body `{"query": "...", "force": false}` |
| `GET` | `/api/reviews/<app_id>` | Query params: `min_star`, `max_star`, `date_from`, `date_to`, `app_version`, `limit` |
| `GET` | `/api/reviews` | Same params plus `app_ids` (comma-separated) |
| `GET` | `/api/reviews/report.pdf` | Same params, returns a PDF download |

Example:




## Tests

Tests are offline — Play Store responses are replayed from VCR cassettes in `apps/scraper/cassettes/`, so no network is needed:




`pytest.ini` already points at `config.settings` via `pytest-django`.

## Project layout

```
config/               Django settings, root URLs, WSGI/ASGI
apps/
  models.py           App + Review models
  views.py            JSON API + PDF endpoints
  pdf.py              ReportLab report generation
  urls.py             App routes
  templates/apps/     Single-page UI (index.html)
  scraper/
    play.py           Google Play scraping + politeness/retries
    service.py        Similarity ranking, persistence, cache logic
    cassettes/        Recorded HTTP for tests
requirements.txt
manage.py
```

## Troubleshooting

- **First search is slow** — the embedding model is downloading. Check your network / `FASTEMBED_CACHE_PATH`.
- **Search returns nothing** — try `force: true` (or the *Re-scrape* button) to bypass a stale cache, and widen `SIMILAR_MIN_SCORE` temporarily.
- **Scraping errors** — Google Play rate-limits; increase `SCRAPE_MIN_INTERVAL` and retry.
- **Port already in use** — `python manage.py runserver 8001`.

## Notes

- `DEBUG` defaults to on and `SECRET_KEY` is a dev placeholder. Do not deploy as-is.
- The scraper runs synchronously inside the request. Fine locally; move it to a task queue (Celery/Django-Q) before serving real traffic.
- Switching to PostgreSQL only requires changing `DATABASES` in `config/settings.py` (`psycopg2-binary` is already listed).
