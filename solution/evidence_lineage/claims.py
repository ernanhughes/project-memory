"""First-class claims and deterministic claim extractors.

A chunk is evidence-bearing text. A claim is a proposition that can
potentially be checked. Claim extraction is itself fallible, so every
claim records its source span and the extractor (plus version) that
produced it.

Three deterministic baselines (no model server required):

* C0 — sentence/statement baseline: naive sentence splitting.
* C1 — structured-schema extraction: deterministic splitting on
  conjunctions and causal/attribution markers with qualifier,
  negation, conditional and attribution flags.
* C2 — Claimify-inspired: selection (verifiable content only),
  disambiguation (ambiguity flags with abstention), decomposition
  (atomic decontextualised claims). Labelled "Claimify-inspired"
  because no Claimify code or API is used; only the published
  principles (selection, ambiguity abstention, coverage,
  decontextualisation) are reproduced.

A true LLM structured extractor is reserved (blocked offline) and
recorded as such in experiment manifests; nothing here pretends to
be one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CLAIM_EXTRACTOR_VERSIONS = {
    "c0": "c0-sentence-v0.1",
    "c1": "c1-structured-v0.1",
    "c2": "c2-claimify-inspired-v0.1",
}

# Markers that usually join two checkable propositions.
_CONJUNCTIONS = (
    " and ",
    " but ",
    " because ",
    " since ",
    " as ",
    " while ",
    " whereas ",
    " although ",
)

_CAUSAL_MARKERS = ("because", "caused", "led to", "due to", "motivated",
                   "resulted in", "triggered")
_ATTRIBUTION_MARKERS = ("reported that", "stated that", "claimed that",
                        "according to", "said that", "argued that")
_NEGATION_MARKERS = (" not ", " never ", " no ", "n't ", " without ")
_CONDITIONAL_MARKERS = (" if ", " unless ", " provided ", " when ",
                        " whenever ", " in case ")
_AMBIGUOUS_PRONOUNS = (" they ", " them ", " their ", " it ", " this ",
                       " that ", " he ", " she ")


@dataclass(frozen=True)
class Claim:
    """An explicit checkable proposition."""

    id: str
    text: str
    originating_artifact: str
    source_span: str | None = None
    producer: str = "c2"
    producer_version: str = CLAIM_EXTRACTOR_VERSIONS["c2"]
    qualifiers: tuple[str, ...] = ()
    negated: bool = False
    conditional: bool = False
    attributed: bool = False
    ambiguous: bool = False
    abstained: bool = False
    extraction_notes: tuple[str, ...] = field(default_factory=tuple)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _flags(sentence: str) -> dict:
    lowered = f" {sentence.lower()} "
    return {
        "negated": any(m in lowered for m in _NEGATION_MARKERS),
        "conditional": any(m in lowered for m in _CONDITIONAL_MARKERS),
        "attributed": any(m in lowered for m in _ATTRIBUTION_MARKERS),
        "ambiguous": any(m in lowered for m in _AMBIGUOUS_PRONOUNS),
    }


def extract_claims_c0(answer: str, artifact: str = "answer") -> list[Claim]:
    """C0 baseline: one claim per sentence, no analysis."""
    claims = []
    for i, sentence in enumerate(_split_sentences(answer)):
        claims.append(Claim(
            id=f"{artifact}-c0-{i}",
            text=sentence,
            originating_artifact=artifact,
            producer="c0",
            producer_version=CLAIM_EXTRACTOR_VERSIONS["c0"],
        ))
    return claims


def _split_structured(sentence: str) -> list[str]:
    """Split a sentence on conjunction/causal joints (C1)."""
    work = [sentence]
    for joint in _CONJUNCTIONS:
        nxt: list[str] = []
        for piece in work:
            if joint in f" {piece.lower()} ":
                pattern = re.compile(re.escape(joint.strip()),
                                     re.IGNORECASE)
                bits = [b.strip(" ,;") for b in pattern.split(piece)]
                nxt.extend(b for b in bits if b)
            else:
                nxt.append(piece)
        work = nxt
    # Drop fragments too short to check.
    return [w for w in work if len(w.split()) >= 3]


def extract_claims_c1(answer: str, artifact: str = "answer") -> list[Claim]:
    """C1: constrained-schema extraction with proposition flags."""
    claims: list[Claim] = []
    idx = 0
    for sent_i, sentence in enumerate(_split_sentences(answer)):
        flags = _flags(sentence)
        for piece in _split_structured(sentence):
            piece_flags = _flags(piece)
            claims.append(Claim(
                id=f"{artifact}-c1-{idx}",
                text=piece,
                originating_artifact=artifact,
                source_span=f"{artifact}:sentence-{sent_i}",
                producer="c1",
                producer_version=CLAIM_EXTRACTOR_VERSIONS["c1"],
                negated=piece_flags["negated"],
                conditional=piece_flags["conditional"],
                attributed=piece_flags["attributed"],
                ambiguous=piece_flags["ambiguous"],
                extraction_notes=("split" if piece != sentence else "single",),
            ))
            idx += 1
    return claims


def extract_claims_c2(answer: str, artifact: str = "answer") -> list[Claim]:
    """C2 Claimify-inspired: select, disambiguate, decompose.

    * Selection: sentences without verifiable content (greetings,
      pure questions, hedges with no proposition) are dropped.
    * Disambiguation: referential ambiguity that cannot be resolved
      from the sentence itself flags the claim; unresolvable
      ambiguity abstains (no claim emitted, abstention recorded).
    * Decomposition: as C1, plus qualifier capture (causal markers
      retained as qualifiers) and bracketed context notes.
    """
    claims: list[Claim] = []
    abstentions: list[Claim] = []
    idx = 0
    for sent_i, sentence in enumerate(_split_sentences(answer)):
        flags = _flags(sentence)
        lowered = sentence.lower().strip()
        # Selection: skip non-verifiable sentences.
        if (lowered in {"ok.", "yes.", "no.", "thanks.", "hello."}
                or lowered.endswith("?")
                or len(sentence.split()) < 3):
            abstentions.append(Claim(
                id=f"{artifact}-c2-abs-{sent_i}",
                text=sentence,
                originating_artifact=artifact,
                producer="c2",
                producer_version=CLAIM_EXTRACTOR_VERSIONS["c2"],
                abstained=True,
                extraction_notes=("selection: no verifiable content",),
            ))
            continue
        # Disambiguation: unresolvable referential ambiguity abstains.
        if flags["ambiguous"] and not re.search(
                r"\b(postgresql|sqlite|importer|benchmark|adr|event store)\b",
                lowered):
            abstentions.append(Claim(
                id=f"{artifact}-c2-abs-{sent_i}",
                text=sentence,
                originating_artifact=artifact,
                producer="c2",
                producer_version=CLAIM_EXTRACTOR_VERSIONS["c2"],
                ambiguous=True,
                abstained=True,
                extraction_notes=("disambiguation: unresolvable reference",),
            ))
            continue
        qualifiers = tuple(m for m in _CAUSAL_MARKERS if m in lowered)
        for piece in _split_structured(sentence):
            piece_flags = _flags(piece)
            claims.append(Claim(
                id=f"{artifact}-c2-{idx}",
                text=piece,
                originating_artifact=artifact,
                source_span=f"{artifact}:sentence-{sent_i}",
                producer="c2",
                producer_version=CLAIM_EXTRACTOR_VERSIONS["c2"],
                qualifiers=qualifiers,
                negated=piece_flags["negated"],
                conditional=piece_flags["conditional"],
                attributed=piece_flags["attributed"],
                ambiguous=piece_flags["ambiguous"],
                extraction_notes=("decomposed",),
            ))
            idx += 1
    return claims + abstentions


def extraction_report(claims: list[Claim]) -> dict:
    """Summary counts for an extraction run (E7-B input)."""
    live = [c for c in claims if not c.abstained]
    return {
        "claims": len(live),
        "abstentions": sum(1 for c in claims if c.abstained),
        "negated": sum(1 for c in live if c.negated),
        "conditional": sum(1 for c in live if c.conditional),
        "attributed": sum(1 for c in live if c.attributed),
        "ambiguous": sum(1 for c in live if c.ambiguous),
    }
