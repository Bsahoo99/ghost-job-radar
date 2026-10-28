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


FETCHERS = {
    "greenhouse": sources.fetch_greenhouse,
    "lever": sources.fetch_lever,
    "ashby": sources.fetch_ashby,
}


def collect_all():
    """Fetch every watchlist board.

    Returns (postings, fetched_boards, errors). fetched_boards holds the
    (source, company) pair of every board that was fetched successfully --
    db.upsert_postings only marks postings removed on those boards, so one
    failed request can't make a whole company's postings look taken down.
    """
    all_postings = []
    fetched_boards = set()
    errors = []

    for company_name, platform, slug in WATCHLIST:
        try:
            jobs = FETCHERS[platform](company_name, slug)
        except Exception as e:
            errors.append(f"{platform}:{slug}: {e}")
            print(f"[{platform}:{slug}] FAILED: {e}", file=sys.stderr)
            continue
        all_postings.extend(jobs)
        fetched_boards.add((platform, company_name))
        print(f"[{platform}:{slug}] {len(jobs)} postings")

    return all_postings, fetched_boards, errors


def main():
    scrape_date = date.today().isoformat()
    print(f"=== ghost-job-radar scrape: {scrape_date} ===")

    postings, fetched_boards, errors = collect_all()
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
    upsert_postings(conn, postings, scrape_date, fetched_boards)
    conn.close()
    print("Upserted into data/postings.db")

    print(f"Run complete at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
