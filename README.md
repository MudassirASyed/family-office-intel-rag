# Family Office Intelligence — Dataset + Micro-RAG

Built for the PolarityIQ Differentiator Stage 1 assessment.

## Status right now (read this first)

- **Dataset complete**: 50 real, individually-verified family office
  records in `data/records.json` (28 single-family offices, 22
  multi-family offices), produced by a re-runnable pipeline, not
  hand-assembled. See `METHODOLOGY.md` for discovery/verification/
  enrichment process and honest blind spots, and `VALIDATION_CHAIN.md`
  for the required 3-record full validation chain.
- **Retrieval pipeline built and verified end-to-end** against the full
  50-record dataset (149 chunks indexed). Chunking, hybrid
  structured+semantic retrieval, LLM generation, and the grounding
  control have all been exercised with real Groq API calls and real
  live queries (both a correctly-grounded multi-firm answer and a
  correctly-withheld off-topic answer) — see `DOCUMENTATION_NOTE.md`
  for the actual query/response pairs and `SYSTEM_DESIGN.md` for
  architecture rationale and what broke on first try.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: add your free NewsAPI key, your real email for SEC_USER_AGENT,
# and your Groq API key (https://console.groq.com - free tier)
```

## Architecture

Two processes, talking over HTTP - not Streamlit importing the RAG
code in-process. See `SYSTEM_DESIGN.md` for why this separation is a
scored requirement, not incidental structure.

```
data/records.json --> api/main.py (FastAPI, port 8000) --> frontend/streamlit_app.py (port 8501)
                       ^ retrieval/data layer                ^ presentation layer only
```

## Runbook

1. **Write your inclusion criteria** in `processing/classifier.py`
   (`INCLUSION_CRITERIA`) - do this before classifying anything.
2. **Run discovery + build the initial dataset:**
   ```bash
   python scripts/run_pipeline.py
   ```
   This writes `data/records.json` using the real seed set + any
   NewsAPI results if you've added a key.
3. **Manually review every candidate** the pipeline surfaces -
   confirm/reject `firm_qualifies`, fill in enrichment fields
   (principal name, LinkedIn, email, phone) where you can verify them.
   Leave fields honestly blank where you can't.
4. **Re-save** `data/records.json` after your review pass.
5. **Smoke-test the RAG pipeline directly** (no server, fast iteration):
   ```bash
   python -m retrieval.rag
   ```
6. **Start the API:**
   ```bash
   uvicorn api.main:app --reload --port 8000
   ```
   Verify it: `curl http://localhost:8000/health`. After updating
   `data/records.json`, call `curl -X POST http://localhost:8000/reindex`
   instead of restarting - or just restart, it reindexes on startup too.
7. **Start the frontend** (in a second terminal, with the API already running):
   ```bash
   streamlit run frontend/streamlit_app.py
   ```
   Set `API_BASE_URL` if the API isn't on `localhost:8000`.
8. **Deploy** — the API and the frontend deploy separately. Streamlit
   Community Cloud (free, connects directly to a GitHub repo) works for
   the frontend; the API needs a host that runs an arbitrary process
   (Render/Railway/Fly free tiers all work) with `API_BASE_URL` set on
   the Streamlit side to point at it.

## What's real vs. scaffolded — full honesty

| Component | Status |
|---|---|
| 50-record family office dataset | Real, sourced, cited, individually verified — see `METHODOLOGY.md` |
| SEC EDGAR 13F discovery/search | Real code, exercised live against `data.sec.gov` (78 raw candidates, joint-filing + recency filtering) |
| News-based discovery script | Real code, run live with a real NewsAPI key |
| ProPublica 990 / SEC EDGAR fetchers | Real code, exercised for verification during enrichment |
| Confidence scoring | Logic tested and correct; never hand-typed (`compute_confidence()`) |
| Chunking (`retrieval/chunking.py`) | Built and live-tested; one real bug found and fixed (see SYSTEM_DESIGN.md) |
| Vector store + hybrid retrieval | Built and live-tested against the full 50-record / 149-chunk dataset |
| Grounding/citation check | Built and live-tested — confirmed it correctly withholds an off-topic answer, confirmed it passes a correctly-grounded multi-firm answer (see DOCUMENTATION_NOTE.md) |
| FastAPI service (`api/main.py`) | Built and live-tested via `curl` — health, query, empty-input, structured-filter, no-match paths all verified |
| Streamlit UI | Verified via HTTP; browser click-through in progress |
| Principal contact enrichment | Manual-but-logged per firm; honest blanks where no public contact exists (see METHODOLOGY.md blind spots) |
| 3-record full validation chain | Complete — `VALIDATION_CHAIN.md` |
| Live deployment URL | Pending |

See `SYSTEM_DESIGN.md` for architecture rationale mapped directly to
the assessment's stated requirements.
