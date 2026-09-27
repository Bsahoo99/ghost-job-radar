"""
Source-specific fetchers. Every function returns a list of dicts in the
same normalized shape, regardless of where the posting came from:

    {
        "source":        "remoteok" | "greenhouse" | "lever",
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
Network calls only work from an environment with real internet access
(e.g. GitHub Actions) -- this sandbox's shell cannot reach these hosts.
"""

import requests

USER_AGENT = "ghost-job-radar/0.1 (personal research project; contact via GitHub)"
TIMEOUT = 20


def fetch_remoteok():
    """RemoteOK's public JSON feed. First element is a legal/ToS notice, not a job."""
    url = "https://remoteok.com/api"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    rows = resp.json()

    out = []
    for row in rows:
        if "id" not in row:
            continue  # the leading legal-notice object has no "id"
        out.append({
            "source": "remoteok",
            "source_job_id": str(row.get("id")),
            "company": row.get("company", "").strip(),
            "title": row.get("position", "").strip(),
            "location": row.get("location", "") or "Remote",
            "remote": True,
            "url": row.get("url") or row.get("apply_url"),
            "salary_min": row.get("salary_min") or None,
            "salary_max": row.get("salary_max") or None,
            "first_published": row.get("date"),
            "updated_at": row.get("date"),  # RemoteOK doesn't expose a separate update time
            "description": row.get("description", ""),
        })
    return out


def fetch_greenhouse(company_display_name, board_slug):
    """A single company's Greenhouse board. Returns [] (not an error) on 404."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    if resp.status_code == 404:
        return []
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
            "description": "",  # Greenhouse's list endpoint omits full description; fetched per-job if needed
        })
    return out


def fetch_lever(company_display_name, lever_slug):
    """A single company's Lever board. Returns [] (not an error) on 404."""
    url = f"https://api.lever.co/v0/postings/{lever_slug}?mode=json"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    if resp.status_code == 404:
        return []
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
