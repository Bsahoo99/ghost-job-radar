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
Hinge Health, LangChain, Modal, Replit, Linear. Ashby was added as a third
source on 2026-10-28 (api.ashbyhq.com/posting-api/job-board/{slug}), and
probing it the same way turned up several companies listed above as
"no evidence found" -- they were never on Greenhouse/Lever, they're on
Ashby: OpenAI, Notion, Perplexity, Ramp, Cursor, Braintrust (the agent
observability company, confirmed from the job descriptions) and Kong
(confirmed the same way).

Still not found on any of the three: Retool, Rippling, Anysphere (Cursor's
board is under "cursor"), Mercury and Deel (Ashby boards exist but list 0
jobs, so they'd add nothing).
"""

# (display_name, platform, board_slug) -- platform is "greenhouse", "lever" or "ashby"
WATCHLIST = [
    ("Vercel", "greenhouse", "vercel"),
    ("Scale AI", "greenhouse", "scaleai"),
    ("Together AI", "greenhouse", "togetherai"),
    ("Handshake", "greenhouse", "handshake"),
    ("Pinterest", "greenhouse", "pinterest"),
    ("Arize AI", "greenhouse", "arizeai"),  # was "arize" -- wrong slug, confirmed 26 jobs at "arizeai"
    ("Airtable", "greenhouse", "airtable"),  # was listed under Lever -- actually Greenhouse, confirmed 3 jobs
    ("Linear", "ashby", "linear"),
    ("Modal", "ashby", "modal"),
    ("Replit", "ashby", "replit"),
    ("LangChain", "ashby", "langchain"),
    ("Hinge Health", "ashby", "hinge-health"),
    ("OpenAI", "ashby", "openai"),
    ("Notion", "ashby", "notion"),
    ("Perplexity", "ashby", "perplexity"),
    ("Ramp", "ashby", "ramp"),
    ("Cursor", "ashby", "cursor"),
    ("Braintrust", "ashby", "braintrust"),
    ("Kong", "ashby", "kong"),
]
