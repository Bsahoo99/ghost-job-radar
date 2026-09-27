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

Separately, `scraper/build_audit_set.py` samples postings into `data/audit_set.csv` for hand-labeling (real / likely_ghost / unsure). This -- not the heuristic labels above -- is what the classifier's precision/recall eventually gets reported against, so it needs an actual person's judgment on a real cross-section of postings. Sampling is stratified by source and capped per company so it isn't dominated by whichever company happens to have the most open reqs, and re-running the tool only adds new postings on top of whatever's already been labeled -- it never touches or re-samples a row that's already been hand-labeled.

## Status

Data collection, repost detection, and the audit-set sampling tool are done. Filling in the audit set by hand, exact labeling-heuristic thresholds, feature engineering, and the classifier come next.

## Running it yourself

```
pip install -r requirements.txt
python -m scraper.run             # scrape + update lifecycle DB
python -m scraper.find_reposts    # detect reposts from the current DB
python -m scraper.build_audit_set # sample postings into data/audit_set.csv for hand-labeling
python -m unittest discover -s tests
```

Requires real internet access (a sandboxed environment without outbound network access to job boards won't be able to run this — see `.github/workflows/scrape.yml` for how it runs automatically on a schedule instead).
