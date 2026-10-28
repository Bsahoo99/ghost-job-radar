"""
Tests for scraper/db.py's lifecycle tracking, against an in-memory SQLite DB.

Covers the two ways removed_date used to go wrong:
  1. A board whose fetch failed must not have its postings marked removed.
  2. RemoteOK rows (whose "removals" only meant "pushed out of the feed")
     are dropped by the migration, along with repost links that touch them.
"""

import sqlite3
import unittest

from scraper.db import SCHEMA, _migrate_drop_remoteok, upsert_postings


def make_posting(source, job_id, company):
    return {
        "source": source,
        "source_job_id": job_id,
        "company": company,
        "title": "Engineer",
        "location": "Remote",
        "remote": True,
        "url": f"https://example.com/{source}/{job_id}",
        "salary_min": None,
        "salary_max": None,
        "first_published": "2026-09-01",
        "updated_at": None,
        "description": "Build things.",
    }


def removed_dates(conn):
    return dict(conn.execute("SELECT source_job_id, removed_date FROM postings"))


class UpsertRemovalTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.executescript(SCHEMA)
        day_one = [
            make_posting("greenhouse", "gh-1", "Vercel"),
            make_posting("greenhouse", "gh-2", "Vercel"),
            make_posting("ashby", "ab-1", "Linear"),
        ]
        upsert_postings(
            self.conn, day_one, "2026-10-01",
            {("greenhouse", "Vercel"), ("ashby", "Linear")},
        )

    def test_missing_posting_on_fetched_board_is_removed(self):
        day_two = [
            make_posting("greenhouse", "gh-1", "Vercel"),
            make_posting("ashby", "ab-1", "Linear"),
        ]
        upsert_postings(
            self.conn, day_two, "2026-10-02",
            {("greenhouse", "Vercel"), ("ashby", "Linear")},
        )
        self.assertEqual(
            removed_dates(self.conn),
            {"gh-1": None, "gh-2": "2026-10-02", "ab-1": None},
        )

    def test_failed_board_leaves_its_postings_alone(self):
        # Linear's fetch failed today, so it's absent from fetched_boards.
        day_two = [
            make_posting("greenhouse", "gh-1", "Vercel"),
            make_posting("greenhouse", "gh-2", "Vercel"),
        ]
        upsert_postings(self.conn, day_two, "2026-10-02", {("greenhouse", "Vercel")})
        self.assertIsNone(removed_dates(self.conn)["ab-1"])

    def test_board_that_came_back_empty_removes_everything(self):
        # Fetched fine, just has no open jobs -- that IS a real takedown.
        upsert_postings(
            self.conn, [], "2026-10-02",
            {("greenhouse", "Vercel"), ("ashby", "Linear")},
        )
        self.assertEqual(set(removed_dates(self.conn).values()), {"2026-10-02"})


class DropRemoteOKMigrationTests(unittest.TestCase):
    def test_drops_remoteok_rows_and_their_repost_links(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.executescript(SCHEMA)
        upsert_postings(
            conn,
            [
                make_posting("remoteok", "ro-1", "SomeCo"),
                make_posting("greenhouse", "gh-1", "Vercel"),
            ],
            "2026-10-01",
            {("remoteok", "SomeCo"), ("greenhouse", "Vercel")},
        )
        conn.executemany(
            "INSERT INTO repost_links (old_source, old_source_job_id, new_source, new_source_job_id,"
            " detected_date) VALUES (?, ?, ?, ?, '2026-10-01')",
            [("remoteok", "ro-0", "remoteok", "ro-1"), ("greenhouse", "gh-0", "greenhouse", "gh-1")],
        )

        _migrate_drop_remoteok(conn)
        _migrate_drop_remoteok(conn)  # idempotent: runs on every get_connection()

        self.assertEqual(
            conn.execute("SELECT source FROM postings").fetchall(), [("greenhouse",)]
        )
        self.assertEqual(
            conn.execute("SELECT old_source FROM repost_links").fetchall(), [("greenhouse",)]
        )


if __name__ == "__main__":
    unittest.main()
