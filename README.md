# Ghost Job Radar

Scraping and modeling real job postings to flag the ones that are probably never going to result in a hire.

## Why

I've been job hunting since February and applied to 30+ roles across two application batches in August alone. Somewhere along the way I started wondering how many of those postings were ever real reqs versus postings kept up for pipeline-building, compliance, or optics. This project is an attempt to actually check, instead of just wondering.

## What it does

Every day, a scheduled job pulls current listings from a mix of sources:

- [RemoteOK's public API](https://remoteok.com/api) — a broad, messy, unmoderated feed (great for messy-data practice, plenty of spam/low-quality postings mixed in with real ones)
- [Greenhouse](https://developers.greenhouse.io/job-board.html) and [Lever](https://github.com/lever/postings-api) public job board APIs for a watchlist of companies (seeded from my own recent application list)

Each day's pull is:
1. Saved as a raw JSONL snapshot in `data/snapshots/` (so the exact daily data is visible in git history)
2. Upserted into `data/postings.db` (SQLite), which tracks each posting's `first_seen_date`, `last_seen_date`, and `removed_date` over time

Running this for several weeks builds a lifecycle history per posting — how long did it stay up, did it get quietly edited, did it disappear and reappear as a new listing under a different id — which is the raw material for the actual ghost-job classifier.

After each scrape, `scraper/find_reposts.py` runs entity resolution over the full posting history: same company + title similarity (token-sort ratio) + description similarity (TF-IDF cosine) + reappearance within 45 days flags a removed posting and a later one as a probable repost, written to a `repost_links` table. See `scraper/entity_resolution.py` for the matching logic and `tests/test_entity_resolution.py` for synthetic-data tests of it (real repost pairs take weeks of collection to show up, so the matching logic is tested independently of live data).

## Status

Data collection and repost detection are done. Labeling heuristics, the manual audit set, and the classifier come next, once there's enough lifecycle history to work with.

## Running it yourself

```
pip install -r requirements.txt
python -m scraper.run          # scrape + update lifecycle DB
python -m scraper.find_reposts # detect reposts from the current DB
python -m unittest discover -s tests
```

Requires real internet access (a sandboxed environment without outbound network access to job boards won't be able to run this — see `.github/workflows/scrape.yml` for how it runs automatically on a schedule instead).
