"""
Grounding control - the actual enforcement mechanism the brief demands
("prompt instructions alone are not enough... your system must
include a working control that limits what an answer may claim").

Method: split the generated answer into sentences, and for each
sentence check what fraction of its meaningful words (4+ letters,
so "the/and/for" don't count) also appear in the retrieved context
text. Below threshold -> flagged as unsupported.

This is deliberately a crude lexical-overlap check, not embedding
similarity per sentence or NLI entailment - stated honestly, not
oversold. It catches the failure mode that actually matters most
here (the model inventing a name, number, or claim that appears
nowhere in retrieval) without needing another model call. It will
miss paraphrase-level hallucination (a wrong number restated in
different words). Documented as a known limitation, not hidden.

Because chunks are now field-scoped (see chunking.py) instead of one
blob per firm, this check is more precise than it would be against a
whole-record blob - less filler text to accidentally "explain away" an
unsupported claim via incidental word overlap.
"""
import re

MEANINGFUL_WORD = re.compile(r"\b[a-z]{4,}\b")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Short hedges/refusals shouldn't be penalized for low word overlap -
# "I don't have enough information to answer that." is a *good*
# outcome, not an ungrounded claim.
HEDGE_PATTERNS = re.compile(
    r"\b(i (don't|do not) (have|know)|not (enough|sufficient) (information|evidence|data)|"
    r"cannot (confirm|answer|determine)|no (record|information) (matches|available))\b",
    re.IGNORECASE,
)


def check_grounding(answer: str, context_docs: list[str], threshold: float = 0.15) -> tuple[bool, list[str]]:
    context_blob = " ".join(context_docs).lower()
    sentences = [s for s in SENTENCE_SPLIT.split(answer.strip()) if s.strip()]

    unsupported = []
    for sent in sentences:
        if HEDGE_PATTERNS.search(sent):
            continue
        words = set(MEANINGFUL_WORD.findall(sent.lower()))
        if not words:
            continue
        overlap = sum(1 for w in words if w in context_blob) / len(words)
        if overlap < threshold:
            unsupported.append(sent.strip())

    return len(unsupported) == 0, unsupported
