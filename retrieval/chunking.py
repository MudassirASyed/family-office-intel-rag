"""
Chunking strategy for the Micro-RAG.

Why not fixed-size token windows: these records are short, structured
rows, not long prose documents. Splitting a 40-word description into
overlapping 200-token windows would just fragment it for no benefit.
The chunking boundary that actually matters here is semantic, and the
brief already hands us the right one - it defines the value of a
record in three named categories:

    1. Entity Attributes      (what the firm is, what it invests in)
    2. Principal Intelligence (who to contact)
    3. Signals / Recent Activity (why to contact them now)

These three things get asked about differently ("who invests in AI"
vs. "who do I call at X" vs. "what has X done lately") and a query
embedding shouldn't have to compete against all three blended into one
paragraph. So each record becomes up to 3 chunks, one per category,
skipped when there's nothing in that category to say. This is a
hybrid retrieval design: chunk_type/firm_type/confidence are exact-
match metadata (structured retrieval), the chunk text is embedded
(semantic retrieval), and a query can combine both.

Tradeoff, stated plainly: this only works because records are short
and field-based. It would not generalize to ingesting a long PDF or
filing - that would need real token-windowed chunking. Don't pretend
otherwise.
"""
from dataclasses import dataclass, field


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict = field(default_factory=dict)


def _clean(*parts: str) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip())


def build_chunks(record: dict, record_id: str) -> list[Chunk]:
    """
    Turn one Family Office record into 1-3 semantically distinct
    chunks. A record with no free text anywhere still produces at
    least a minimal profile chunk (the firm name + type), so it
    remains findable by name even when enrichment is thin.
    """
    base_meta = {
        "record_id": record_id,
        "name": record.get("name", ""),
        "firm_type": record.get("firm_type", "unclear"),
        "firm_qualifies": bool(record.get("firm_qualifies", False)),
        "confidence": float(record.get("confidence", 0.0)),
        "city": record.get("city", ""),
        "state": record.get("state", ""),
        "country": record.get("country", ""),
    }

    chunks: list[Chunk] = []

    # 1. Profile / entity attributes
    profile_text = _clean(
        record.get("name", ""),
        f"({record.get('firm_type', 'unclear').replace('_', ' ')})" if record.get("firm_type") else "",
        record.get("description", ""),
        f"Investment thesis: {record['investment_thesis']}." if record.get("investment_thesis") else "",
        f"Sectors: {record['investing_sectors']}." if record.get("investing_sectors") else "",
        f"AUM: {record['aum']}." if record.get("aum") else "",
        f"Location: {', '.join(x for x in [record.get('city'), record.get('state'), record.get('country')] if x)}."
        if any([record.get("city"), record.get("state"), record.get("country")]) else "",
    )
    if profile_text:
        chunks.append(Chunk(
            id=f"{record_id}::profile",
            text=profile_text,
            metadata={**base_meta, "chunk_type": "profile"},
        ))

    # 2. Principal / decision-maker intelligence
    if record.get("principal_name"):
        principal_text = _clean(
            f"{record['principal_name']}, {record.get('principal_title', 'principal')} at {record.get('name', '')}.",
            f"Email: {record['principal_email']}." if record.get("principal_email") else "",
            f"Phone: {record['principal_phone']}." if record.get("principal_phone") else "",
        )
        chunks.append(Chunk(
            id=f"{record_id}::principal",
            text=principal_text,
            metadata={**base_meta, "chunk_type": "principal"},
        ))

    # 3. Signals / recent activity - the "why now" layer
    signal_text = _clean(
        f"Recent activity at {record.get('name', '')}: {record['recent_activity']}"
        f" (as of {record['recent_activity_date']})." if record.get("recent_activity") else "",
        f"Qualification basis for {record.get('name', '')}: {record['qualification_evidence']}"
        if record.get("qualification_evidence") else "",
    )
    if signal_text:
        chunks.append(Chunk(
            id=f"{record_id}::signals",
            text=signal_text,
            metadata={
                **base_meta,
                "chunk_type": "signals",
                "recent_activity_date": record.get("recent_activity_date", ""),
            },
        ))

    # Fallback: nothing but a name and a type. Still index it so the
    # firm is findable - an honest "we have almost nothing on this
    # firm" is better than the firm silently vanishing from search.
    if not chunks:
        chunks.append(Chunk(
            id=f"{record_id}::profile",
            text=_clean(record.get("name", ""), record.get("firm_type", "unclear")),
            metadata={**base_meta, "chunk_type": "profile"},
        ))

    return chunks


def build_all_chunks(records: list[dict]) -> list[Chunk]:
    chunks = []
    for i, r in enumerate(records):
        chunks.extend(build_chunks(r, record_id=f"rec_{i}"))
    return chunks
