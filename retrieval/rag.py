"""
Micro-RAG orchestrator. Composes four pieces that each live in their
own module on purpose (retrieval/data/generation stay separable and
independently testable):

    chunking.py    -> turns a record into semantically-scoped chunks
    vectorstore.py -> structured + semantic retrieval over those chunks
    generator.py   -> the LLM call
    grounding.py   -> the post-hoc control that checks the LLM obeyed

This file's job is only to wire them together and decide what the
user-facing response looks like when something upstream fails. It
does not embed, call Chroma, or call Groq directly - see the modules
above for that.
"""
import re
from dataclasses import dataclass, field
from difflib import get_close_matches

from retrieval.chunking import build_all_chunks
from retrieval.vectorstore import VectorStore
from retrieval.generator import AnswerGenerator, GenerationError
from retrieval.grounding import check_grounding
from config import DEFAULT_N_RESULTS

# Aggregate/count questions ("how many SFOs do you have") can't be answered
# correctly from a top-k semantic slice - the LLM only sees whichever 8
# chunks matched, not the whole corpus, and will confidently miscount.
# Caught live in browser testing: "how many SFO u have in records" returned
# "There is only 1... Soros Fund Management" even though the dataset has 28,
# and it passed the lexical grounding check because that one name genuinely
# appeared in the (partial) retrieved context - the wrong count wasn't an
# invented claim, it was a reasoning error over incomplete context. Fixed by
# routing count-shaped questions to the structured side of retrieval
# (VectorStore.all_records_metadata(), the full corpus) instead of the
# semantic side, and answering deterministically without an LLM call.
#
# A first version matched one exact regex phrase and silently fell through
# to the same broken LLM-guessing path on anything that didn't match it
# word-for-word. Caught live, again: a real typo ("how many recoreds are in
# dataset in total" instead of "records") missed the exact regex entirely
# and reproduced the original bug. On a public deployed URL, real users
# will mistype and rephrase, so exact-string matching isn't good enough -
# detection now needs a trigger phrase (tolerant of a few common phrasings)
# plus a fuzzy (typo-tolerant) check that the question is actually about
# this dataset's firms, not a hard-coded literal sentence.
_COUNT_TRIGGER_RE = re.compile(
    r"\b(how many|how much|count of|number of|total number)\b", re.IGNORECASE
)
_SCOPE_KEYWORDS = [
    "sfo", "mfo", "single-family", "multi-family", "family", "families",
    "offices", "office", "records", "record", "firms", "firm", "dataset",
    "total",
]


# The sidebar's confidence slider and a threshold typed *inside* the
# question ("show every firm with confidence above 50%") are two
# separate inputs - min_confidence was only ever read from the sidebar,
# so typing a threshold in text while the slider sat at 0.0 was
# silently ignored (the text-stated intent never took effect, no error,
# no indication anything was dropped). Extracted here and combined with
# whatever the sidebar sent - the stricter (higher) of the two wins,
# and the effective value actually used is always stated in the answer
# for the two structured paths below, so it's never silently ambiguous
# even for phrasings this regex doesn't catch.
_CONFIDENCE_THRESHOLD_RE = re.compile(
    r"confidence\D{0,20}?(\d+(?:\.\d+)?)\s*%?|(\d+(?:\.\d+)?)\s*%?\D{0,20}?confidence",
    re.IGNORECASE,
)


def _extract_text_confidence_threshold(query: str) -> float | None:
    match = _CONFIDENCE_THRESHOLD_RE.search(query)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    value = float(raw)
    if value > 1:
        value /= 100.0
    return max(0.0, min(1.0, value))


def _is_count_query(query: str) -> bool:
    if not _COUNT_TRIGGER_RE.search(query):
        return False
    words = re.findall(r"[a-z]+", query.lower())
    for w in words:
        if w in ("sfo", "mfo"):
            return True  # short acronyms: exact match only, too short to fuzzy-match safely
        if len(w) >= 4 and get_close_matches(w, _SCOPE_KEYWORDS, n=1, cutoff=0.75):
            return True
    return False


# Same underlying failure mode as the count-query bug above, different
# intent: "list all records / complete dataset view" also needs the
# whole corpus, not a top-8 semantic slice. Caught live on the deployed
# app: "list all records in detail in tabular form, all fields... a
# complete dataset view" returned only 8 records and just 3 fields
# (Organization/Name/Title) - the LLM was, correctly, only shown 8
# chunks and did its best with them, but the answer looked like a
# complete listing when it silently wasn't one. Routed to the same
# structured, full-corpus path as the count query.
_LIST_ALL_TRIGGER_RE = re.compile(
    r"\b(list all|show all|all records|all firms|complete (dataset|list|view)|"
    r"full (dataset|list)|entire dataset|every (record|firm)|tabular (form|view))\b",
    re.IGNORECASE,
)


