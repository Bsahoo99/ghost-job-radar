"""
Watchlist of companies to check on Greenhouse and Lever.

Seeded from Biswajeet's own 2026-08-18 application batches (SF mid/senior-level
roles) plus a handful of well-known AI/dev-tool startups likely to be on these
ATS platforms. Slugs are best guesses (usually the lowercase company name with
no spaces/punctuation) -- Greenhouse and Lever board slugs don't always match
the public brand name, so the scraper is expected to 404 on a chunk of these.
Each run logs which slugs actually resolved; prune/fix this list from that
feedback rather than guessing further up front.
"""

# (display_name, greenhouse_slug_or_None, lever_slug_or_None)
WATCHLIST = [
    ("Kong", "konginc", None),
    ("Braintrust", "braintrust", None),
    ("Hinge Health", "hingehealth", None),
    ("Arize AI", "arize", None),
    ("LangChain", "langchain", None),
    ("Ramp", "ramp", None),
    ("Notion", "notion", None),
    ("Vercel", "vercel", None),
    ("Retool", "retool", None),
    ("Scale AI", "scaleai", None),
    ("Anysphere", "anysphere", None),  # Cursor
    ("Perplexity", "perplexityai", None),
    ("Together AI", "togetherai", None),
    ("Modal", None, "modal"),
    ("Replit", None, "replit"),
    ("Mercury", None, "mercury"),
    ("Rippling", "rippling", None),
    ("Deel", "deel", None),
    ("Airtable", None, "airtable"),
    ("Linear", None, "linear"),
    ("Handshake", "handshake", None),
    ("Pinterest", "pinterest", None),
    ("OpenAI", "openai", None),
]
