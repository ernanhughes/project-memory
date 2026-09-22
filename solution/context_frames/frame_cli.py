"""Frame-safety demo: one wrong-frame case end to end.

Shows task -> signals -> candidate frames -> establishment class ->
policy action -> hard-frame / safe-policy / query-only contexts ->
reader actions -> behavior scores -> harm. The gate and all contexts
are deterministic and need no model; the reader section runs only
when Ollama is reachable.

    python -m context_frames.frame_cli demo [--scenario B-prose-weak-dev]
"""

from __future__ import annotations

import sys

from . import fixtures as fx
from . import frame_fixtures as ffx
from . import frame_safety as fs

BAR = "=" * 72


def demo(scenario_id: str = "B-prose-weak-dev") -> int:
    sys.path.insert(0, "solution")
    import run_ch13 as R
    from behavior_eval.tasks import task_by_id

    scenario = ffx.scenario_by_id(scenario_id)
    task = task_by_id(scenario.behavior_task)
    project = fx.PF_MEMORY_BOOK()
    print(BAR)
    print(f"TASK {task.task_id}: {task.work_objective}")
    print(BAR)
    print("\nSIGNALS:")
    for s in scenario.signals:
        print(f"  [{s.signal_id}] ({s.kind}) {s.text}")
    decision, ftrace = R.run_gate(scenario, project)
    print("\nCANDIDATE FRAMES:")
    for cand in ftrace.to_dict()["candidate_frames"]:
        print(f"  {cand['project']}/{cand['work_type']} "
              f"via {cand['signals']}")
    print(f"\nESTABLISHMENT: {decision.establishment}")
    print(f"REASONS: {list(decision.reasons)}")
    print(f"POLICY ACTION: {decision.action}")

    texts = R.C.corpus_texts()
    units_list = R.corpus()
    units = {u.unit_id: u for u in units_list}
    from context_frames.retrieval import HybridRetriever, OllamaEmbedder
    retriever = HybridRetriever(units_list, OllamaEmbedder())
    retriever.warm()
    chtask = fx.task_by_id(scenario.ch10_task)
    frame = fx.PROJECT_FRAMES[chtask.work_frame.project_id]()
    bundles = R.build_corpus_bundles(
        scenario, frame, chtask.work_frame, retriever, units, texts)
    true_frame = R.true_frame_for(scenario, project)
    if true_frame is not None:
        from context_frames.policy import build_context
        b2, _ = build_context(
            "C5", chtask.query, frame, true_frame, retriever, units,
            R.BUDGET, trace_id=f"{scenario.scenario_id}-F2")
        bundles["F2"] = (R.render_live_bundle(b2, texts), None,
                         b2.digest())
    print("\nCONTEXTS (rendered chars):")
    for cond in ("F2", "F3", "F4", "F1"):
        if cond in bundles:
            print(f"  {cond}: {len(bundles[cond][0])} chars")

    from context_frames.reader import Reader
    reader = Reader()
    if not reader.available():
        print("\nNo live reader: gate + contexts above need no model.")
        return 0
    from behavior_eval import runner as Rr
    from behavior_eval.runner import ReaderClient
    from pathlib import Path
    import tempfile
    client = ReaderClient(reader.model, Path(tempfile.mkdtemp()),
                          live=lambda prompt: reader.ask(prompt))
    membership = R.membership_for_scenario(scenario, texts)
    print("\nREADER ACTIONS (same reader, temperature 0):")
    for cond in ("F2", "F3", "F4", "F1"):
        if cond not in bundles:
            continue
        entry = R.bundle_entry(bundles[cond][0], [f"live-{cond}"],
                               f"demo {cond}")
        outcome = Rr.run_condition(task, cond, entry, client.ask,
                                   client.name, membership=membership,
                                   no_memory_types=None).to_dict()
        print(f"  {cond}: score={outcome['task_score']} "
              f"actions={outcome['structured_actions']} "
              f"fail={outcome['failure_classes']}")
    return 0


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="context_frames.frame_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("demo")
    p.add_argument("--scenario", default="B-prose-weak-dev")
    p.set_defaults(func=lambda args: demo(args.scenario))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
