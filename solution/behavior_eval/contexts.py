"""Memory conditions built from frozen artifacts only (§18).

Every context string is hashed (sha256) and every source run recorded,
so the reader input is frozen by condition. Runtime never sees hidden
labels: MA/MR/MW/MS are constructed by unit-ID surgery on frozen
renders/bundles, and the ledger IDs they use are recorded as
intervention metadata, not shown to the reader.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CH10_RUN = (REPO_ROOT / "experiments" / "benchmark" / "runs"
            / "ch10-20260920T163314Z-context-frames")
CH14_RUN = (REPO_ROOT / "experiments" / "benchmark" / "runs"
            / "ch14-20260920T174259Z-context-assembly")

# Behaviour conditions used across tasks (§41 ladder).
# B1 = all 68 visible units across three projects (contamination
# control); B1P = the 57 Memory-project units only. The pair
# distinguishes "too much relevant history" from "foreign-project
# contamination" (review repair item 3).
CONDITIONS = ("B0", "B1", "B1P", "B2", "B3", "B4", "BO",
              "BA", "BR", "BW", "BS")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _load_json(path: Path):
    return json.loads(path.read_text())


def corpus_texts() -> dict[str, dict]:
    """Corpus units: id -> {text, kind, source_refs, project_id}.

    Membership/metadata come from the frozen ch10 corpus.jsonl; texts
    come from the versioned corpus code, cross-checked against the
    frozen per-unit token counts so a text drift can never silently
    change a frozen context (code commit is in every manifest).
    """
    import sys
    sys.path.insert(0, str(REPO_ROOT / "solution"))
    from context_frames.corpus import corpus as live_corpus
    from context_frames.model import estimate_tokens
    frozen = {}
    for line in (CH10_RUN / "corpus.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        frozen[row["unit_id"]] = row
    out = {}
    for unit in live_corpus():
        row = frozen.get(unit.unit_id, {})
        if row and row.get("tokens") != estimate_tokens(unit.text):
            raise ValueError(
                f"corpus text drift for {unit.unit_id}: frozen tokens "
                f"{row.get('tokens')} vs live "
                f"{estimate_tokens(unit.text)}")
        out[unit.unit_id] = {
            "text": unit.text, "kind": unit.kind,
            "source_refs": list(unit.source_refs),
            "project_id": unit.project_id,
            "tokens": estimate_tokens(unit.text),
        }
    return out


def render_bundle_members(bundle: dict, texts: dict[str, dict]) -> str:
    """Deterministic render of a frozen ch10 bundle from member texts."""
    parts = []
    for item in bundle.get("items", ()):
        members = item.get("members", ())
        refs: list[str] = []
        for mid in members:
            for ref in texts.get(mid, {}).get("source_refs", ()):
                if ref not in refs:
                    refs.append(ref)
        header = (f"[{item.get('kind', 'evidence')} | sources: "
                  f"{', '.join(refs) or 'unsourced'} | "
                  f"item {item.get('item_id', '')}]")
        body = "\n".join(texts[m]["text"] for m in members if m in texts)
        parts.append(f"{header}\n{body}")
    return "\n\n---\n\n".join(parts)


def load_bundle(task_id: str, condition: str) -> dict:
    path = CH10_RUN / "bundles" / f"{task_id}-{condition}.json"
    return _load_json(path)


def load_render(condition: str, budget: str, task_id: str) -> str:
    path = CH14_RUN / "rendered-contexts" / f"{condition}-budget-{budget}.json"
    return _load_json(path)[task_id]


def ch10_task_ids() -> list[str]:
    return sorted(p.name[:-len("-C5.json")]
                  for p in (CH10_RUN / "bundles").glob("*-C5.json"))


def full_history_text(texts: dict[str, dict],
                      project: str | None = None) -> str:
    """All visible units, optionally restricted to one project.

    Unrestricted (B1): 68 units across memory-book/writer/cocoder.
    Project-restricted (B1P): 57 memory-book units only.
    """
    parts = []
    for uid in sorted(texts):
        row = texts[uid]
        if project is not None and row.get("project_id") != project:
            continue
        refs = ", ".join(row.get("source_refs", ())) or "unsourced"
        parts.append(f"[{row.get('project_id', '')} | sources: {refs} | "
                     f"item {uid}]\n{row['text']}")
    return "\n\n---\n\n".join(parts)


def history_counts(texts: dict[str, dict]) -> dict:
    from collections import Counter
    return dict(Counter(r.get("project_id", "?") for r in texts.values()))


def strip_units(rendered: str, unit_ids: set[str]) -> str:
    """Remove evidence blocks naming any of unit_ids (MA surgery).

    Ch14 renders mark blocks with `item <unit_id>` headers; ch10-style
    renders use the same header convention. Blocks are `---` separated.
    """
    blocks = rendered.split("\n\n---\n\n")
    kept = [b for b in blocks
            if not any(f"item {uid}" in b for uid in unit_ids)]
    return "\n\n---\n\n".join(kept)


def append_units(rendered: str, unit_ids: list[str],
                 texts: dict[str, dict], note: str) -> str:
    blocks = [rendered] if rendered.strip() else []
    for uid in unit_ids:
        row = texts.get(uid)
        if row is None:
            continue
        refs = ", ".join(row.get("source_refs", ())) or "unsourced"
        blocks.append(f"[{row.get('kind', 'evidence')} | sources: {refs} "
                      f"| item {uid}]\n[{note}]\n{row['text']}")
    return "\n\n---\n\n".join(blocks)


def texts_of(unit_ids: list[str], texts: dict[str, dict],
             note: str) -> str:
    return append_units("", unit_ids, texts, note)


def build_condition(task_id: str, condition: str, texts: dict[str, dict],
                    decisive: tuple[str, ...],
                    wrong_units: tuple[str, ...],
                    ch10_task: str | None = None) -> dict:
    """Return {context, memory_ids, context_hash, tokens, note}.

    `ch10_task` selects which frozen ch10/ch14 task supplies the
    bundle (defaults to task_id when it is a ch10 task id).
    """
    src = ch10_task or task_id
    if condition == "B0":
        return {"context": "", "memory_ids": [], "note": "no memory"}
    if condition == "B1":
        context = full_history_text(texts)
        return {"context": context, "memory_ids": sorted(texts),
                "note": "full visible history (68 units, 3 projects)"}
    if condition == "B1P":
        context = full_history_text(texts, project="memory-book")
        ids = sorted(uid for uid, row in texts.items()
                     if row.get("project_id") == "memory-book")
        return {"context": context, "memory_ids": ids,
                "note": "full Memory-project history only (57 units)"}
    if condition == "B2":
        bundle = load_bundle(src, "C0")
        context = render_bundle_members(bundle, texts)
        return {"context": context,
                "memory_ids": _members(bundle),
                "note": f"frozen {src}-C0"}
    if condition == "B3":
        bundle = load_bundle(src, "C5")
        context = render_bundle_members(bundle, texts)
        return {"context": context,
                "memory_ids": _members(bundle),
                "note": f"frozen {src}-C5"}
    if condition == "B4":
        context = load_render("A6-composed", "768", src)
        return {"context": context,
                "memory_ids": ["frozen-render"],
                "note": f"frozen {src} A6@768 render"}
    if condition == "BO":
        context = load_render("CO-auditable", "full", src)
        return {"context": context,
                "memory_ids": ["frozen-render"],
                "note": f"frozen {src} CO-auditable render (ceiling)"}
    if condition == "BA":
        base = load_render("A6-composed", "768", src)
        context = strip_units(base, set(decisive))
        return {"context": context, "memory_ids": ["frozen-render-minus"],
                "note": f"A6@768 minus decisive {sorted(decisive)}"}
    if condition == "BR":
        base = load_render("A6-composed", "768", src)
        stripped = strip_units(base, set(decisive))
        context = append_units(stripped, list(decisive), texts,
                               "restored decisive evidence")
        return {"context": context, "memory_ids": ["frozen-render-plus"],
                "note": f"BA plus restored {sorted(decisive)}"}
    if condition == "BW":
        context = texts_of(list(wrong_units), texts,
                           "unfiltered memory listing")
        return {"context": context, "memory_ids": list(wrong_units),
                "note": "wrong/stale memory positive control"}
    if condition == "BS":
        base = load_render("A6-composed", "768", src)
        context = strip_units(base, set(decisive))
        # Substitution set: distractor members of the same C5 bundle.
        bundle = load_bundle(src, "C5")
        distractors = _distractors(bundle, decisive)
        context = append_units(
            context, distractors, texts,
            "substituted evidence (scrambled control)")
        return {"context": context, "memory_ids": ["frozen-render-mixed"],
                "note": "decisive replaced by distractors"}
    raise ValueError(f"unknown condition {condition}")


def _members(bundle: dict) -> list[str]:
    out: list[str] = []
    for item in bundle.get("items", ()):
        out.extend(item.get("members", ()))
    return out


def _distractors(bundle: dict,
                 decisive: tuple[str, ...]) -> list[str]:
    """Distractor members of a C5 bundle via ch10 fixture ledgers."""
    import sys
    sys.path.insert(0, str(REPO_ROOT / "solution"))
    from context_frames import fixtures as fx
    ledgers = {t.task_id: t.ledger for t in fx.all_tasks()}
    task_id = bundle.get("bundle_id", "")[3:].rsplit("-", 1)[0]
    ledger = ledgers.get(task_id, {})
    return [u for u in _members(bundle)
            if ledger.get(u) == "DISTRACTOR" and u not in decisive][:4]


def finalize(entry: dict) -> dict:
    context = entry["context"]
    entry["context_hash"] = sha(context)
    entry["tokens"] = estimate_tokens(context)
    return entry