_COMPLETENESS_WORDS = ["all", "complete", "entire", "every", "full", "whole"]


def _is_list_all_query(query: str) -> bool:
    if _LIST_ALL_TRIGGER_RE.search(query):
        return True
    # Fuzzy fallback for typos in the trigger phrase itself (e.g. "list
    # al records"). Requires a completeness word AND a dataset-scope
    # word - just "list"/"show" alone is a normal semantic question
    # ("show me family offices investing in AI") and must not be routed
    # here.
    words = re.findall(r"[a-z]+", query.lower())
    has_completeness = any(
        w in _COMPLETENESS_WORDS
        or (len(w) >= 4 and get_close_matches(w, _COMPLETENESS_WORDS, n=1, cutoff=0.8))
        for w in words
    )
    if not has_completeness:
        return False
    for w in words:
        if w in ("sfo", "mfo"):
            return True
        if len(w) >= 4 and get_close_matches(w, _SCOPE_KEYWORDS, n=1, cutoff=0.75):
            return True
    return False


@dataclass
class Source:
    name: str
    firm_type: str
    confidence: float
    chunk_type: str

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class RagResponse:
    answer: str
    grounded: bool
    status: str  # "ok" | "no_results" | "ungrounded" | "generation_unavailable" | "generation_error"
    sources: list[Source] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "grounded": self.grounded,
            "status": self.status,
            "sources": [s.to_dict() for s in self.sources],
        }


