"""
SQLite-backed lifecycle tracking for scraped postings.

The whole point of running this daily for 2-3 weeks is to observe *change*:
does a posting stay up for months with no close date, does it get pulled and
reposted as a "new" listing days later, does it get edited (title/description)
without really changing. A single scrape is a snapshot; this table is the
memory across scrapes that makes those patterns visible.

Schema (table: postings):
    source            TEXT   -- remoteok / greenhouse / lever
    source_job_id     TEXT   -- id from the origin platform
    company           TEXT
    title             TEXT
    location          TEXT
    remote            INTEGER (0/1/NULL)
    url               TEXT
    salary_min        INTEGER
    salary_max        INTEGER
    first_published   TEXT   -- ISO date, earliest we've seen a "published" claim
    source_updated_at TEXT   -- ISO date, latest "updated_at" the source itself reports
    description_hash  TEXT   -- sha256 of description text, to detect silent edits
    first_seen_date   TEXT   -- ISO date, first day OUR scraper observed this posting
    last_seen_date    TEXT   -- ISO date, most recent day it was still active
    removed_date      TEXT   -- ISO date, first day it was gone from an active scrape (NULL if still active)
    times_seen         INTEGER -- count of daily scrapes it has appeared in

Primary key is (source, source_job_id) -- NOT globally unique across a
company's reposts, which is intentional: reposting under a new id is exactly
the pattern this project is trying to catch, and it will show up as a *new*
row with a suspiciously similar title/company to a recently-removed row
(that similarity join is a later analysis step, not something to bake into
the schema now).
"""

import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "postings.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    source            TEXT NOT NULL,
    source_job_id     TEXT NOT NULL,
    company           TEXT,
    title             TEXT,
    location          TEXT,
    remote            INTEGER,
    url               TEXT,
    salary_min        INTEGER,
    salary_max        INTEGER,
    first_published   TEXT,
    source_updated_at TEXT,
    description_hash  TEXT,
    first_seen_date   TEXT NOT NULL,
    last_seen_date    TEXT NOT NULL,
    removed_date       TEXT,
    times_seen         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (source, source_job_id)
);
"""


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    return conn


def _hash_description(text):
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def upsert_postings(conn, postings, scrape_date):
    """
    postings: list of normalized dicts from scraper/sources.py
    scrape_date: ISO date string (YYYY-MM-DD) for this run

    Any row already in the table whose (source, source_job_id) is NOT in
    `postings` this run is considered removed as of `scrape_date` (only set
    once -- first disappearance wins, so re-appearing sets last_seen_date but
    does not clear removed_date; that's a signal in itself, handled at
    analysis time, not here).
    """
    seen_keys = set()
    for p in postings:
        key = (p["source"], p["source_job_id"])
        seen_keys.add(key)
        desc_hash = _hash_description(p.get("description"))

        existing = conn.execute(
            "SELECT first_seen_date, times_seen FROM postings WHERE source = ? AND source_job_id = ?",
            key,
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO postings (
                    source, source_job_id, company, title, location, remote, url,
                    salary_min, salary_max, first_published, source_updated_at,
                    description_hash, first_seen_date, last_seen_date, removed_date, times_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)
                """,
                (
                    p["source"], p["source_job_id"], p["company"], p["title"],
                    p["location"], p["remote"], p["url"], p["salary_min"], p["salary_max"],
                    p["first_published"], p["updated_at"], desc_hash, scrape_date, scrape_date,
                ),
            )
        else:
            first_seen_date, times_seen = existing
            conn.execute(
                """
                UPDATE postings
                SET title = ?, location = ?, remote = ?, url = ?,
                    salary_min = ?, salary_max = ?, source_updated_at = ?,
                    description_hash = ?, last_seen_date = ?, times_seen = ?
                WHERE source = ? AND source_job_id = ?
                """,
                (
                    p["title"], p["location"], p["remote"], p["url"],
                    p["salary_min"], p["salary_max"], p["updated_at"],
                    desc_hash, scrape_date, times_seen + 1,
                    p["source"], p["source_job_id"],
                ),
            )

    # Mark newly-missing rows as removed (only if not already marked).
    rows = conn.execute(
        "SELECT source, source_job_id FROM postings WHERE removed_date IS NULL"
    ).fetchall()
    for source, source_job_id in rows:
        if (source, source_job_id) not in seen_keys:
            conn.execute(
                "UPDATE postings SET removed_date = ? WHERE source = ? AND source_job_id = ?",
                (scrape_date, source, source_job_id),
            )

    conn.commit()
