"""
Tests for scraper/features.py.

The properties that matter most here are the leakage-safety ones: a
feature computed "as of" an earlier date must not see data from later than
that date, and a posting's own future outcome must never leak into its own
features. Getting this wrong is exactly the mistake the PRD's original
Success Criteria made (evaluating against the same signals used to define
the label) -- these tests exist to make sure the fix actually holds.
"""

import datetime
import unittest

from scraper.features import (
    build_feature_table,
    compute_company_context,
    description_vagueness_score,
    days_open_so_far,
    is_open_as_of,
    salary_disclosed,
)

TODAY = datetime.date(2026, 9, 27)


def make_posting(source, job_id, company, first_seen_date, removed_date=None,
                  description="", times_seen=1, salary_min=None, salary_max=None):
    return {
        "source": source,
        "source_job_id": job_id,
        "company": company,
        "title": "Engineer",
        "description": description,
        "first_seen_date": first_seen_date,
        "removed_date": removed_date,
        "times_seen": times_seen,
        "salary_min": salary_min,
        "salary_max": salary_max,
    }


class IsOpenAsOfTests(unittest.TestCase):
    def test_open_posting_with_no_removed_date_is_open(self):
        p = make_posting("greenhouse", "1", "Acme", "2026-09-01")
        self.assertTrue(is_open_as_of(p, TODAY))

    def test_removed_before_as_of_date_is_not_open(self):
        p = make_posting("greenhouse", "1", "Acme", "2026-08-01", removed_date="2026-09-10")
        self.assertFalse(is_open_as_of(p, TODAY))

    def test_removed_after_as_of_date_was_still_open_then(self):
        # As of 2026-09-05, this posting hadn't been removed yet (that
        # happens on 09-10) -- scoring it "as of" an earlier date must see
        # it as open, not use the future removal to say otherwise.
        p = make_posting("greenhouse", "1", "Acme", "2026-08-01", removed_date="2026-09-10")
        self.assertTrue(is_open_as_of(p, datetime.date(2026, 9, 5)))

    def test_posting_not_yet_first_seen_is_not_open(self):
        p = make_posting("greenhouse", "1", "Acme", "2026-10-01")
        self.assertFalse(is_open_as_of(p, TODAY))


class DaysOpenSoFarTests(unittest.TestCase):
    def test_counts_from_first_seen_to_as_of_date_only(self):
        p = make_posting("greenhouse", "1", "Acme", "2026-09-01")
        self.assertEqual(days_open_so_far(p, TODAY), 26)

    def test_does_not_use_removed_date_even_when_present(self):
        # Two postings, identical first_seen_date, different removed_date --
        # days_open_so_far as of the SAME as_of_date must be identical,
        # since removed_date (the future outcome) must not affect it.
        p_still_open = make_posting("greenhouse", "1", "Acme", "2026-09-01")
        p_will_be_removed_later = make_posting(
            "greenhouse", "2", "Acme", "2026-09-01", removed_date="2026-12-01"
        )
        self.assertEqual(
            days_open_so_far(p_still_open, TODAY),
            days_open_so_far(p_will_be_removed_later, TODAY),
        )


class DescriptionVaguenessScoreTests(unittest.TestCase):
    def test_boilerplate_heavy_description_scores_higher(self):
        vague = "We are looking for a rockstar ninja self-starter for our dynamic team in a fast-paced environment."
        specific = (
            "You'll own our Postgres-backed billing service, migrate it to event "
            "sourcing, and pair with the two engineers already on the team."
        )
        self.assertGreater(description_vagueness_score(vague), description_vagueness_score(specific))

    def test_missing_description_returns_none_not_zero(self):
        self.assertIsNone(description_vagueness_score(""))
        self.assertIsNone(description_vagueness_score(None))


class SalaryDisclosedTests(unittest.TestCase):
    def test_true_when_either_bound_present(self):
        self.assertTrue(salary_disclosed(make_posting("g", "1", "A", "2026-09-01", salary_min=100000)))
        self.assertTrue(salary_disclosed(make_posting("g", "1", "A", "2026-09-01", salary_max=150000)))

    def test_false_when_neither_present(self):
        self.assertFalse(salary_disclosed(make_posting("g", "1", "A", "2026-09-01")))


class CompanyContextLeakageTests(unittest.TestCase):
    def test_repost_rate_only_reflects_removals_on_or_before_as_of_date(self):
        postings = [
            make_posting("greenhouse", "1", "Acme", "2026-08-01", removed_date="2026-08-15"),
            make_posting("greenhouse", "2", "Acme", "2026-08-20"),  # the repost of #1
            make_posting("greenhouse", "3", "Acme", "2026-09-01", removed_date="2026-09-20"),
        ]
        repost_links = [
            {"old_source": "greenhouse", "old_source_job_id": "1",
             "new_source": "greenhouse", "new_source_job_id": "2"},
        ]

        # As of a date BEFORE posting #1 was even removed, this repost
        # pattern shouldn't be visible at all.
        early_context = compute_company_context(postings, repost_links, datetime.date(2026, 8, 10))
        self.assertIsNone(early_context["acme"].repost_rate)

        # As of a date after #1's removal and the repost, it should show up.
        # By 2026-09-27, both #1 and #3 have been removed (removed_count=2),
        # and only #1 has a detected repost link, so the rate is 1/2, not 1.0.
        later_context = compute_company_context(postings, repost_links, datetime.date(2026, 9, 27))
        self.assertEqual(later_context["acme"].repost_rate, 0.5)

    def test_active_posting_count_reflects_as_of_date(self):
        postings = [
            make_posting("greenhouse", "1", "Acme", "2026-08-01", removed_date="2026-08-15"),
            make_posting("greenhouse", "2", "Acme", "2026-09-01"),
        ]
        context_early = compute_company_context(postings, [], datetime.date(2026, 8, 5))
        context_later = compute_company_context(postings, [], datetime.date(2026, 9, 27))
        self.assertEqual(context_early["acme"].active_posting_count, 1)  # only #1, not yet #2
        self.assertEqual(context_later["acme"].active_posting_count, 1)  # only #2, #1 now removed


class BuildFeatureTableTests(unittest.TestCase):
    def test_excludes_closed_postings_and_includes_open_ones(self):
        postings = [
            make_posting("greenhouse", "1", "Acme", "2026-08-01", removed_date="2026-08-15"),
            make_posting("greenhouse", "2", "Acme", "2026-09-01"),
        ]
        rows = build_feature_table(postings, [], TODAY)
        job_ids = {r["source_job_id"] for r in rows}
        self.assertEqual(job_ids, {"2"})

    def test_feature_row_has_expected_keys(self):
        postings = [make_posting("greenhouse", "1", "Acme", "2026-09-01", description="A real job. " * 10)]
        rows = build_feature_table(postings, [], TODAY)
        self.assertEqual(len(rows), 1)
        expected_keys = {
            "source", "source_job_id", "company", "as_of_date", "days_open_so_far",
            "times_seen_so_far", "description_length_chars", "description_vagueness_score",
            "salary_disclosed", "company_active_posting_count", "company_repost_rate",
        }
        self.assertEqual(set(rows[0].keys()), expected_keys)


if __name__ == "__main__":
    unittest.main()