class MicroRAG:
    def __init__(self):
        self.store = VectorStore()
        self.generator = AnswerGenerator()
        self.records: list[dict] = []

    def index_records(self, records: list[dict]) -> int:
        self.records = records
        chunks = build_all_chunks(records)
        return self.store.rebuild(chunks)

    def record_count_indexed(self) -> int:
        return self.store.count()

    def _sources_from(self, metas: list[dict]) -> list[Source]:
        # One row per firm, not per chunk - a user doesn't want to see
        # "Hillspire" listed 3 times because it matched on 3 chunk types.
        seen: dict[str, Source] = {}
        for m in metas:
            name = m.get("name", "unknown")
            if name not in seen:
                seen[name] = Source(
                    name=name,
                    firm_type=m.get("firm_type", "unclear"),
                    confidence=float(m.get("confidence", 0.0)),
                    chunk_type=m.get("chunk_type", ""),
                )
        return list(seen.values())

    def _answer_count_query(self, min_confidence: float, firm_type: str | None) -> RagResponse:
        all_meta = self.store.all_records_metadata()
        filtered = [
            m for m in all_meta
            if float(m.get("confidence", 0.0)) >= min_confidence
            and (firm_type is None or m.get("firm_type") == firm_type)
        ]
        sfo = sum(1 for m in filtered if m.get("firm_type") == "single_family_office")
        mfo = sum(1 for m in filtered if m.get("firm_type") == "multi_family_office")
        other = len(filtered) - sfo - mfo

        parts = [
            f"{sfo} single-family office{'s' if sfo != 1 else ''}",
            f"{mfo} multi-family office{'s' if mfo != 1 else ''}",
        ]
        if other:
            parts.append(f"{other} unclassified")
        answer = (
            f"The dataset currently contains {len(filtered)} firm(s) matching your filters "
            f"(minimum confidence {round(min_confidence * 100)}%): "
            + ", ".join(parts) + ". This is an exact count over the full indexed dataset, "
            "not a semantic-search estimate."
        )
        return RagResponse(
            answer=answer,
            grounded=True,
            status="ok",
            sources=[
                Source(
                    name=m.get("name", "unknown"),
                    firm_type=m.get("firm_type", "unclear"),
                    confidence=float(m.get("confidence", 0.0)),
                    chunk_type="profile",
                )
                for m in filtered
            ],
        )

    def _answer_list_all_query(self, min_confidence: float, firm_type: str | None) -> RagResponse:
        filtered = [
            r for r in self.records
            if float(r.get("confidence", 0.0)) >= min_confidence
            and (firm_type is None or r.get("firm_type") == firm_type)
        ]
        filtered.sort(key=lambda r: r.get("name", ""))

        def cell(v) -> str:
            v = (v or "").strip() if isinstance(v, str) else v
            return str(v) if v else "N/A"  # plain ASCII - avoid Unicode console/encoding issues

        header = "| Name | Type | Location | Principal | Title | AUM | Confidence |"
        sep = "|---|---|---|---|---|---|---|"
        rows = []
        for r in filtered:
            location = ", ".join(
                p for p in [r.get("city"), r.get("state"), r.get("country")] if p
            ) or "N/A"
            type_label = {
                "single_family_office": "SFO", "multi_family_office": "MFO",
            }.get(r.get("firm_type"), "Unclear")
            rows.append(
                f"| {cell(r.get('name'))} | {type_label} | {location} | "
                f"{cell(r.get('principal_name'))} | {cell(r.get('principal_title'))} | "
                f"{cell(r.get('aum'))} | {round(float(r.get('confidence', 0.0)) * 100)}% |"
            )

        table = "\n".join([header, sep] + rows)
        answer = (
            f"Complete dataset view - {len(filtered)} firm(s) matching your filters "
            f"(minimum confidence {round(min_confidence * 100)}%), core fields (not the "
            f"full schema - see the source dataset file for verification sources/evidence "
            f"per field):\n\n{table}"
        )
        return RagResponse(
            answer=answer,
            grounded=True,
            status="ok",
            sources=[
                Source(
                    name=r.get("name", "unknown"),
                    firm_type=r.get("firm_type", "unclear"),
                    confidence=float(r.get("confidence", 0.0)),
                    chunk_type="profile",
                )
                for r in filtered
            ],
        )

    def grounded_answer(
        self,
        query: str,
        min_confidence: float = 0.0,
        firm_type: str | None = None,
        n_results: int = DEFAULT_N_RESULTS,
    ) -> RagResponse:
        if not query or not query.strip():
            return RagResponse(
                answer="Please enter a question.",
                grounded=True,
                status="no_results",
            )

        if _is_list_all_query(query) or _is_count_query(query):
            # A threshold typed *inside* the question ("confidence above
            # 50%") is a separate input from the sidebar's min_confidence
            # slider - stated explicitly in text, it should not be
            # silently dropped just because the slider itself is at 0.
            # The stricter (higher) of the two wins.
            text_threshold = _extract_text_confidence_threshold(query)
            effective_min_confidence = (
                max(min_confidence, text_threshold)
                if text_threshold is not None else min_confidence
            )
            if _is_list_all_query(query):
                return self._answer_list_all_query(effective_min_confidence, firm_type)
            return self._answer_count_query(effective_min_confidence, firm_type)

        results = self.store.query(
            query, n_results=n_results, min_confidence=min_confidence, firm_type=firm_type
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]

        # Defense in depth: every chunk is labeled with its firm name at
        # assembly time, not just relied on to be embedded in the chunk
        # text by whoever wrote chunking.py. Caught live: a chunk built
        # only from qualification_evidence omitted the name, and the LLM
        # answered "the family office ranked #1... name not specified"
        # even though the name was right there in metadata. Labeling here
        # makes that failure mode structurally impossible, regardless of
        # what future chunk types get added.
        labeled_docs = [f"[{m.get('name', 'Unknown firm')}] {d}" for d, m in zip(docs, metas)]

        if not docs:
            return RagResponse(
                answer="No records in the dataset match this query at the selected confidence level. "
                       "Try lowering the minimum confidence or rephrasing the question.",
                grounded=True,
                status="no_results",
            )

        if not self.generator.available:
            return RagResponse(
                answer="The answer-generation model is not configured (missing API key), "
                       "so only matching records are shown below - no generated summary.",
                grounded=False,
                status="generation_unavailable",
                sources=self._sources_from(metas),
            )

        try:
            raw_answer = self.generator.generate(query, labeled_docs)
        except GenerationError:
            return RagResponse(
                answer="The system found matching records but could not generate a summary right now "
                       "due to a technical issue with the answer-generation service. "
                       "The matching records are shown below.",
                grounded=False,
                status="generation_error",
                sources=self._sources_from(metas),
            )

        grounded, _unsupported = check_grounding(raw_answer, labeled_docs)

        if not grounded:
            return RagResponse(
                answer="The generated answer contained claims that could not be verified against the "
                       "retrieved records, so it has been withheld rather than shown as fact. "
                       "The matching records are shown below so you can review them directly.",
                grounded=False,
                status="ungrounded",
                sources=self._sources_from(metas),
            )

        return RagResponse(
            answer=raw_answer,
            grounded=True,
            status="ok",
            sources=self._sources_from(metas),
        )


if __name__ == "__main__":
    import json
    from config import DATA_PATH

    with open(DATA_PATH) as f:
        records = json.load(f)

    rag = MicroRAG()
    n = rag.index_records(records)
    print(f"Indexed {n} chunks from {len(records)} records.\n")

    for q in [
        "Which family offices are active in AI investing?",
        "Who do I contact at Hillspire?",
        "What has Duquesne Family Office done recently?",
    ]:
        print(f"Q: {q}")
        resp = rag.grounded_answer(q)
        print(json.dumps(resp.to_dict(), indent=2))
        print()
