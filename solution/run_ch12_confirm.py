"""Confirmatory Chapter 12 driver (Tests 2+4): repeated ladder + BT control.

Test 2: 3 repeats per task per condition (B0/B1/B1P/B2/B3/B4/BO) on
the matched seven-task set with Muse. Unique session ID per model
call (SI-A audit found no carry-over; unique sessions remove the
ambiguity going forward).

Test 4: token-matched remove/restore control (BT) with Muse and
llama3.1:8b: BA (decisive removed) vs BT (decisive removed +
token-matched nondecisive context) vs BR (decisive restored).

Frozen: same contexts/builders, grader, prompt, fixtures as the
canonical and SR-1 runs. New condition BT is diagnostic only; the
canonical v2 run is untouched.

Outdirs:
  sr1c-ch12-confirm-<stamp>-muse   (Test 2 ladder)
  ch12-token-control-<stamp>-muse  (Test 4, Muse)
  ch12-token-control-<stamp>-llama (Test 4, llama)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solution"))

from behavior_eval import contexts as C  # noqa: E402
from behavior_eval import prompts as P  # noqa: E402
from behavior_eval import runner as R  # noqa: E402
from behavior_eval.experiments import (  # noqa: E402
    PLAN,
    _ablation_entry,
    _here_units,
    _render_members,
    ablation_base,
    cleanup_entry,
    membership_for,
    summarize,
)
from behavior_eval.model import (  # noqa: E402
    BEHAVIOR_SCHEMA_VERSION,
    FIXTURE_VERSION,
    GRADER_VERSION,
)
from behavior_eval.prompts import PROMPT_VERSION  # noqa: E402
from behavior_eval.runner import ReaderClient, capped_ask  # noqa: E402
from behavior_eval.tasks import all_tasks  # noqa: E402
from context_frames.reader import SYSTEM_PROMPT as OLLAMA_SYSTEM  # noqa: E402
from context_frames.reader import Reader as OllamaReader  # noqa: E402

MATCHED = ("cite-rule", "credit-rule", "fix-store", "release-blockers",
           "review-arch", "review-prose", "ship-ch10")
LADDER = ("B0", "B1", "B1P", "B2", "B3", "B4", "BO")
BT_TASKS = ("fix-store", "ship-ch10", "release-blockers", "credit-rule",
            "cite-rule", "review-arch", "corpus-cleanup")


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
            text=True).strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------- BT ---

def _words(text: str) -> set[str]:
    import re
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def build_bt(task_id: str, plan: dict, texts: dict, task,
             ba_entry: dict, br_entry: dict) -> dict:
    """Token-matched nondecisive restore over the BA context.

    Target: token cost of the decisive restore (BR minus BA).
    Filler: same-project units, excluding decisive / wrong-memory /
    already-present units, ranked by ascending lexical overlap with
    the task + decisive texts (operationalises "not a substitute").
    """
    target = (C.estimate_tokens(br_entry["context"])
              - C.estimate_tokens(ba_entry["context"]))
    in_ba = _render_members(task, ba_entry, texts, plan)
    excluded = set(task.decisive_units) | set(plan["wrong"]) | set(in_ba)
    # Mechanical validity preference (§15 "valid/current where possible"):
    # units whose own id marks them stale are avoided unless needed to
    # reach the token target. Documented; no hand-picking of content.
    avoided = {uid for uid in texts if "stale" in uid} - excluded
    anchor = _words(task.present_state + " " + task.work_objective)
    for uid in task.decisive_units:
        if uid in texts:
            anchor |= _words(texts[uid]["text"])
    scored = []
    for uid, row in texts.items():
        if row.get("project_id") != "memory-book":
            continue
        if uid in excluded:
            continue
        overlap = len(_words(row["text"]) & anchor)
        # Avoided (stale-marked) units sort after everything else.
        scored.append((uid in avoided, overlap, -row["tokens"], uid))
    scored.sort()
    chosen: list[str] = []
    total = 0
    for _, _, _, uid in scored:
        tok = texts[uid]["tokens"]
        if total >= round(0.9 * target):
            break
        if total + tok <= round(1.1 * target) or not chosen:
            chosen.append(uid)
            total += tok
    if task_id == "corpus-cleanup" and total < round(0.9 * target):
        # Derived world has one valid nondecisive unit; top up from
        # the same project pool is already what `chosen` holds.
        pass
    context = ba_entry["context"]
    if chosen:
        context = context + "\n\n---\n\n" + C.append_units(
            "", chosen, texts, "token-matched nondecisive context")
    entry = {"context": context, "memory_ids": ["token-matched"],
             "note": (f"BA plus nondecisive {chosen} "
                      f"({total}tok vs decisive {target}tok)")}
    entry = C.finalize(entry)
    entry["bt_units"] = chosen
    entry["bt_tokens"] = total
    entry["bt_target"] = target
    entry["bt_ratio"] = round(total / target, 3) if target else None
    return entry


def bt_composition(tasks, plans_texts) -> dict:
    """Dry-run BT composition for review (no model calls)."""
    out = {}
    for task_id in BT_TASKS:
        task, plan, texts = plans_texts[task_id]
        if task_id == "corpus-cleanup":
            ba = cleanup_entry("BA")
            br = cleanup_entry("BR")
        else:
            base_cond, base_entry = ablation_base(task, plan, texts)
            ba = C.finalize(_ablation_entry(task, plan, texts, base_cond,
                                            base_entry, "BA"))
            br = C.finalize(_ablation_entry(task, plan, texts, base_cond,
                                            base_entry, "BR"))
        bt = build_bt(task_id, plan, texts, task, ba, br)
        out[task_id] = {
            "base": base_cond if task_id != "corpus-cleanup" else "B4-custom",
            "decisive": list(task.decisive_units),
            "bt_units": bt["bt_units"],
            "bt_tokens": bt["bt_tokens"],
            "bt_target": bt["bt_target"],
            "bt_ratio": bt["bt_ratio"],
            "ba_tokens": ba["tokens"],
            "br_tokens": br["tokens"],
        }
    return out


# ------------------------------------------------------------ readers ---

def make_muse_client(outdir: Path, run_id: str, model: str,
                     temperature: float, max_tokens: int, effort: str):
    from providers.opencode import (  # noqa: E402
        OpenCodeModel,
        resolve_api_key,
        resolve_model,
        resolve_reasoning_effort,
    )
    model = resolve_model(model)
    effort = resolve_reasoning_effort(effort)
    backend = OpenCodeModel()
    if not resolve_api_key(backend.api_key):
        return None, None
    cache_dir = outdir / "reader-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    salt = f"opencode|{model}|reason-{effort}|temp-{temperature}"
    client = ReaderClient(f"opencode:{model}", cache_dir, live=None,
                          cache_salt=salt)
    totals: dict = {}
    records: list[dict] = []
    calls_path = outdir / "muse_calls.jsonl"
    if calls_path.exists():
        for line in calls_path.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
    seen_records = {(r.get("task"), r.get("condition"), r.get("repeat"))
                    for r in records}

    def generate_with_retry(full: str, session: str):
        import random as _random
        last = None
        for attempt in range(4):
            result = backend.generate(
                full, model=model, temperature=temperature,
                max_tokens=max_tokens, reasoning_effort=effort,
                session_id=session)
            if not result.get("error"):
                return result
            last = result
            etype = result.get("error_type")
            status = result.get("status_code")
            retryable = (etype in ("timeout", "network", "rate_limited")
                         or (etype == "http_error" and status in
                             (408, 425, 429, 500, 502, 503, 504)))
            if not retryable or attempt == 3:
                return result
            delay = min(240, 15 * (2 ** attempt)) + _random.uniform(0, 5)
            print(f"transient {etype}/{status}; sleeping {delay:.0f}s "
                  f"(attempt {attempt + 1}/4)")
            time.sleep(delay)
        return last

    def ask(task, entry, prompt: str, condition: str, repeat: int) -> str:
        session = f"memory-{run_id}-{task.task_id}-{condition}-r{repeat}"
        key = client._cache_key(prompt, repeat)
        path = cache_dir / f"{key}.json"
        hit = path.exists()
        if hit:
            client.hits += 1
            response = json.loads(path.read_text())["response"]
            usage: dict = json.loads(path.read_text()).get("usage", {})
            actual_session = "(cache replay)"
        else:
            client.calls += 1
            result = generate_with_retry(
                f"{P.SYSTEM_PROMPT}\n\n{prompt}", session)
            if result.get("error"):
                raise RuntimeError(
                    f"muse failed [{result.get('error_type')}] "
                    f"on {task.task_id}/{condition}/r{repeat} "
                    f"after retries: {result.get('error')}")
            response = result["response"]
            usage = result.get("usage") or {}
            request = dict(result.get("request") or {})
            path.write_text(json.dumps(
                {"task": task.task_id, "condition": condition,
                 "repeat": repeat, "context_hash": entry["context_hash"],
                 "prompt": prompt, "response": response,
                 "usage": usage, "request": request}))
            actual_session = session
        for k in ("input_tokens", "cached_input_tokens", "output_tokens",
                  "reasoning_tokens", "total_tokens"):
            totals[k] = totals.get(k, 0) + int(usage.get(k, 0) or 0)
        totals["calls"] = totals.get("calls", 0) + (0 if hit else 1)
        if (task.task_id, condition, repeat) not in seen_records:
            seen_records.add((task.task_id, condition, repeat))
            records.append({"task": task.task_id, "condition": condition,
                            "repeat": repeat,
                            "context_hash": entry["context_hash"],
                            "session_requested": session,
                            "session_actual": actual_session,
                            "cache_hit": hit,
                            "usage": usage, "response": response})
        return response

    client.live = ask  # ask via closure; live unused by run loop below
    identity = {"reader": client.name, "reader_provider": "opencode-zen-go",
                "reader_model": model, "reasoning_effort": effort,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
                "session_scheme": "unique-per-call",
                "muse_usage_totals": totals}
    return (client, ask, totals, records, identity)


def make_ollama_client(outdir: Path, model: str):
    reader = OllamaReader(model=model)
    if not reader.available():
        return None
    cache_dir = outdir / "reader-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    client = ReaderClient(model, cache_dir, live=None)

    def ask(task, entry, prompt: str, condition: str, repeat: int) -> str:
        key = client._cache_key(prompt, repeat)
        path = cache_dir / f"{key}.json"
        if path.exists():
            client.hits += 1
            return json.loads(path.read_text())["response"]
        client.calls += 1
        last: Exception | None = None
        for attempt in range(4):
            try:
                response = capped_ask(model, reader.host, OLLAMA_SYSTEM,
                                      prompt)
                break
            except (TimeoutError, urllib.error.URLError,
                    ConnectionError, OSError) as exc:
                last = exc
                time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f"ollama reader unreachable: {last}")
        path.write_text(json.dumps(
            {"task": task.task_id, "condition": condition,
             "repeat": repeat, "context_hash": entry["context_hash"],
             "prompt": prompt, "response": response}))
        return response

    identity = {"reader": client.name, "reader_provider": "ollama-local",
                "reader_model": model, "temperature": 0.0,
                "session_scheme": "n/a (local)"}
    return (client, ask, identity)


# ---------------------------------------------------------------- run ---

def build_entry(task_id: str, task, plan: dict, texts: dict,
                condition: str, bt_cache: dict) -> tuple[dict, str | None]:
    """Standard entries via frozen builders; BT via token-match."""
    if task_id == "corpus-cleanup":
        if condition == "BT":
            ba = cleanup_entry("BA")
            br = cleanup_entry("BR")
            return build_bt(task_id, plan, texts, task, ba, br), None
        return cleanup_entry(condition), None
    if condition in ("BA", "BR"):
        base_cond, base_entry = ablation_base(task, plan, texts)
        entry = C.finalize(_ablation_entry(task, plan, texts, base_cond,
                                           base_entry, condition))
        return entry, base_cond
    if condition == "BT":
        base_cond, base_entry = ablation_base(task, plan, texts)
        ba = C.finalize(_ablation_entry(task, plan, texts, base_cond,
                                        base_entry, "BA"))
        br = C.finalize(_ablation_entry(task, plan, texts, base_cond,
                                        base_entry, "BR"))
        return build_bt(task_id, plan, texts, task, ba, br), base_cond
    entry = C.finalize(C.build_condition(
        plan["ch10"], condition, texts, task.decisive_units,
        plan["wrong"], ch10_task=plan["ch10"]))
    return entry, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--reader", default="muse",
                        choices=("muse", "llama", "ministral"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--tasks", default=None)
    parser.add_argument("--conditions", default=None)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--reasoning-effort", default=None)
    parser.add_argument("--tag", default="confirm",
                        help="run-name tag (confirm | token-control)")
    parser.add_argument("--show-bt", action="store_true",
                        help="print BT composition; no model calls")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tasks = all_tasks()
    if args.tasks:
        want = set(args.tasks.split(","))
        tasks = [t for t in tasks if t.task_id in want]
    conditions = (args.conditions.split(",") if args.conditions else None)
    plans_texts = {}
    texts = C.corpus_texts()
    for t in tasks:
        plans_texts[t.task_id] = (t, PLAN[t.task_id], texts)

    if args.show_bt:
        comp = bt_composition(
            [t.task_id for t in tasks if t.task_id in BT_TASKS],
            plans_texts)
        print(json.dumps(comp, indent=1))
        return 0

    ncalls = (len(tasks) * len(conditions or ()) * args.repeats
              if conditions else 0)
    if args.dry_run:
        print(f"dry-run: reader={args.reader} tasks={[t.task_id for t in tasks]} "
              f"conditions={conditions} repeats={args.repeats} "
              f"live_slots={ncalls}")
        return 0
    if not conditions:
        print("no conditions selected; aborting")
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reader_tag = {"muse": "muse", "llama": "llama",
                  "ministral": "ministral"}[args.reader]
    outdir = Path(args.outdir) if args.outdir else (
        ROOT / "experiments" / "benchmark" / "runs"
        / f"{args.tag}-{stamp}-{reader_tag}")
    outdir.mkdir(parents=True, exist_ok=True)
    run_id = outdir.name

    if args.reader == "muse":
        made = make_muse_client(outdir, run_id, args.model,
                                args.temperature, args.max_tokens,
                                args.reasoning_effort)
        if made[0] is None:
            print("no Muse credentials (no live calls made)")
            return 2
        client, ask, totals, records, identity = made
    else:
        from providers.opencode import resolve_model as _rm
        model = (args.model or {"llama": "llama3.1:8b",
                                "ministral": "ministral-3:8b"}[args.reader])
        made = make_ollama_client(outdir, model)
        if made is None:
            print(f"ollama reader {model} unreachable; aborting")
            return 2
        client, ask, identity = made
        totals, records = {}, []

    suite: dict = {"conditions": {}, "ablation_base": {}}
    bt_comp: dict = {}
    manifest = {
        "suite": ("SR-1c confirmatory ladder" if args.tag == "confirm"
                  else "SR-1d token-matched control"),
        "run_id": run_id,
        "created_at": stamp,
        "behavior_schema_version": BEHAVIOR_SCHEMA_VERSION,
        "grader_version": GRADER_VERSION,
        "fixture_version": FIXTURE_VERSION,
        "prompt_version": PROMPT_VERSION,
        "benchmark_contract": ("benchmark-v0.1 plus diagnostic "
                               "behavioural dimensions (no contract change)"),
        "conditions_run": conditions,
        "repeats": args.repeats,
        "tasks": [t.task_id for t in tasks],
        "ch10_source_run": "ch10-20260920T163314Z-context-frames",
        "ch11_source_run": "ch11-20260920T171039Z-derived-loops",
        "ch14_source_run": "ch14-20260920T174259Z-context-assembly",
        "token_estimator": "chars//4 (estimated tokens)",
        "code_commit": _commit(),
        "reader_cache_calls": client.calls,
        "reader_cache_hits": client.hits,
        "cost": "not computed",
        **identity,
    }
    if args.reader == "muse":
        manifest["muse_usage_totals"] = totals
    # Resume: rows frozen by earlier invocations are reused when the
    # rebuilt entry hashes identically (same discipline as run_suite).
    resumed: dict = {}
    prior = outdir / "conditions.json"
    if prior.exists():
        for cond, rows in json.loads(prior.read_text()).items():
            for r in rows:
                o = r["outcome"]
                resumed[(o["task_id"], cond, o.get("repeat_index", 0))] = r
        print(f"resuming: {len(resumed)} stored rows available")
    for rep in range(args.repeats):
        # B0 first per repeat (seeds paired attribution like run_suite).
        b0_types: dict[str, list] = {}
        b0_entries: dict[str, dict] = {}
        for task in tasks:
            tid = task.task_id
            if conditions and "B0" not in conditions:
                continue
            plan = PLAN[tid]
            entry = (cleanup_entry("B0") if tid == "corpus-cleanup"
                     else C.finalize(C.build_condition(
                         plan["ch10"], "B0", texts, task.decisive_units,
                         (), ch10_task=plan["ch10"])))
            b0_entries[tid] = entry
            stored = _reuse_slot(suite, resumed, tid, "B0", entry, rep)
            if stored is not None:
                b0_types[tid] = _actions_of(stored)
                continue
            outcome = R.run_condition(task, "B0", entry, ask, client.name,
                                      repeat=rep,
                                      membership=membership_for(
                                          plan["ch10"], texts),
                                      no_memory_types=None)
            _store(suite, outcome, entry)
            b0_types[tid] = [a.get("action_type")
                             for a in outcome.structured_actions]
        for task in tasks:
            tid = task.task_id
            plan = PLAN[tid]
            membership = membership_for(plan["ch10"], texts)
            for condition in [c for c in (conditions or []) if c != "B0"]:
                entry, base_cond = build_entry(
                    tid, task, plan, texts, condition, bt_comp)
                if condition == "BT" and tid not in bt_comp:
                    bt_comp[tid] = {
                        "bt_units": entry.get("bt_units"),
                        "bt_tokens": entry.get("bt_tokens"),
                        "bt_target": entry.get("bt_target"),
                        "bt_ratio": entry.get("bt_ratio"),
                        "ba_tokens": None, "br_tokens": None,
                        "base": base_cond}
                if base_cond is not None:
                    suite["ablation_base"].setdefault(tid, base_cond)
                stored = _reuse_slot(suite, resumed, tid, condition,
                                     entry, rep)
                if stored is not None:
                    continue
                here = _here_units(task, entry, texts, plan)
                outcome = R.run_condition(
                    task, condition, entry, ask, client.name, repeat=rep,
                    membership=dict(membership, here=here),
                    no_memory_types=b0_types.get(tid))
                _store(suite, outcome, entry)
        print(f"rep {rep} done: calls={client.calls} hits={client.hits}")
        _freeze(suite, outdir, bt_comp, records, client, manifest,
                write_calls=args.reader == "muse")

    summary = _freeze(suite, outdir, bt_comp, records, client, manifest,
                      write_calls=args.reader == "muse")
    print(f"wrote {outdir} calls={client.calls} hits={client.hits}")
    for cond, stats in summary["mean_by_condition"].items():
        print(f"  {cond}: success={stats['task_success']} "
              f"harmful={stats['harmful']} n={stats['n']}")
    return 0


def _store(suite: dict, outcome, entry: dict) -> None:
    slot = suite["conditions"].setdefault(outcome.memory_condition, [])
    slot.append({"outcome": outcome.to_dict(),
                 "context": entry.get("context", ""),
                 "note": entry.get("note", "")})


def _actions_of(stored_outcome: dict) -> list:
    return [a.get("action_type")
            for a in stored_outcome.get("structured_actions", [])]


def _reuse_slot(suite: dict, resumed: dict, task_id: str, condition: str,
                entry: dict, rep: int) -> dict | None:
    """Reuse a frozen row when the rebuilt context hashes identically."""
    stored = resumed.get((task_id, condition, rep))
    if (stored is not None and stored["outcome"].get("context_hash")
            == entry["context_hash"]):
        slot = suite["conditions"].setdefault(condition, [])
        slot.append({"outcome": stored["outcome"],
                     "context": stored.get("context", ""),
                     "note": stored.get("note", "")})
        return stored["outcome"]
    return None


def _freeze(suite: dict, outdir: Path, bt_comp: dict, records: list[dict],
            client, manifest: dict, write_calls: bool = True) -> dict:
    summary = summarize(suite)
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))
    serial = {}
    for cond, rows in suite["conditions"].items():
        serial[cond] = [{"outcome": dict(r["outcome"]), "note": r["note"]}
                        for r in rows]
    (outdir / "conditions.json").write_text(json.dumps(serial, indent=2))
    contexts_out = {}
    for cond, rows in suite["conditions"].items():
        for r in rows:
            o = r["outcome"]
            contexts_out[f"{o['task_id']}|{cond}|{o['repeat_index']}"] = {
                "context": r.get("context", ""),
                "context_hash": o["context_hash"],
                "tokens": o["context_tokens"], "note": r["note"]}
    (outdir / "contexts.json").write_text(json.dumps(contexts_out, indent=2))
    (outdir / "ablation_base.json").write_text(
        json.dumps(suite["ablation_base"], indent=2))
    if bt_comp:
        (outdir / "bt-composition.json").write_text(
            json.dumps(bt_comp, indent=2))
    if write_calls:
        (outdir / "muse_calls.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    manifest["reader_cache_calls"] = client.calls
    manifest["reader_cache_hits"] = client.hits
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
