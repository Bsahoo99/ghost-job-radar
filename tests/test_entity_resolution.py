"""
Unit tests for scraper/entity_resolution.py, against synthetic postings.

Real repost history doesn't exist yet (the scraper has been running for a
day), so these tests exercise the matching logic directly rather than
waiting on live data -- the whole point of building this as a parallel
track while collection runs.

Run with: python -m unittest discover -s tests
"""

import unittest

from scraper.entity_resolution import (
    MAX_REPOST_GAP_DAYS,
    MIN_TITLE_SIM_NO_DESC,
    description_similarity,
    find_repost_candidates,
    is_probable_repost,
    title_similarity,
)

LONG_DESC_A = (
    "We are looking for a Senior Backend Engineer to join our platform team. "
    "You will design and build APIs, work with distributed systems, and "
    "collaborate closely with product and design on our core infrastructure."
)
LONG_DESC_A_REWORDED = (
    "Join our platform team as a Senior Backend Engineer. You'll design and "
    "build APIs, work with distributed systems, and collaborate closely with "
    "product and design on our core infrastructure."
)
LONG_DESC_UNRELATED = (
    "We need a Marketing Coordinator to run our social media presence, plan "
    "events, write newsletter copy, and support the brand team on campaigns "
    "across every channel we operate in."
)


def make_posting(source, job_id, company, title, description="", removed_date=None,
                  first_seen_date=None):
    return {
        "source": source,
        "source_job_id": job_id,
        "company": company,
        "title": title,
        "description": description,
        "removed_date": removed_date,
        "first_seen_date": first_seen_date,
    }


class TitleSimilarityTests(unittest.TestCase):
    def test_identical_titles_score_one(self):
        self.assertEqual(title_similarity("Senior Backend Engineer", "Senior Backend Engineer"), 1.0)

    def test_reordered_words_score_high(self):
        # Token-sort ratio should treat these as near-identical despite reordering.
        sim = title_similarity("Senior Backend Engineer", "Backend Engineer, Senior")
        self.assertGreater(sim, 0.9)

    def test_unrelated_titles_score_low(self):
        sim = title_similarity("Senior Backend Engineer", "Marketing Coordinator")
        self.assertLess(sim, 0.5)

    def test_empty_title_scores_zero(self):
        self.assertEqual(title_similarity("", "Senior Backend Engineer"), 0.0)


class DescriptionSimilarityTests(unittest.TestCase):
    def test_reworded_description_scores_high(self):
        sim = description_similarity(LONG_DESC_A, LONG_DESC_A_REWORDED)
        self.assertGreater(sim, 0.75)

    def test_unrelated_description_scores_low(self):
        sim = description_similarity(LONG_DESC_A, LONG_DESC_UNRELATED)
        self.assertLess(sim, 0.3)


class IsProbableRepostTests(unittest.TestCase):
    def test_matches_same_company_similar_title_and_description(self):
        old = make_posting(
            "greenhouse", "111", "Acme Inc", "Senior Backend Engineer",
            description=LONG_DESC_A, removed_date="2026-09-10",
        )
        new = make_posting(
            "greenhouse", "222", "Acme Inc", "Backend Engineer, Senior",
            description=LONG_DESC_A_REWORDED, first_seen_date="2026-09-20",
        )
        match = is_probable_repost(old, new)
        self.assertIsNotNone(match)
        self.assertTrue(match.used_description)
        self.assertEqual(match.days_gap, 10)

    def test_rejects_different_company(self):
        old = make_posting(
            "greenhouse", "111", "Acme Inc", "Senior Backend Engineer",
            description=LONG_DESC_A, removed_date="2026-09-10",
        )
        new = make_posting(
            "greenhouse", "222", "Other Corp", "Senior Backend Engineer",
            description=LONG_DESC_A, first_seen_date="2026-09-20",
        )
        self.assertIsNone(is_probable_repost(old, new))

    def test_rejects_gap_beyond_max_days(self):
        old = make_posting(
            "greenhouse", "111", "Acme Inc", "Senior Backend Engineer",
            description=LONG_DESC_A, removed_date="2026-01-01",
        )
        new = make_posting(
            "greenhouse", "222", "Acme Inc", "Senior Backend Engineer",
            description=LONG_DESC_A,
            first_seen_date="2026-01-01",  # placeholder, overwritten below
        )
        # Push first_seen_date well past MAX_REPOST_GAP_DAYS from removed_date.
        import datetime
        removed = datetime.date(2026, 1, 1)
        too_late = removed + datetime.timedelta(days=MAX_REPOST_GAP_DAYS + 30)
        new["first_seen_date"] = too_late.isoformat()
        self.assertIsNone(is_probable_repost(old, new))

    def test_falls_back_to_title_only_when_no_description(self):
        old = make_posting(
            "greenhouse", "111", "Acme Inc", "Senior Backend Engineer",
            description="", removed_date="2026-09-10",
        )
        # Near-identical title, no usable description on either side.
        new_same = make_posting(
            "greenhouse", "222", "Acme Inc", "Senior Backend Engineer",
            description="", first_seen_date="2026-09-15",
        )
        match = is_probable_repost(old, new_same)
        self.assertIsNotNone(match)
        self.assertFalse(match.used_description)
        self.assertIsNone(match.description_similarity)

        # Title similar but not similar enough to clear the stricter
        # no-description bar -- should NOT match.
        new_different = make_posting(
            "greenhouse", "333", "Acme Inc", "Backend Engineer II",
            description="", first_seen_date="2026-09-15",
        )
        self.assertLess(
            title_similarity(old["title"], new_different["title"]), MIN_TITLE_SIM_NO_DESC
        )
        self.assertIsNone(is_probable_repost(old, new_different))


class FindRepostCandidatesTests(unittest.TestCase):
    def test_finds_the_one_real_pair_in_a_mixed_set(self):
        postings = [
            make_posting(
                "greenhouse", "111", "Acme Inc", "Senior Backend Engineer",
                description=LONG_DESC_A, removed_date="2026-09-10",
                first_seen_date="2026-08-01",
            ),
            make_posting(
                "greenhouse", "222", "Acme Inc", "Backend Engineer, Senior",
                description=LONG_DESC_A_REWORDED, first_seen_date="2026-09-20",
            ),
            # An unrelated still-active posting at the same company -- should not match.
            make_posting(
                "greenhouse", "333", "Acme Inc", "Marketing Coordinator",
                description=LONG_DESC_UNRELATED, first_seen_date="2026-09-01",
            ),
            # A removed posting at a different company -- should not pair with anything above.
            make_posting(
                "lever", "444", "Other Corp", "Senior Backend Engineer",
                description=LONG_DESC_A, removed_date="2026-09-05",
            ),
        ]
        matches = find_repost_candidates(postings)
        self.assertEqual(len(matches), 1)
        self.assertEqual((matches[0].old_source_job_id, matches[0].new_source_job_id), ("111", "222"))


if __name__ == "__main__":
    unittest.main()
