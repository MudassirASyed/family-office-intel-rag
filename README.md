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
- **Live API deployed**: https://family-office-intel-rag.onrender.com
  (`/health`, `/query`, `/reindex` — see `DOCUMENTATION_NOTE.md` for the
  deployment story, including the memory-constrained free-tier fixes).
  Frontend deploy in progress.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: add your free NewsAPI key, your real email for SEC_USER_AGENT,
# your Groq API key (https://console.groq.com - free tier), and your
# Cohere API key (https://dashboard.cohere.com/api-keys - free, no card,
# used for embeddings - see "Deploying for real" below for why)
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
   the frontend; the API is deployed on Render (free tier) with
   `API_BASE_URL` set on the Streamlit side to point at it. See
   "Deploying for real" below before you try this on a memory-limited
   free tier - the embedding choice matters a lot more than it looks.

## Deploying for real (read this before you deploy the API)

The API is live at **https://family-office-intel-rag.onrender.com** on
Render's free tier (512MB RAM). Getting there took three attempts, each
one a real lesson, not a footnote:

1. **sentence-transformers (PyTorch)** - the original local embedding
   choice, ~650-700MB in this process alone. OOM-killed on Render
   instantly (`status 137`).
2. **Chroma's bundled ONNX-runtime embedding** (same `all-MiniLM-L6-v2`
   model, lighter runtime) - dropped steady-state memory to ~150MB
   locally, and batched the embed calls (25 chunks at a time instead of
   all ~150 in one shot) to cut the startup spike. This got the service
   *live*, but it was still borderline: `/reindex` (which re-embeds
   everything, live) intermittently OOM-crashed the whole process, and
   a fresh cold boot occasionally did too - a coin-flip, not a fix.
3. **Cohere's hosted embedding API** (`embed-english-v3.0`, free tier,
   no card) - the actual fix. No embedding model of any kind loads into
   this process anymore; embedding happens on Cohere's infrastructure
   over a plain HTTPS call, the same pattern already used for Groq
   (generation) and NewsAPI (discovery). The API process is now just
   FastAPI + chromadb's vector math, comfortably under the memory
   ceiling through a full reindex cycle - previously the exact
   operation that crashed it.

The honest lesson: on a memory-constrained free host, *any* locally-
loaded ML model - even a "lightweight" ONNX one - is a live risk, not
just a one-time sizing problem. A hosted embedding API removes the
whole class of failure rather than shrinking it.

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
| Live API deployment | Complete — https://family-office-intel-rag.onrender.com (Render), see "Deploying for real" above |
| Live frontend deployment | In progress (Streamlit Community Cloud) |

See `SYSTEM_DESIGN.md` for architecture rationale mapped directly to
the assessment's stated requirements.
