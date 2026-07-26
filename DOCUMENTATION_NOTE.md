# Documentation Note — Stack, Chunking, Embedding, Retrieval

## Stack and why

| Piece | Choice | Why |
|---|---|---|
| Vector store | Chroma (local, embedded) | Zero external infra for a 50-record / ~150-chunk dataset; full-rebuild-on-index is cheap at this scale (see below) |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` | Free, runs locally (no per-call cost or API key), fast enough for a 148-chunk corpus (~2-3s to fully re-embed), good-enough semantic quality for short structured chunks |
| Generation | Groq (Llama) | Free tier, fast inference, no local GPU needed |
| API layer | FastAPI | Thin HTTP boundary between retrieval/data and presentation, required by the brief's layer-separation rule |
| Frontend | Streamlit, calling the API over `requests` (HTTP), not importing `MicroRAG` in-process | Enforces the same layer separation on the client side — the frontend is a genuine external consumer of the API, not a shortcut |
| Two processes, one deploy target | API (FastAPI/uvicorn) + frontend (Streamlit), talking over `API_BASE_URL` | Each is independently restartable/testable; `curl` alone can validate the whole retrieval pipeline without a browser |

## Chunking strategy

Records are short structured rows, not documents — fixed-token windows
would fragment a 40-word description for no benefit. Each record splits
into up to 3 chunks along the boundary the brief itself defines as where
the value lives: **profile** (identity/thesis/sectors/location),
**principal** (decision-maker, skipped if absent), **signals** (recent
activity + qualification evidence — the "why contact them now" layer).
Every chunk carries `record_id`, `name`, `firm_type`, `confidence`, and
`chunk_type` as metadata. Current corpus: 50 records -> 149 chunks.

Real bug found in live testing, not review: a chunk built purely from
`qualification_evidence` didn't originally mention the firm's name, so a
multi-firm result caused the LLM to answer "the top-ranked firm... name not
specified" even though the name was in the metadata the whole time. Fixed
in two places — `chunking.py` now always names the firm in the chunk text
itself, and `rag.py` labels every context block `[Firm Name]` at assembly
time regardless of chunk text, closing the failure mode structurally
instead of patching the one spot it was caught.

## Retrieval — what makes it hybrid

`VectorStore.query()` does semantic similarity search **and** structured
metadata filtering (`min_confidence`, `firm_type`) in the same call — not
semantic-only search over one blob per firm. This was exercised live:

```
POST /query {"question": "Who is the principal contact at Duquesne Family
Office?", "firm_type": "single_family_office"}
-> "The principal at Duquesne Family Office is Stanley Druckenmiller."
   grounded: true, sources: 6 single_family_office chunks
```

The `firm_type` filter actually narrowed retrieval to SFO-only chunks
before the semantic search ran, not after.

## Grounding — the real control, not a prompt instruction

The brief is explicit that prompt instructions alone don't prove anything.
`retrieval/grounding.py::check_grounding()` is the enforcement mechanism:
it splits the generated answer into sentences and checks each against the
retrieved context for lexical overlap, withholding the whole answer (not
the underlying records) if a claim isn't supported. Hedge/refusal
sentences are exempted so honest uncertainty isn't punished as an
unsupported claim.

This was caught working live, not just in a unit test — an off-topic
control query returned an ungrounded response and the API correctly
suppressed the generated text:

```
POST /query {"question": "What is the weather in Tokyo?"}
-> grounded: false, status: "ungrounded"
   answer: "The generated answer contained claims that could not be
   verified against the retrieved records, so it has been withheld
   rather than shown as fact. The matching records are shown below so
   you can review them directly."
```

Stated honestly: this is lexical overlap, not embedding-similarity or NLI
entailment per sentence. It reliably catches invented names/numbers/claims
that appear nowhere in retrieval — the failure mode that matters most here
— but it will miss a paraphrased wrong number. Known limitation, not a
hidden one.

A positive multi-firm query was also run live and returned a correctly
grounded, multi-source answer:

```
POST /query {"question": "Which family offices are active in AI investing?"}
-> grounded: true
   answer: "...Hillspire - 22 private AI company investments since 2019
   ...Thiel Capital - sectors include artificial intelligence..."
   sources: 8 chunks across 8 distinct firms
```

## What works

- Hybrid retrieval (semantic + metadata filter) confirmed live, not just
  in code review.
- Grounding control confirmed on both a positive case (multi-firm AI
  question, correctly grounded) and a negative case (off-topic weather
  question, correctly withheld).
- `MicroRAG.grounded_answer()` never lets an exception reach the caller —
  every branch (no matches, generation unavailable, LLM failure, failed
  grounding) returns a plain-language `RagResponse`, verified via the
  no-match/off-topic case above returning a clean message, not a stack
  trace.

## Browser end-to-end test (Streamlit UI, not just the API)

Driven headlessly against the running app (Chrome DevTools Protocol, no
new dependencies installed) rather than only curl-testing the API:

1. Typed a question into the input, clicked **Search** → grounded answer
   rendered with a "Records used" section listing 8 source firms with
   confidence bars — matches the API-level result exactly.
2. Clicked the **"Who do I contact at Hillspire?"** example chip →
   populated the input correctly, and clicking **Search** again produced
   the correct grounded answer ("Eric Schmidt is the Principal at
   Hillspire... no phone number or email provided").

**Real bug found in step 2, not in review:** the original code built the
text input as `st.text_input(..., value=example_clicked or "")` with no
`key`. Because the `value=` argument changes between reruns, Streamlit
treats it as a new widget each time and resets it — so clicking an
example chip and then pressing Search on the *next* rerun silently wiped
the query back to blank and returned nothing. Fixed by keying the widget
to `st.session_state["query_text"]` and setting that key directly from
the button handlers, the standard Streamlit pattern for cross-widget
state. Confirmed fixed by re-running the same browser sequence.

**Second real bug found by the user, live, after the browser test above:**
asking "how many SFO u have in records" returned *"There is only 1 Single
Family Office (SFO) in the records: Soros Fund Management"* - wrong (the
real count is 28). Root cause: semantic retrieval only pulls the top 8
chunks (`VectorStore.query(..., n_results=8)`), so the LLM was reasoning
over a tiny slice of the corpus, not all 50 records - and the lexical
grounding check didn't catch it because "Soros Fund Management" genuinely
appeared in that partial context; the wrong *count* was a reasoning gap
over incomplete data, not an invented fact. Fixed by routing count-shaped
questions (`_is_count_query()` in `rag.py`, matches "how many ... SFO /
MFO / family office / records / firms") to the **structured** side of
retrieval instead of the semantic side: `VectorStore.all_records_metadata()`
reads every indexed chunk's metadata, dedups to one row per firm, and the
count is computed directly - no LLM call, no top-k slice, no room for a
wrong guess. Re-tested directly against the pipeline after the fix:
"how many SFO" -> "28 single-family offices, 22 multi-family offices" -
exact match against the dataset. This is what "hybrid retrieval" should
mean in practice: aggregate questions get the structured/exact path,
descriptive questions get the semantic path - not one generic path for
everything.

## What doesn't / known limitations

- Grounding is lexical overlap, not semantic entailment (above).
- 13F dollar figures are unreliable beyond simple joint-filing detection —
  three distinct failure modes found and documented in `SYSTEM_DESIGN.md`;
  response was to drop unverifiable dollar values dataset-wide rather than
  publish a number believed to be wrong.
- Vector store does a full rebuild on every index call — correct tradeoff
  at 50 records / 149 chunks (a few seconds), wrong at 50,000 (a
  deliberate, stated tradeoff, not an oversight).
- CORS on the API is wide open (`allow_origins=["*"]`) — fine for this
  single-consumer demo, not for a real deployment with untrusted origins.

## What to improve given more time

- Replace lexical-overlap grounding with a lightweight NLI/entailment
  model per sentence, to catch paraphrased-but-wrong numbers.
- Incremental (upsert) indexing instead of full rebuild, once record count
  outgrows the few-seconds-per-rebuild budget.
- Real NLP entity extraction (spaCy or an LLM pass) in place of the regex
  used in `news_search.extract_candidate_names()`.
- Diagnose the root cause of the 13F batch-pull value-inflation bug
  (suspected XML schema-version drift across filers) instead of only
  mitigating it by dropping the field.
