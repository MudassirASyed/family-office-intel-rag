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
_COUNT_QUERY_RE = re.compile(
    r"\bhow many\b.*\b(sfo|mfo|single[- ]family|multi[- ]family|family offices?|records?|firms?)\b",
    re.IGNORECASE,
)


def _is_count_query(query: str) -> bool:
    return bool(_COUNT_QUERY_RE.search(query))


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

    def index_records(self, records: list[dict]) -> int:
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
            f"The dataset currently contains {len(filtered)} firm(s) matching your filters: "
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

        if _is_count_query(query):
            return self._answer_count_query(min_confidence, firm_type)

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
