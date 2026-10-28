"""
Tests for scraper/sources.py's response parsing, with HTTP mocked out.

The fetchers run against the real APIs every day in GitHub Actions; these
tests pin down the parsing that was easy to get subtly wrong: Greenhouse's
HTML-escaped descriptions, Ashby's salary block, and 404 handling.
"""

import unittest
from unittest import mock

import requests

from scraper import sources


def fake_response(status_code, payload=None):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.json.return_value = payload
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code} Error")
    return resp


class GreenhouseTests(unittest.TestCase):
    def test_description_is_unescaped_html(self):
        payload = {"jobs": [{
            "id": 1, "title": "Engineer", "location": {"name": "Remote"},
            "absolute_url": "https://example.com/1",
            "first_published": "2026-09-01T00:00:00Z", "updated_at": None,
            "content": "&lt;p&gt;Build &amp;amp; ship.&lt;/p&gt;",
        }]}
        with mock.patch.object(sources.requests, "get", return_value=fake_response(200, payload)) as get:
            jobs = sources.fetch_greenhouse("Airtable", "airtable")
        self.assertIn("content=true", get.call_args.args[0])
        self.assertEqual(jobs[0]["description"], "<p>Build &amp; ship.</p>")

    def test_404_raises_instead_of_looking_like_an_empty_board(self):
        with (
            mock.patch.object(sources.requests, "get", return_value=fake_response(404)),
            self.assertRaises(requests.HTTPError),
        ):
            sources.fetch_greenhouse("Notion", "notion")


class AshbyTests(unittest.TestCase):
    def make_job(self, **overrides):
        job = {
            "id": "abc", "title": " Engineer ", "location": "SF", "isRemote": False,
            "jobUrl": "https://jobs.ashbyhq.com/x/abc", "isListed": True,
            "publishedAt": "2021-04-27T20:13:45.158+00:00",
            "descriptionHtml": "<p>Build things.</p>", "compensation": None,
        }
        job.update(overrides)
        return job

    def fetch(self, jobs):
        with mock.patch.object(sources.requests, "get", return_value=fake_response(200, {"jobs": jobs})):
            return sources.fetch_ashby("Linear", "linear")

    def test_normalizes_a_job(self):
        [job] = self.fetch([self.make_job()])
        self.assertEqual(job["source"], "ashby")
        self.assertEqual(job["company"], "Linear")
        self.assertEqual(job["title"], "Engineer")
        self.assertEqual(job["first_published"], "2021-04-27T20:13:45.158+00:00")
        self.assertEqual(job["description"], "<p>Build things.</p>")
        self.assertEqual((job["salary_min"], job["salary_max"]), (None, None))

    def test_reads_yearly_salary_and_skips_equity(self):
        compensation = {"summaryComponents": [
            {"compensationType": "EquityPercentage", "interval": "NONE", "minValue": None, "maxValue": None},
            {"compensationType": "Salary", "interval": "1 YEAR", "minValue": 211400, "maxValue": 290600},
        ]}
        [job] = self.fetch([self.make_job(compensation=compensation)])
        self.assertEqual((job["salary_min"], job["salary_max"]), (211400, 290600))

    def test_ignores_hourly_salary(self):
        compensation = {"summaryComponents": [
            {"compensationType": "Salary", "interval": "1 HOUR", "minValue": 50, "maxValue": 70},
        ]}
        [job] = self.fetch([self.make_job(compensation=compensation)])
        self.assertEqual((job["salary_min"], job["salary_max"]), (None, None))

    def test_skips_unlisted_jobs(self):
        jobs = self.fetch([self.make_job(), self.make_job(id="hidden", isListed=False)])
        self.assertEqual([j["source_job_id"] for j in jobs], ["abc"])


if __name__ == "__main__":
    unittest.main()
