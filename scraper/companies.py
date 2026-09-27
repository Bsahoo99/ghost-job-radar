"""
Watchlist of companies to check on Greenhouse and Lever.

Seeded from Biswajeet's own 2026-08-18 application batches (SF mid/senior-level
roles) plus a handful of well-known AI/dev-tool startups likely to be on these
ATS platforms. Pruned after the first live run (2026-09-27) against the actual
boards-api.greenhouse.io / api.lever.co responses, checked one at a time to
avoid the parallel-request rate limiting that gave false 404s on the first
verification pass.

Confirmed working: Vercel, Scale AI, Together AI, Handshake, Pinterest
(these produced the 527 greenhouse rows in the first snapshot), plus Arize AI
and Airtable below, fixed from wrong slugs/wrong platform.

Confirmed dead (real 404 on the public Job Board API, verified individually,
not a rate-limit artifact) even where the company's own careers page IS on
Greenhouse: Notion, Retool, Perplexity. Greenhouse's public Job Board API is
an opt-in setting separate from the hosted careers page, so a company can be
"on Greenhouse" and still 404 here -- that's a real platform limitation, not
a wrong slug.

Confirmed on a different ATS entirely (mostly Ashby, not Greenhouse/Lever):
Hinge Health, LangChain, Modal, Replit, Linear. Ashby has its own public API
(api.ashbyhq.com/posting-api/job-board/{slug}) -- worth adding as a fourth
source later, documented as a stretch goal rather than built now.

Removed with no evidence found on either platform under any guessed slug:
Kong, Braintrust (the only Greenhouse hit was the unrelated "Braintrust
Tutors"), Ramp (the only Greenhouse hit was the unrelated "Ramp Network"),
Anysphere/Cursor, Rippling, Deel, OpenAI, Mercury.
"""

# (display_name, greenhouse_slug_or_None, lever_slug_or_None)
WATCHLIST = [
    ("Vercel", "vercel", None),
    ("Scale AI", "scaleai", None),
    ("Together AI", "togetherai", None),
    ("Handshake", "handshake", None),
    ("Pinterest", "pinterest", None),
    ("Arize AI", "arizeai", None),  # was "arize" -- wrong slug, confirmed 26 jobs at "arizeai"
    ("Airtable", "airtable", None),  # was listed under Lever -- actually Greenhouse, confirmed 3 jobs
]
