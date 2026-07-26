# System Design

## Layer separation (required by the brief)

```
ingestion/       -> discovery + raw fetching (news, 990s, EDGAR, web pages)
processing/      -> record schema, confidence scoring, qualification classifier
retrieval/       -> chunking, embedding, vector store, LLM generation, grounding check
api/             -> FastAPI service - the retrieval/data layer's HTTP boundary
frontend/        -> Streamlit UI (customer-facing, no raw JSON/dev console)
scripts/         -> orchestration (run_pipeline.py ties it all together)
data/            -> the actual dataset artifact (records.json)
```

`frontend/streamlit_app.py` does not import `MicroRAG`. It calls
`api/main.py` over HTTP (`requests`), the same way a `curl` command or
a future non-Streamlit client would. That is the real separation
between the retrieval/data layer and the presentation layer: each is
independently deployable, independently restartable, and independently
testable - you can validate the entire retrieval pipeline with `curl`
against a running API and never open a browser. This resolves a gap
flagged in an earlier draft of this file, where Streamlit called
`MicroRAG` in-process.

Within `retrieval/`, the pieces are further split by responsibility so
each is independently testable:

| Module | Responsibility |
|---|---|
| `chunking.py` | Turns one record into semantically-scoped chunks (see below) |
| `vectorstore.py` | Chroma wrapper - structured + semantic query, full-rebuild indexing |
| `generator.py` | The LLM call (Groq), isolated so the provider can be swapped |
| `grounding.py` | Post-hoc check of the LLM's answer against retrieved context |
| `rag.py` | Orchestrator - wires the above together, decides what the user sees on failure |

Each layer only imports downward (frontend -> api -> retrieval ->
processing/config), never sideways or upward.

## Chunking strategy

Records here are short, structured rows, not long documents - fixed-
size token windows would fragment a 40-word description for no
benefit. Instead, each record is split into up to 3 chunks along the
boundary the brief itself defines as where the value lives:

1. **Profile** - firm identity, description, thesis, sectors, location
2. **Principal** - decision-maker name/title/contact (skipped if absent)
3. **Signals** - recent activity + qualification evidence, i.e. the
   "why contact them now" layer

A query about "who invests in AI" and a query about "who do I call at
X" shouldn't have to compete against one blended paragraph per firm -
splitting by category lets the embedding for each chunk actually
represent what it's about. Every chunk carries `record_id`, `name`,
`firm_type`, `confidence`, and `chunk_type` as metadata, which is what
makes retrieval **hybrid**: `vectorstore.query()` does semantic
similarity search *and* structured metadata filtering (`min_confidence`,
`firm_type`) in the same call, not semantic-only search over a single
blob per firm.

Caught in live testing, not in review: a chunk built purely from
`qualification_evidence` originally didn't mention the firm's name, so
a query with mixed-firm results caused the LLM to answer "the family
office ranked #1... name not specified" even though the name was right
there in metadata. Fixed two ways - chunking.py now always names the
firm in every chunk's text, and `rag.py` labels every context block
with `[Firm Name]` at assembly time regardless of what the chunk text
says, so the failure mode is structurally closed off rather than just
patched in the one spot it was found.

Indexing is a full rebuild on every call (`VectorStore.rebuild()`), not
an incremental upsert. At 50 records (~150 chunks) re-embedding
everything costs a few seconds and removes an entire class of bugs
(stale chunks from an edited or deleted record lingering in the
index). This would be the wrong call at 50,000 records - stated as a
deliberate tradeoff for this scale, not a limitation nobody noticed.

## Two-rule verification model (required by the brief)

- `FamilyOfficeRecord.sources_checked` / `.evidence` -> per-CELL basis
  (rule 1: individual facts, honest blanks allowed)
- `FamilyOfficeRecord.firm_qualifies` -> per-FIRM gate
  (rule 2: strict, no partial credit, no "probably")

`qualifies_for_final_dataset()` enforces both simultaneously - a
well-verified record on a disqualified firm still fails.

## Grounding discipline (required by the brief)

The brief explicitly says prompt instructions alone don't prove
anything. `retrieval/grounding.py::check_grounding()` is the actual
enforcement mechanism: it splits the LLM's generated answer into
sentences and checks each against the retrieved context for lexical
overlap, withholding the answer (not the underlying records) if a
claim isn't supported. Hedge/refusal sentences ("I don't have enough
information...") are exempted so honest uncertainty isn't penalized as
if it were an unsupported claim.

Stated honestly: this is lexical overlap, not embedding-similarity or
NLI entailment per sentence. It catches invented names/numbers/claims
that appear nowhere in retrieval - the failure mode that matters most
here - but it will miss a paraphrased wrong number. That's a known
limitation, not a hidden one.

## Failure handling (required by the brief - "not an error dump")

`MicroRAG.grounded_answer()` never lets an exception reach the caller.
Every branch - no matching records, generation model not configured,
the LLM call itself failing, or the LLM's answer failing grounding -
returns a `RagResponse` with a plain-language message and a `status`
field the UI branches on. The FastAPI layer and the Streamlit layer
each additionally catch their own failure modes (bad request, API
unreachable) so a user never sees a stack trace or raw JSON, per the
brief's explicit requirement.

## Source class separation (required by the brief - "not one convenient source")

| Source class       | What it's good for                          | What it CANNOT tell you |
|---------------------|----------------------------------------------|---------------------------|
| News/press           | Discovering SFOs tied to liquidity events   | Structured/complete data |
| ProPublica 990s      | Discovering family foundations (proxy signal)| Whether an investment vehicle exists |
| SEC EDGAR/ADV        | Verifying registered/hybrid entities         | True exempt SFOs (they don't file) |
| Firm websites        | Verification only, when a site exists        | Nothing, for many true SFOs (no site) |

Discovery sources and verification sources are kept as separate
function calls in separate files on purpose - conflating them is
exactly the "one convenient source" failure mode the brief warns
about.

## Known limitations (stated honestly)

- `news_search.extract_candidate_names()` uses a crude regex, not NLP
  entity extraction - expect false positives/negatives.
- `check_qualification()` in classifier.py is deliberately NOT a
  black-box automatic classifier - it returns a structured prompt for
  human (your) review. Design decision, not an unfinished feature.
- The grounding check is lexical overlap, not semantic entailment
  (see above).
- The FastAPI CORS policy is wide open (`allow_origins=["*"]`) -
  acceptable for this assessment's single-consumer demo, not for a
  real deployment with untrusted origins.
- The vector store rebuilds fully on every index call - the right
  tradeoff at 50 records, the wrong one at scale (see Chunking
  strategy above).
- 13F `value` figures are NOT reliably usable as position size or AUM
  without independent cross-checking, beyond the joint-filing case
  already handled by `get_filing_summary()`. Confirmed live during
  enrichment: West Family Investments' own 13F total was independently
  verified at ~$383M, but a later bulk pull of "top holding value" for
  a batch of 21 other filers returned a figure of $34B for this same
  firm - 89x its real size, with `otherIncludedManagersCount=0` (so
  the existing joint-filing check didn't and wouldn't catch it). Root
  cause not fully diagnosed (schema-version differences across filers'
  XML are suspected). Response: dollar values were dropped from
  `recent_activity` for every firm in that batch except the two where
  the value was independently plausible against already-verified AUM;
  only the holding name and filing date were kept as the verified
  signal. This is a second, distinct 13F pitfall beyond the
  joint-filing one already documented above - don't assume a clean
  `otherIncludedManagersCount=0` fully clears a value figure for use.
