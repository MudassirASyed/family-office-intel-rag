"""
Thin wrapper around Chroma. Kept separate from rag.py so the
orchestrator doesn't know or care that Chroma specifically is the
vector store underneath it.

Rebuild-on-index, not incremental upsert: at the scale of this
assessment (50 records, ~150 chunks), re-embedding the whole
collection on every index_records() call takes a few seconds and
removes an entire class of bugs (stale chunks from a since-deleted
or since-edited record lingering in the index). Incremental
diffing would be the right call at 50,000 records; at 50 it's
premature complexity that only adds ways to be wrong. That's the
tradeoff, made on purpose.
"""
import chromadb
from chromadb.utils import embedding_functions

from config import CHROMA_PERSIST_DIR, CHROMA_COLLECTION_NAME
from retrieval.chunking import Chunk


class VectorStore:
    def __init__(
        self,
        persist_dir: str = CHROMA_PERSIST_DIR,
        collection_name: str = CHROMA_COLLECTION_NAME,
    ):
        self.client = chromadb.PersistentClient(path=persist_dir)
        # Hosted embedding API (Cohere), not a locally-loaded model.
        # Two local approaches were tried and rejected on Render's
        # free-tier 512MB cap: sentence-transformers/PyTorch (~650-700MB
        # process) and Chroma's bundled ONNX runtime (~150MB steady
        # state, but still OOM-killed intermittently during startup/
        # reindex - close enough to the ceiling to be unreliable, not a
        # fix). Calling a hosted API - the same pattern already used for
        # Groq (generation) and NewsAPI (discovery) - means no embedding
        # model of any kind runs in this process; the API service is
        # just FastAPI + chromadb's vector math + outbound HTTP calls.
        self.embed_fn = embedding_functions.CohereEmbeddingFunction(
            model_name="embed-english-v3.0"
        )
        self.collection_name = collection_name
        self.collection = self.client.get_or_create_collection(
            name=collection_name, embedding_function=self.embed_fn
        )

    def rebuild(self, chunks: list[Chunk], batch_size: int = 25) -> int:
        """
        Wipe and re-populate the collection from scratch. Returns chunk count.

        Embeds in small batches rather than one `add()` call for the whole
        corpus - encoding ~150 texts through the ONNX model in a single
        batch was enough of a memory spike to OOM-kill the process on
        Render's free tier (512MB) even though steady-state usage
        afterward is only ~150MB. Batching trades a few hundred
        milliseconds of extra startup time for a much lower peak.
        """
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name, embedding_function=self.embed_fn
        )
        if not chunks:
            return 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            self.collection.add(
                ids=[c.id for c in batch],
                documents=[c.text for c in batch],
                metadatas=[c.metadata for c in batch],
            )
        return len(chunks)

    def count(self) -> int:
        return self.collection.count()

    def all_records_metadata(self) -> list[dict]:
        """
        Every distinct firm currently indexed, deduped from per-chunk
        metadata (a firm can have up to 3 chunks). This is the structured
        side of hybrid retrieval - used for aggregate questions ("how many
        SFOs do you have") where semantic top-k similarity search would
        only surface a handful of chunks and can't answer a corpus-wide
        count correctly.
        """
        data = self.collection.get(include=["metadatas"])
        seen: dict[str, dict] = {}
        for m in data.get("metadatas", []):
            name = m.get("name", "unknown")
            if name not in seen:
                seen[name] = m
        return list(seen.values())

    def query(
        self,
        query_text: str,
        n_results: int = 8,
        min_confidence: float = 0.0,
        firm_type: str | None = None,
        chunk_type: str | None = None,
    ) -> dict:
        """
        Semantic search (query_text -> embedding similarity) combined
        with structured metadata filters (min_confidence / firm_type /
        chunk_type) - the hybrid retrieval the brief asks for, not
        semantic-only.
        """
        conditions = []
        if min_confidence > 0:
            conditions.append({"confidence": {"$gte": min_confidence}})
        if firm_type:
            conditions.append({"firm_type": {"$eq": firm_type}})
        if chunk_type:
            conditions.append({"chunk_type": {"$eq": chunk_type}})

        where = None
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        return self.collection.query(
            query_texts=[query_text], n_results=n_results, where=where
        )
