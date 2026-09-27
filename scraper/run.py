#!/usr/bin/env python3
"""
Daily entrypoint: fetch every source, upsert into the lifecycle DB, and
write a dated JSONL snapshot (so the raw daily pull is visible in git
history even if the DB logic changes later).

Usage: python -m scraper.run
Meant to be invoked by .github/workflows/scrape.yml on a daily cron.
"""

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from scraper import sources
from scraper.companies import WATCHLIST
from scraper.db import get_connection, upsert_postings

DATA_DIR = Path(__file__).parent.parent / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"


def collect_all():
    all_postings = []
    errors = []

    try:
        remoteok = sources.fetch_remoteok()
        all_postings.extend(remoteok)
        print(f"[remoteok] {len(remoteok)} postings")
    except Exception as e:
        errors.append(f"remoteok: {e}")
        print(f"[remoteok] FAILED: {e}", file=sys.stderr)

    for company_name, gh_slug, lever_slug in WATCHLIST:
        if gh_slug:
            try:
                jobs = sources.fetch_greenhouse(company_name, gh_slug)
                all_postings.extend(jobs)
                print(f"[greenhouse:{gh_slug}] {len(jobs)} postings")
            except Exception as e:
                errors.append(f"greenhouse:{gh_slug}: {e}")
                print(f"[greenhouse:{gh_slug}] FAILED: {e}", file=sys.stderr)

        if lever_slug:
            try:
                jobs = sources.fetch_lever(company_name, lever_slug)
                all_postings.extend(jobs)
                print(f"[lever:{lever_slug}] {len(jobs)} postings")
            except Exception as e:
                errors.append(f"lever:{lever_slug}: {e}")
                print(f"[lever:{lever_slug}] FAILED: {e}", file=sys.stderr)

    return all_postings, errors


def main():
    scrape_date = date.today().isoformat()
    print(f"=== ghost-job-radar scrape: {scrape_date} ===")

    postings, errors = collect_all()
    print(f"Total normalized postings this run: {len(postings)}")
    if errors:
        print(f"{len(errors)} source(s) failed this run (see stderr above); continuing with what succeeded.")

    # 1. Dated JSONL snapshot -- raw record of exactly what we saw today.
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOT_DIR / f"{scrape_date}.jsonl"
    with open(snapshot_path, "w") as f:
        for p in postings:
            f.write(json.dumps(p) + "\n")
    print(f"Wrote snapshot: {snapshot_path}")

    # 2. Lifecycle DB -- upsert so we can track first_seen/last_seen/removed over time.
    conn = get_connection()
    upsert_postings(conn, postings, scrape_date)
    conn.close()
    print("Upserted into data/postings.db")

    print(f"Run complete at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
