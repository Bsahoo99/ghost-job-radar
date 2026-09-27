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
    description       TEXT   -- latest-seen raw description text (for entity resolution / features)
    description_hash  TEXT   -- sha256 of description text, to detect silent edits cheaply
    first_seen_date   TEXT   -- ISO date, first day OUR scraper observed this posting
    last_seen_date    TEXT   -- ISO date, most recent day it was still active
    removed_date      TEXT   -- ISO date, first day it was gone from an active scrape (NULL if still active)
    times_seen         INTEGER -- count of daily scrapes it has appeared in

Primary key is (source, source_job_id) -- NOT globally unique across a
company's reposts, which is intentional: reposting under a new id is exactly
the pattern this project is trying to catch, and it will show up as a *new*
row with a suspiciously similar title/company to a recently-removed row.
That similarity join is handled by scraper/entity_resolution.py, which reads
this table's `description` column and writes matches to `repost_links`
(schema below) -- not baked into the postings schema itself.

Schema (table: repost_links) -- output of entity_resolution.py, one row per
detected repost pair:
    old_source, old_source_job_id      -- the removed posting
    new_source, new_source_job_id      -- the posting judged to be its repost
    company
    title_similarity                   -- token-sort ratio, 0-1
    description_similarity             -- TF-IDF cosine similarity, 0-1, or NULL
                                           if descriptions weren't usable on
                                           one or both sides (see entity_resolution.py)
    days_gap                           -- days between removed_date and the new posting's first_seen_date
    used_description                   -- 0/1, whether description_similarity was part of the match
    detected_date                      -- ISO date this link was computed
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
    description       TEXT,
    description_hash  TEXT,
    first_seen_date   TEXT NOT NULL,
    last_seen_date    TEXT NOT NULL,
    removed_date       TEXT,
    times_seen         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (source, source_job_id)
);

CREATE TABLE IF NOT EXISTS repost_links (
    old_source          TEXT NOT NULL,
    old_source_job_id   TEXT NOT NULL,
    new_source          TEXT NOT NULL,
    new_source_job_id   TEXT NOT NULL,
    company             TEXT,
    title_similarity    REAL,
    description_similarity REAL,
    days_gap            INTEGER,
    used_description    INTEGER,
    detected_date       TEXT NOT NULL,
    PRIMARY KEY (old_source, old_source_job_id, new_source, new_source_job_id)
);
"""


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    _migrate_add_description_column(conn)
    return conn


def _migrate_add_description_column(conn):
    """Add `description` to a postings table created before this column existed.

    A plain CREATE TABLE IF NOT EXISTS won't add a column to an existing
    table, and the first live run's postings.db predates this column.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(postings)")}
    if "description" not in columns:
        conn.execute("ALTER TABLE postings ADD COLUMN description TEXT")
        conn.commit()


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
                    description, description_hash, first_seen_date, last_seen_date, removed_date, times_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)
                """,
                (
                    p["source"], p["source_job_id"], p["company"], p["title"],
                    p["location"], p["remote"], p["url"], p["salary_min"], p["salary_max"],
                    p["first_published"], p["updated_at"], p.get("description"), desc_hash,
                    scrape_date, scrape_date,
                ),
            )
        else:
            first_seen_date, times_seen = existing
            conn.execute(
                """
                UPDATE postings
                SET title = ?, location = ?, remote = ?, url = ?,
                    salary_min = ?, salary_max = ?, source_updated_at = ?,
                    description = ?, description_hash = ?, last_seen_date = ?, times_seen = ?
                WHERE source = ? AND source_job_id = ?
                """,
                (
                    p["title"], p["location"], p["remote"], p["url"],
                    p["salary_min"], p["salary_max"], p["updated_at"],
                    p.get("description"), desc_hash, scrape_date, times_seen + 1,
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


def fetch_all_postings(conn):
    """All postings as a list of dicts, for entity_resolution.find_repost_candidates."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM postings").fetchall()
    conn.row_factory = None
    return [dict(row) for row in rows]


def record_repost_links(conn, matches, detected_date):
    """Persist RepostMatch results from entity_resolution.py.

    Upsert on the (old, new) pair's primary key: re-running detection as
    more data comes in re-scores existing pairs rather than duplicating them.
    """
    for m in matches:
        conn.execute(
            """
            INSERT INTO repost_links (
                old_source, old_source_job_id, new_source, new_source_job_id,
                company, title_similarity, description_similarity, days_gap,
                used_description, detected_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (old_source, old_source_job_id, new_source, new_source_job_id)
            DO UPDATE SET
                title_similarity = excluded.title_similarity,
                description_similarity = excluded.description_similarity,
                days_gap = excluded.days_gap,
                used_description = excluded.used_description,
                detected_date = excluded.detected_date
            """,
            (
                m.old_source, m.old_source_job_id, m.new_source, m.new_source_job_id,
                m.company, m.title_similarity, m.description_similarity, m.days_gap,
                int(m.used_description), detected_date,
            ),
        )
    conn.commit()
