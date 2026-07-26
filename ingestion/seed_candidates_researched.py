"""
REAL entity names, found via live web research (news search) during
planning, before this pipeline existed. These are genuinely real
companies with real public press coverage - not fabricated.

IMPORTANT - what these are and are NOT:
- These ARE real, named single-family offices confirmed via press
  (CNBC's "Inside Wealth Family Office 15" ranking, Feb 2026;
  Yahoo Finance/Motley Fool coverage).
- These are NOT yet enriched (no principal contact info) or run
  through your classifier's inclusion standard.
- These are also all billionaire-tier, heavily-publicized SFOs -
  i.e. still a somewhat "convenient" source in aggregate (financial
  press covering famous people). Do NOT let this list alone become
  your final 50. Use it as a bootstrap/test set for your pipeline
  while you build out the regional/990/podcast sourcing that finds
  the genuinely obscure ones the brief is really testing for.

Treat this as a hand-verified starting point to test your enrichment
and RAG code against real entities while the scaled discovery
scripts (news_search.py, propublica_990.py) are still being built out.
"""

RESEARCHED_SEEDS = [
    {
        "name": "Hillspire",
        "principal_family": "Eric & Wendy Schmidt",
        "notes": "Ranked #1 in CNBC's inaugural Inside Wealth Family Office 15 (2026), 15 investments in 2025, mostly AI.",
        "source": "press",
        "source_url": "https://www.cnbc.com/2026/02/12/inside-wealth-family-office-15.html",
    },
    {
        "name": "Bezos Expeditions",
        "principal_family": "Jeff Bezos",
        "notes": "Backed Unconventional AI, Physical Intelligence; ranked #2 in CNBC's 2026 list.",
        "source": "press",
        "source_url": "https://www.cnbc.com/2026/02/12/inside-wealth-family-office-15.html",
    },
    {
        "name": "Thiel Capital",
        "principal_family": "Peter Thiel",
        "notes": "Listed among most active family offices for 2025 dealmaking per CNBC.",
        "source": "press",
        "source_url": "https://www.cnbc.com/2026/02/12/inside-wealth-family-office-15.html",
    },
    {
        "name": "Jaws Estates Capital",
        "principal_family": "Barry Sternlicht",
        "notes": "Listed among most active family offices for 2025 dealmaking per CNBC.",
        "source": "press",
        "source_url": "https://www.cnbc.com/2026/02/12/inside-wealth-family-office-15.html",
    },
    {
        "name": "Wildcat Capital Management",
        "principal_family": "David Bonderman (TPG co-founder, d. Dec 2024)",
        "notes": "Founded 2011 as single-family office; recent $16.6M exit from TIC Solutions covered by Motley Fool/Yahoo Finance.",
        "source": "press",
        "source_url": "https://finance.yahoo.com/news/billionaire-family-offices-16-6-183153119.html",
    },
    {
        "name": "Duquesne Family Office",
        "principal_family": "Stanley Druckenmiller",
        "notes": "New Q4 2025 position in Bloom Energy per CNBC coverage of 13F filings.",
        "source": "press",
        "source_url": "https://www.cnbc.com/2026/02/26/billionaire-family-office-investments.html",
    },
    {
        "name": "Kemnay Advisory Services",
        "principal_family": "Alan Parker (duty-free mogul)",
        "notes": "Increased Coinbase position ~44% in Q4 2025 per CNBC 13F coverage.",
        "source": "press",
        "source_url": "https://www.cnbc.com/2026/02/26/billionaire-family-office-investments.html",
    },
]

if __name__ == "__main__":
    for s in RESEARCHED_SEEDS:
        print(f"{s['name']} — {s['principal_family']} ({s['source_url']})")
