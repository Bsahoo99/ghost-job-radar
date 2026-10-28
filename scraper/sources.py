"""
Source-specific fetchers. Every function returns a list of dicts in the
same normalized shape, regardless of where the posting came from:

    {
        "source":        "greenhouse" | "lever" | "ashby",
        "source_job_id": str   -- stable id from the origin platform
        "company":        str,
        "title":          str,
        "location":       str,
        "remote":         bool | None,
        "url":            str,
        "salary_min":     int | None,
        "salary_max":     int | None,
        "first_published": str | None,  -- ISO 8601, when the source tracks it
        "updated_at":      str | None,  -- ISO 8601, when the source tracks it
        "description":     str,          -- raw text/HTML, not cleaned here
    }

Every fetcher must be defensive: a single company's board being missing
(404), rate-limited, or malformed should never take down the whole run.

Every source here returns a company's COMPLETE board on each call, which is
what makes "missing from today's pull" mean "taken down". RemoteOK was
dropped on 2026-10-28 for failing that test: its feed only ever returns the
newest ~99 jobs, so a posting falling out of it just meant newer ones pushed
it out (see the 2026-10-28 note in db.py).
"""

import html

import requests

USER_AGENT = "ghost-job-radar/0.1 (personal research project; contact via GitHub)"
TIMEOUT = 20


def fetch_greenhouse(company_display_name, board_slug):
    """A single company's Greenhouse board.

    A 404 raises like any other HTTP error rather than returning []: an
    empty list would mark every posting we have for this company as taken
    down, when what actually happened is the board went unreachable.
    """
    # content=true is what makes the list endpoint include each job's
    # description (HTML-escaped HTML); without it the description is absent.
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs?content=true"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])

    out = []
    for job in jobs:
        location = (job.get("location") or {}).get("name", "")
        out.append({
            "source": "greenhouse",
            "source_job_id": str(job.get("id")),
            "company": company_display_name,
            "title": (job.get("title") or "").strip(),
            "location": location,
            "remote": "remote" in location.lower() if location else None,
            "url": job.get("absolute_url"),
            "salary_min": None,
            "salary_max": None,
            "first_published": job.get("first_published"),
            "updated_at": job.get("updated_at"),
            "description": html.unescape(job.get("content") or ""),
        })
    return out


def fetch_lever(company_display_name, lever_slug):
    """A single company's Lever board. A 404 raises (see fetch_greenhouse)."""
    url = f"https://api.lever.co/v0/postings/{lever_slug}?mode=json"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = resp.json()

    out = []
    for job in jobs:
        categories = job.get("categories", {}) or {}
        out.append({
            "source": "lever",
            "source_job_id": str(job.get("id")),
            "company": company_display_name,
            "title": (job.get("text") or "").strip(),
            "location": categories.get("location", ""),
            "remote": (categories.get("commitment", "") or "").lower().find("remote") >= 0
                      or "remote" in (categories.get("location", "") or "").lower(),
            "url": job.get("hostedUrl"),
            "salary_min": None,
            "salary_max": None,
            "first_published": None,  # Lever doesn't expose a created timestamp on this endpoint
            "updated_at": job.get("createdAt"),  # epoch millis; normalized in run.py
            "description": job.get("descriptionPlain", "") or job.get("description", ""),
        })
    return out


def _ashby_salary(compensation):
    """(min, max) annual salary from an Ashby compensation block, or (None, None).

    Only a yearly "Salary" component counts; equity, bonus and hourly
    components are skipped rather than mixed into one number.
    """
    for component in (compensation or {}).get("summaryComponents") or []:
        if component.get("compensationType") == "Salary" and component.get("interval") == "1 YEAR":
            return component.get("minValue"), component.get("maxValue")
    return None, None


def fetch_ashby(company_display_name, ashby_slug):
    """A single company's Ashby board. A 404 raises (see fetch_greenhouse)."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{ashby_slug}?includeCompensation=true"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])

    out = []
    for job in jobs:
        if not job.get("isListed", True):
            continue  # unlisted jobs are only reachable by direct link, not part of the public board
        salary_min, salary_max = _ashby_salary(job.get("compensation"))
        out.append({
            "source": "ashby",
            "source_job_id": str(job.get("id")),
            "company": company_display_name,
            "title": (job.get("title") or "").strip(),
            "location": job.get("location") or "",
            "remote": job.get("isRemote"),
            "url": job.get("jobUrl"),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "first_published": job.get("publishedAt"),
            "updated_at": None,  # Ashby's public board doesn't expose an update time
            "description": job.get("descriptionHtml") or job.get("descriptionPlain") or "",
        })
    return out
