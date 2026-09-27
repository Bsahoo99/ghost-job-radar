"""
Tests for scraper/build_audit_set.py, against synthetic postings.

Covers the two properties that matter for a hand-labeling workflow:
  1. Sampling respects the target size and per-company cap.
  2. Re-running the tool never loses or re-samples an already-labeled row.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from scraper.build_audit_set import (
    build_new_rows,
    load_existing,
    stratified_sample,
    write_audit_set,
)


def make_posting(source, job_id, company, title="Engineer", description=""):
    return {
        "source": source,
        "source_job_id": job_id,
        "company": company,
        "title": title,
        "location": "Remote",
        "url": f"https://example.com/{source}/{job_id}",
        "first_seen_date": "2026-09-27",
        "last_seen_date": "2026-09-27",
        "removed_date": None,
        "times_seen": 1,
        "description": description,
    }


class StratifiedSampleTests(unittest.TestCase):
    def setUp(self):
        # 5 companies on greenhouse with 20 postings each (100 total),
        # 60 remoteok postings each at a distinct company (no repeats).
        self.candidates = []
        for c in range(5):
            for j in range(20):
                self.candidates.append(
                    make_posting("greenhouse", f"gh-{c}-{j}", f"Company{c}")
                )
        for j in range(60):
            self.candidates.append(
                make_posting("remoteok", f"ro-{j}", f"RemoteCo{j}")
            )

    def test_respects_target_count(self):
        sample = stratified_sample(self.candidates, target_count=50, max_per_company=25, seed=1)
        self.assertLessEqual(len(sample), 50)

    def test_respects_per_company_cap(self):
        sample = stratified_sample(self.candidates, target_count=150, max_per_company=10, seed=1)
        counts = {}
        for p in sample:
            key = (p["source"], p["company"])
            counts[key] = counts.get(key, 0) + 1
        for key, count in counts.items():
            self.assertLessEqual(count, 10, f"{key} exceeded the per-company cap: {count}")

    def test_draws_from_both_sources_when_target_allows(self):
        sample = stratified_sample(self.candidates, target_count=60, max_per_company=25, seed=1)
        sources = {p["source"] for p in sample}
        self.assertEqual(sources, {"greenhouse", "remoteok"})

    def test_empty_candidates_returns_empty(self):
        self.assertEqual(stratified_sample([], target_count=50, max_per_company=10, seed=1), [])

    def test_zero_target_returns_empty(self):
        self.assertEqual(stratified_sample(self.candidates, target_count=0, max_per_company=10, seed=1), [])


class AuditSetFileRoundTripTests(unittest.TestCase):
    def test_existing_labels_survive_a_second_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit_set.csv"

            # First write: two rows, one already hand-labeled.
            first_rows = build_new_rows(
                [make_posting("greenhouse", "1", "Acme"), make_posting("greenhouse", "2", "Acme")],
                sampled_date="2026-09-27",
            )
            first_rows[0]["label"] = "real"
            first_rows[0]["notes"] = "confirmed via LinkedIn post"
            write_audit_set(path, existing_rows=[], new_rows=first_rows)

            # Simulate a later run: load what's there, add one new row, write again.
            existing = load_existing(path)
            self.assertEqual(len(existing), 2)
            self.assertEqual(existing[0]["label"], "real")

            second_new_rows = build_new_rows(
                [make_posting("greenhouse", "3", "Acme")], sampled_date="2026-09-28"
            )
            write_audit_set(path, existing_rows=existing, new_rows=second_new_rows)

            final = load_existing(path)
            self.assertEqual(len(final), 3)
            # The hand-entered label from the first run must survive untouched.
            self.assertEqual(final[0]["label"], "real")
            self.assertEqual(final[0]["notes"], "confirmed via LinkedIn post")
            self.assertEqual(final[2]["source_job_id"], "3")


if __name__ == "__main__":
    unittest.main()
