"""Frozen corpus builder (H1).

Pipeline: ledger -> render -> ids -> queries -> audits (gate) -> manifest.

Usage:
    python -m generator.build --seed 20240823 --worlds 12 \
        --out experiments/benchmark/fixtures/v0.1

Layout written under --out:
    corpus/artifacts/gen-NNNNNN.md   rendered history (system-visible)
    corpus/queries.jsonl             query inputs WITHOUT answers
    eval/ledger.jsonl                hidden records (evaluator-side only)
    eval/expected.jsonl              expected answers (evaluator-side only)
    eval/oracle.jsonl                E-04 oracle passage sets, no roles
    eval/oracle_roles.jsonl          E-04 oracle passage sets with roles
    eval/build_meta.jsonl            render/template metadata (evaluator-side)
    manifest.json                    version, seed, commit, checksums

No retriever, memory system, or model call is implemented here. The build
aborts (non-zero exit, no manifest) if any leakage audit fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

from . import audits, ids, manifest as manifest_mod, queries
from . import render as render_mod
from . import worlds
from .audits import AUTHORITATIVE
from .schema import Ledger

CORPUS_VERSION = "v0.1"
QUERY_SET_VERSION = "v0.1-q1q2"
DEFAULT_SEED = 20240823
DEFAULT_WORLDS = 12


def render_all(ledger: Ledger, context: list[dict], rng: random.Random,
               world_a_keys: set[str], pick_realisation) -> tuple[list, list]:
    """Render records + context artifacts. Returns (artifacts, build_meta)."""
    artifacts: list = []
    build_meta: list[dict] = []
    for rec in ledger.records:
        if rec.kind == "decision" and rec.render_style == "crisp":
            realisation = pick_realisation(rec.kind)
        elif rec.kind == "decision":
            realisation = {"buried": "session-closing-remark", "split": "session-split"}[
                rec.render_style
            ]
        else:
            realisation = pick_realisation(rec.kind)
        for art in render_mod.render_record(rec, rng, realisation):
            artifacts.append(art)
            build_meta.append(
                {
                    "display_id": art.display_id,
                    "record_key": rec.key,
                    "kind": rec.kind,
                    "scenario": rec.scenario,
                    "world": "world-a" if rec.key in world_a_keys else "parametric",
                    "realisation": art.realisation,
                    "render_style": rec.render_style,
                    "has_timestamp": art.has_timestamp,
                }
            )
    for spec in context:
        art = render_mod.render_context_artifact(spec, rng)
        artifacts.append(art)
    return artifacts, build_meta


def strip_datelineless(ledger: Ledger, artifacts: list, rng: random.Random,
                       rate: float = 0.12) -> None:
    """Stratified dateline stripping: ~rate of session-backed artifacts per
    record kind lose their dateline (seeded choice within kind). Absence is
    therefore independent of kind by construction, matching the ledger rule
    ("sometimes absent") without creating a learnable kind shortcut."""
    record_by_key = ledger.by_key()
    by_kind: dict[str, list] = {}
    for art in artifacts:
        if not art.record_keys or art.kind != "session" or not art.dateline:
            continue
        kind = record_by_key[art.record_keys[0]].kind
        by_kind.setdefault(kind, []).append(art)
    for kind, arts in by_kind.items():
        # floor, not round: small kinds keep every timestamp, so the
        # cross-kind spread stays small deterministically.
        picks = rng.sample(arts, k=int(rate * len(arts)))
        for art in picks:
            art.body = art.body.replace(art.dateline + "\n", "", 1)
            art.dateline = ""
            art.has_timestamp = False


def build_corpus(seed: int = DEFAULT_SEED, n_worlds: int = DEFAULT_WORLDS,
                 ledger=None) -> dict:
    """Full in-memory build. Returns everything the writer needs.

    ``ledger`` injects a prebuilt (possibly overlaid) ledger instead of
    building from seed; audits and rendering proceed unchanged. The
    default path is byte-identical to previous builds.
    """
    rng = random.Random(seed)
    if ledger is None:
        ledger, context, _alloc = worlds.build_ledger(n_worlds, seed)
    else:
        # Injected (possibly overlaid) ledger: World A context artifacts
        # stay; parametric worlds carry none. Audits still apply to the
        # default path unchanged; overlay runs skip freezing.
        _, context = worlds.build_world_a()
    wa_records, _ = worlds.build_world_a()  # deterministic: no rng inside
    world_a_keys = {r.key for r in wa_records}
    # Round-robin (seeded offset) realisation choice for every kind, so
    # template-diversity coverage is deterministic rather than luck.
    rr_pools = {
        kind: list(render_mod.REALISATIONS[kind])
        for kind in (
            "proposal", "preference", "evidence", "decision",
            "production_state", "derived_restatement",
        )
    }
    rr_offsets = {k: rng.randrange(len(v)) for k, v in rr_pools.items()}
    rr_pos = {k: 0 for k in rr_pools}

    def pick_realisation(kind: str) -> str:
        pool = rr_pools[kind]
        choice = pool[(rr_offsets[kind] + rr_pos[kind]) % len(pool)]
        rr_pos[kind] += 1
        return choice

    artifacts, build_meta = render_all(
        ledger, context, rng, world_a_keys, pick_realisation
    )
    strip_datelineless(ledger, artifacts, rng)
    _by_display_tmp = {a.display_id: a for a in artifacts}
    for entry in build_meta:  # sync post-strip timestamp flags
        entry["has_timestamp"] = _by_display_tmp[entry["display_id"]].has_timestamp

    ordered = ids.ingestion_order(artifacts, rng)
    id_map = ids.assign_ids([a.display_id for a in ordered])
    for art in ordered:
        art.internal_id = id_map[art.display_id]  # type: ignore[attr-defined]

    by_display = {a.display_id: a for a in ordered}
    record_by_key = ledger.by_key()
    record_kind_of = {key: rec.kind for key, rec in record_by_key.items()}

    queries_list, expected_list = queries.build_queries(
        ledger, by_display, rng, queries.default_as_of_dates()
    )

    # E-04 oracle: per Q2 query, exactly the ledger-relevant artifacts.
    oracle, oracle_roles = build_oracle(
        ledger, by_display, id_map, queries_list, expected_list
    )

    classifier_rows = []
    for idx, art in enumerate(ordered):
        if not art.record_keys:
            continue  # context artifacts carry no record labels (documented)
        rec = record_by_key[art.record_keys[0]]
        suffix = int(art.display_id.rsplit("-", 1)[1])
        classifier_rows.append(
            {
                "order_index": idx,
                "gen_number": idx + 1,
                "display_suffix": suffix,
                "kind": rec.kind,
                "template": rec.scenario,
                "authority": (
                    "authoritative" if rec.kind in AUTHORITATIVE else "background"
                ),
            }
        )

    record_backed = [a for a in ordered if a.record_keys]
    audit_inputs = {
        "queries": queries_list,
        "records": ledger.records,
        "artifacts": record_backed,
        "record_kind_of": record_kind_of,
        "build_meta": [m for m in build_meta],
        "classifier_rows": classifier_rows,
        "corpus_dir": None,  # filled by write-out path (content sweep)
    }
    return {
        "rng_state": None,
        "ledger": ledger,
        "artifacts": ordered,
        "by_display": by_display,
        "id_map": id_map,
        "queries": queries_list,
        "expected": expected_list,
        "oracle": oracle,
        "oracle_roles": oracle_roles,
        "build_meta": build_meta,
        "context_count": len(ordered) - len(record_backed),
        "audit_inputs": audit_inputs,
    }


def build_oracle(ledger, by_display, id_map, queries_list, expected_list):
    exp_by_q = {e.query_id: e for e in expected_list}
    oracle, oracle_roles = [], []
    for q in queries_list:
        if not q.family.startswith("Q2"):
            continue
        exp = exp_by_q[q.query_id]
        passages, roles = [], []
        for did in exp.supporting:
            art = by_display[did]
            digest = hashlib.sha256(art.body.encode("utf-8")).hexdigest()
            rec = ledger.by_key()[art.record_keys[0]] if art.record_keys else None
            role = rec.kind if rec else "context"
            passages.append(
                {"artifact": id_map[did], "display": did, "body_sha256": digest}
            )
            roles.append(
                {
                    "artifact": id_map[did], "display": did,
                    "body_sha256": digest, "role": role,
                }
            )
        oracle.append({"query_id": q.query_id, "passages": passages})
        oracle_roles.append({"query_id": q.query_id, "passages": roles})
    return oracle, oracle_roles


def write_corpus(built: dict, out: Path) -> None:
    corpus_dir = out / "corpus" / "artifacts"
    eval_dir = out / "eval"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)

    for art in built["artifacts"]:
        (corpus_dir / ids.filename_for(art.internal_id)).write_text(
            art.body + "\n", encoding="utf-8"
        )
    with open(out / "corpus" / "queries.jsonl", "w", encoding="utf-8") as fh:
        for q in built["queries"]:
            fh.write(
                json.dumps(
                    {
                        "query_id": q.query_id, "family": q.family,
                        "topic": q.topic, "text": q.text, "as_of": q.as_of,
                    }
                ) + "\n"
            )
    with open(eval_dir / "ledger.jsonl", "w", encoding="utf-8") as fh:
        for r in built["ledger"].records:
            fh.write(
                json.dumps(
                    {
                        "key": r.key, "kind": r.kind, "topic": r.topic,
                        "content": r.content, "actors": list(r.actors),
                        "date": r.date, "valid_from": r.valid_from,
                        "valid_until": r.valid_until,
                        "supersedes": list(r.supersedes),
                        "supported_by": list(r.supported_by),
                        "derived_from": list(r.derived_from),
                        "display_id": r.display_id, "artifact_kind": r.artifact_kind,
                        "render_style": r.render_style,
                        "second_display_id": r.second_display_id,
                        "scenario": r.scenario,
                    }
                ) + "\n"
            )
    with open(eval_dir / "expected.jsonl", "w", encoding="utf-8") as fh:
        for e in built["expected"]:
            fh.write(
                json.dumps(
                    {
                        "query_id": e.query_id, "family": e.family,
                        "topic": e.topic, "as_of": e.as_of,
                        "answer": e.answer, "supporting": e.supporting,
                    }
                ) + "\n"
            )
    with open(eval_dir / "oracle.jsonl", "w", encoding="utf-8") as fh:
        for entry in built["oracle"]:
            fh.write(json.dumps(entry) + "\n")
    with open(eval_dir / "oracle_roles.jsonl", "w", encoding="utf-8") as fh:
        for entry in built["oracle_roles"]:
            fh.write(json.dumps(entry) + "\n")
    with open(eval_dir / "build_meta.jsonl", "w", encoding="utf-8") as fh:
        for entry in built["build_meta"]:
            fh.write(json.dumps(entry) + "\n")


def freeze(
    seed: int = DEFAULT_SEED,
    n_worlds: int = DEFAULT_WORLDS,
    out: str | Path = "experiments/benchmark/fixtures/v0.1",
    repo_root: str | Path = ".",
) -> Path:
    """Build, audit-gate, and write the frozen corpus. Returns out path."""
    out = Path(out)
    built = build_corpus(seed=seed, n_worlds=n_worlds)
    write_corpus(built, out)

    built["audit_inputs"]["corpus_dir"] = out / "corpus"
    results = audits.run_all(built["audit_inputs"])
    failures = [r for r in results if not r.passed]
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[audit] {status} {r.name}: {r.detail}")
    if failures:
        print("REFUSING TO FREEZE: audits failed.", file=sys.stderr)
        raise SystemExit(1)

    repo_root = Path(repo_root)
    man = manifest_mod.Manifest(
        corpus_version=CORPUS_VERSION,
        seed=seed,
        n_parametric_worlds=n_worlds,
        generator_commit=manifest_mod.generator_commit(repo_root),
        query_set_version=QUERY_SET_VERSION,
    )
    manifest_mod.write_manifest(out, man)
    print(f"frozen corpus at {out} "
          f"({len(built['artifacts'])} artifacts, "
          f"{len(built['queries'])} queries)")
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the v0.1 frozen corpus.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--worlds", type=int, default=DEFAULT_WORLDS)
    parser.add_argument("--out", default="experiments/benchmark/fixtures/v0.1")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    freeze(seed=args.seed, n_worlds=args.worlds, out=args.out,
           repo_root=args.repo_root)


if __name__ == "__main__":
    main()
