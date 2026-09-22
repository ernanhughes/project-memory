"""The Chapter 5 experiment suite, E5-A through E5-H.

Every experiment here runs at the *retrieval* level on the deterministic
ledger fixture: no reader, no model server, no network. That is a
limitation and it is stated as one — these runs establish whether
propagation finds the right memories at a bounded cost, not whether a
reader then answers correctly. Answer-level comparison against Chapter 3
and Chapter 4 requires those chapters' frozen runs and is recorded as
pending, not assumed.

What the retrieval-level suite can settle honestly:

* whether propagation reaches evidence that direct seeding misses (E5-A);
* whether cue conditioning separates branches of one entity (E5-B);
* whether multi-hop cases resolve at all (E5-C);
* what propagation costs in precision (E5-D);
* whether hubs capture the selection (E5-E);
* what one false derived edge does (E5-F);
* whether adaptive weights help later cues (E5-G);
* whether frequency-driven reinforcement creates a feedback loop (E5-H).
"""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from .config import AssociativeConfig, LearningConfig
from .evaluation.adapter import metric_means, score_case
from .fixtures import build_cases, build_graph, oracle_seed_nodes
from .health.checks import check_graph
from .pathways.learning import BAD, GOOD, OutcomeRecord, PathwayLearner, path_edge_ids
from .pathways.weights import AssociationState
from .pipeline import AssociativeMemory
from .propagation.base import ActivatedMemory, RetrievalResult

SUITE_VERSION = "E5-v0.1"


# -- helpers ------------------------------------------------------------


def _seed_only_result(memory: AssociativeMemory, cue: str) -> RetrievalResult:
    """No propagation at all: whatever seeding found, ranked by seed score.

    This is the honest floor. If it matches spreading activation, the
    chapter's mechanism has bought nothing and must say so.
    """
    from .activation.state import ActivationState

    started = time.perf_counter()
    seeds = memory.seeder.seed(cue, memory.graph)
    state = ActivationState()
    for seed in seeds:
        state.seed(seed.node_id, seed.score)
    state.terminated_because = "no-propagation"
    admitted = []
    for seed in seeds[: memory.config.selection.max_memories]:
        node = memory.graph.nodes[seed.node_id]
        admitted.append(
            ActivatedMemory(
                node_id=seed.node_id,
                label=node.label,
                kind=node.kind,
                activation=seed.score,
                hops=0,
                path=[seed.node_id],
                source_ids=list(node.source_ids),
                score=seed.score,
                seeded=True,
            )
        )
    return RetrievalResult(
        cue=cue,
        strategy="seed-only",
        seeds=seeds,
        admitted=admitted,
        explored=list(admitted),
        state=state,
        nodes_expanded=len(seeds),
        edges_traversed=0,
        steps_run=0,
        terminated_because="no-propagation",
        latency_ms=(time.perf_counter() - started) * 1000.0,
    )


def run_condition(
    condition: str,
    graph,
    config: AssociativeConfig,
    strategy: str | None,
    cases,
    oracle_nodes=None,
    association_state=None,
) -> tuple[list, dict]:
    """Run every cue under one configuration and score it."""
    memory = AssociativeMemory(
        graph=graph,
        config=config,
        # The seed-only floor has no retriever of its own; it borrows a
        # configured one and never calls it.
        strategy="spreading" if strategy == "seed-only" else strategy,
        oracle_nodes=oracle_nodes,
        association_state=association_state,
    )
    started = time.perf_counter()
    results = []
    scored = []
    for case in cases:
        if strategy == "seed-only":
            result = _seed_only_result(memory, case.cue)
        else:
            result = memory.retrieve(case.cue)
        results.append((case, result))
        scored.append(score_case(case, result, graph, condition))
    summary = {
        "condition": condition,
        "cases": len(cases),
        "wall_seconds": round(time.perf_counter() - started, 4),
        "means": metric_means(scored),
        "total_nodes_expanded": sum(c.nodes_expanded for c in scored),
        "total_edges_traversed": sum(c.edges_traversed for c in scored),
        "mean_context_tokens": (
            sum(c.context_tokens_estimate for c in scored) / len(scored)
            if scored
            else 0
        ),
        "mean_latency_ms": (
            sum(c.latency_ms for c in scored) / len(scored) if scored else 0.0
        ),
        "manifest": memory.manifest(),
    }
    return scored, summary, results


def _subset(cases, hop_class: str):
    return [case for case in cases if case.hop_class == hop_class]


# -- E5-A: direct versus associative retrieval ---------------------------


def e5a_direct_vs_associative(graph, cases, config) -> dict:
    """Does propagation recover evidence that seeding alone misses?

    Conditions include the seed-only floor, each propagation strategy, a
    degree-preserving edge-shuffle control, and oracle seeding. The
    shuffle control is the one that matters most: if a rewired graph
    scores the same, the associations carried no information.
    """
    conditions: dict[str, dict] = {}
    for strategy in (
        "seed-only",
        "direct",
        "pagerank",
        "spreading",
        "conditioned",
        "conditioned-pagerank",
    ):
        _, summary, _ = run_condition(
            strategy, graph, config, strategy, cases
        )
        conditions[strategy] = summary

    shuffled = graph.with_shuffled_edges(seed=17)
    _, summary, _ = run_condition(
        "spreading-shuffled-control", shuffled, config, "spreading", cases
    )
    conditions["spreading-shuffled-control"] = summary

    oracle_config = replace(
        config, seeding=replace(config.seeding, method="oracle")
    )
    _, summary, _ = run_condition(
        "oracle-seed-spreading",
        graph,
        oracle_config,
        "spreading",
        cases,
        oracle_nodes=oracle_seed_nodes(),
    )
    conditions["oracle-seed-spreading"] = summary

    for method in ("embedding", "hybrid"):
        seed_config = replace(
            config, seeding=replace(config.seeding, method=method)
        )
        _, summary, _ = run_condition(
            f"seedmethod-{method}", graph, seed_config, "spreading", cases
        )
        conditions[f"seedmethod-{method}"] = summary

    return {
        "experiment": "E5-A",
        "seeding_note": (
            "The default seeder is lexical. seedmethod-embedding and "
            "seedmethod-hybrid use the deterministic hashing embedder, "
            "which preserves no semantics; they are a lower bound on "
            "dense seeding, not a measurement of it."
        ),
        "question": "Does graph propagation recover useful memories that "
        "direct similarity misses?",
        "conditions": conditions,
    }


# -- E5-B: context-conditioned branching ---------------------------------

BRANCH_GROUPS = {
    "a.silva": (
        "c-cond-silva-eventstore",
        "c-cond-silva-corpus",
        "c-cond-silva-orphans",
    ),
    "j.lindqvist": (
        "c-cond-lindqvist-backend",
        "c-cond-lindqvist-procedure",
    ),
}


def _overlap(first: list[str], second: list[str]) -> float:
    a, b = set(first), set(second)
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def e5b_conditioned_branching(graph, cases, config) -> dict:
    """Do two cues naming the same actor activate different neighbourhoods?

    The measurement is branch separation: the overlap between the admitted
    source sets of two cues about the same entity. Low overlap with high
    per-cue recall means the cue, not the entity, chose the region.
    """
    by_id = {case.case_id: case for case in cases}
    report: dict[str, dict] = {}
    for strategy in ("direct", "spreading", "conditioned", "conditioned-pagerank"):
        memory = AssociativeMemory(graph=graph, config=config, strategy=strategy)
        admitted: dict[str, list[str]] = {}
        recall: dict[str, float] = {}
        for group in BRANCH_GROUPS.values():
            for case_id in group:
                case = by_id[case_id]
                result = memory.retrieve(case.cue)
                admitted[case_id] = result.admitted_sources()
                expected = set(case.expected_sources)
                got = set(admitted[case_id])
                recall[case_id] = (
                    len(expected & got) / len(expected) if expected else 1.0
                )
        overlaps: dict[str, float] = {}
        for actor, group in BRANCH_GROUPS.items():
            pairs = [
                (group[i], group[j])
                for i in range(len(group))
                for j in range(i + 1, len(group))
            ]
            for first, second in pairs:
                overlaps[f"{actor}:{first}|{second}"] = _overlap(
                    admitted[first], admitted[second]
                )
        report[strategy] = {
            "mean_branch_overlap": (
                sum(overlaps.values()) / len(overlaps) if overlaps else None
            ),
            "mean_branch_recall": (
                sum(recall.values()) / len(recall) if recall else None
            ),
            "overlaps": {k: round(v, 4) for k, v in sorted(overlaps.items())},
            "recall": {k: round(v, 4) for k, v in sorted(recall.items())},
            "admitted": {k: v for k, v in sorted(admitted.items())},
        }
    return {
        "experiment": "E5-B",
        "question": "Does the active cue, rather than entity identity, "
        "determine which neighbourhood activates?",
        "strategies": report,
    }


# -- E5-C: multi-hop retrieval --------------------------------------------


def e5c_multi_hop(graph, cases, config) -> dict:
    """Do cases whose evidence is two or more valid edges away resolve?"""
    indirect = _subset(cases, "indirect")
    direct = _subset(cases, "direct")
    report: dict[str, dict] = {}
    for strategy in ("seed-only", "direct", "pagerank", "spreading", "conditioned"):
        _, indirect_summary, _ = run_condition(
            strategy, graph, config, strategy, indirect
        )
        _, direct_summary, _ = run_condition(
            strategy, graph, config, strategy, direct
        )
        report[strategy] = {
            "indirect": indirect_summary["means"],
            "direct_control": direct_summary["means"],
        }
    return {
        "experiment": "E5-C",
        "question": "Can associative retrieval solve cases where the "
        "evidence is two or more edges away, without harming the direct "
        "cases?",
        "indirect_cases": [case.case_id for case in indirect],
        "direct_cases": [case.case_id for case in direct],
        "strategies": report,
    }


# -- E5-D: precision cost and per-constraint ablation ---------------------


def e5d_precision_cost(graph, cases, config) -> dict:
    """What does each constraint contribute, and what does it cost?"""
    ablations = {
        "full": config,
        "no-inhibition": replace(
            config, propagation=replace(config.propagation, inhibition=False)
        ),
        "no-fan-division": replace(
            config, propagation=replace(config.propagation, fan_division=False)
        ),
        "no-threshold": replace(
            config,
            propagation=replace(config.propagation, activation_threshold=0.0),
        ),
        "no-decay": replace(
            config, propagation=replace(config.propagation, retention=0.0,
                                         spread_factor=1.0)
        ),
        "hops-1": replace(
            config, propagation=replace(config.propagation, max_hops=1)
        ),
        "hops-5": replace(
            config, propagation=replace(config.propagation, max_hops=5)
        ),
        "unconstrained": replace(
            config,
            propagation=replace(
                config.propagation,
                inhibition=False,
                fan_division=False,
                activation_threshold=0.0,
                retention=0.0,
                spread_factor=1.0,
                max_hops=5,
                max_nodes_expanded=10_000,
            ),
        ),
    }
    report: dict[str, dict] = {}
    for name, variant in ablations.items():
        _, summary, _ = run_condition(name, graph, variant, "spreading", cases)
        report[name] = {
            "means": summary["means"],
            "total_nodes_expanded": summary["total_nodes_expanded"],
            "total_edges_traversed": summary["total_edges_traversed"],
            "mean_context_tokens": summary["mean_context_tokens"],
            "mean_latency_ms": summary["mean_latency_ms"],
        }
    return {
        "experiment": "E5-D",
        "question": "How much irrelevant material does propagation "
        "introduce, and which constraint prevents it?",
        "ablations": report,
    }


# -- E5-E: hub resistance ---------------------------------------------------


def e5e_hub_resistance(graph, cases, config) -> dict:
    """Does the mechanism avoid high-degree distractors?"""
    adversarial = _subset(cases, "adversarial")
    report: dict[str, dict] = {}
    variants = {
        "full": config,
        "no-fan-division": replace(
            config, propagation=replace(config.propagation, fan_division=False)
        ),
        "no-inhibition": replace(
            config, propagation=replace(config.propagation, inhibition=False)
        ),
    }
    for name, variant in variants.items():
        for strategy in ("spreading", "pagerank", "conditioned"):
            _, summary, _ = run_condition(
                f"{name}:{strategy}", graph, variant, strategy, adversarial
            )
            report[f"{name}:{strategy}"] = summary["means"]
    return {
        "experiment": "E5-E",
        "question": "Does propagation avoid high-degree distractors?",
        "adversarial_cases": [case.case_id for case in adversarial],
        "graph_hubs": graph.hubs(top=5),
        "variants": report,
    }


# -- E5-F: false-edge resilience ---------------------------------------------


def e5f_false_edge(graph, cases, config) -> dict:
    """What happens when Chapter 4 derived one relation incorrectly?

    The injected edge is the most damaging plausible one: it wires the
    event-store decision hub directly to the same-symptom incident whose
    real cause is unrelated, exactly the mistake an extractor makes when
    two passages share vocabulary.
    """
    corrupted = graph.with_injected_error(
        edge_id="false-001",
        source="claim:evt-205",
        target="source:incident-106",
        relation="SUPPORTED_BY",
        association=0.9,
    )
    report: dict[str, dict] = {}
    for label, target_graph in (("clean", graph), ("false-edge", corrupted)):
        for strategy in ("spreading", "pagerank", "conditioned"):
            _, summary, _ = run_condition(
                f"{label}:{strategy}", target_graph, config, strategy, cases
            )
            report[f"{label}:{strategy}"] = summary["means"]
    # Per-case effect on the cue the false edge was built to derail.
    affected = [case for case in cases if case.case_id == "c-adv-tempting"]
    per_case: dict[str, dict] = {}
    for label, target_graph in (("clean", graph), ("false-edge", corrupted)):
        scored, _summary, runs = run_condition(
            label, target_graph, config, "spreading", affected
        )
        _case, result = runs[0]
        per_case[label] = {
            "admitted_sources": result.admitted_sources(),
            "explored_sources": result.explored_sources(),
            "means": metric_means(scored),
        }

    health = check_graph(corrupted)
    return {
        "experiment": "E5-F",
        "affected_case": per_case,
        "question": "What does one incorrect derived relation do to "
        "propagation, and is it visible?",
        "injected_edge": {
            "edge_id": "false-001",
            "from": "claim:evt-205",
            "to": "source:incident-106",
            "relation": "SUPPORTED_BY",
            "evidence_confidence": 0.0,
        },
        "conditions": report,
        "health_flags_it": health.injected_errors > 0
        and any(
            issue.check == "unprovenanced-edges" for issue in health.issues
        ),
    }


# -- E5-G: static versus adaptive pathways -----------------------------------

# Cue sequences that share a region: a route found for the first question
# might help the later ones. Outcomes are supplied by the ledger, not by
# the system's own opinion of its retrieval.
ADAPTIVE_SEQUENCE = (
    "c-hop-why",
    "c-hop-backup",
    "c-hop-fixtures",
)


def e5g_static_vs_adaptive(graph, cases, config) -> dict:
    """Does outcome-gated reinforcement improve later related cues?"""
    by_id = {case.case_id: case for case in cases}
    learning = LearningConfig(enabled=True)
    learn_config = replace(config, learning=learning)
    working = type(graph).from_dict(graph.to_dict())
    state = AssociationState.from_graph(working, learning.policy_version)
    memory = AssociativeMemory(
        graph=working, config=learn_config, strategy="spreading",
        association_state=state,
    )
    learner = PathwayLearner(learning, state, working)

    trace: list[dict] = []
    # Training pass: run each cue, judge it against the ledger, update.
    #
    # The judgement is deliberately asymmetric. A route that *reached*
    # required evidence is reinforced even if the selection budget cut it,
    # because that is the case reinforcement is for: promoting a correct
    # pathway the ranking under-valued. A route that was admitted and
    # turned out irrelevant is weakened. Nothing is judged by how often it
    # was travelled.
    for case_id in ADAPTIVE_SEQUENCE:
        case = by_id[case_id]
        result = memory.retrieve(case.cue)
        expected = set(case.expected_sources)
        admitted_ids = {item.node_id for item in result.admitted}
        judged = 0
        for item in result.explored:
            edges = path_edge_ids(result.state, item)
            if not edges:
                continue  # seeded directly; there is no pathway to credit
            useful = bool(expected & set(item.source_ids))
            if not useful and item.node_id not in admitted_ids:
                continue  # never entered context; no outcome to attribute
            learner.record_outcome(
                OutcomeRecord(
                    cue=case.cue,
                    outcome=GOOD if useful else BAD,
                    path_edges=edges,
                    note=f"ledger-judged for {case_id}",
                )
            )
            judged += 1
        state.apply_to(working)
        trace.append(
            {
                "case_id": case_id,
                "routes_judged": judged,
                "updates_so_far": len(state.updates),
                "admitted": result.admitted_sources(),
                "reached_but_not_admitted": sorted(
                    set(result.explored_sources()) - set(result.admitted_sources())
                ),
            }
        )

    _, before, _ = run_condition("static", graph, config, "spreading", cases)
    _, after, _ = run_condition(
        "adapted", working, learn_config, "spreading", cases,
        association_state=state,
    )
    refusal_counts: dict[str, int] = {}
    for _edge_id, why in learner.refusals:
        refusal_counts[why] = refusal_counts.get(why, 0) + 1
    return {
        "experiment": "E5-G",
        "question": "Does experience using memory improve later traversal?",
        "sequence": list(ADAPTIVE_SEQUENCE),
        "training_trace": trace,
        "updates_recorded": len(state.updates),
        "strengthened": sum(
            1 for u in state.updates if u.new_weight > u.prior_weight
        ),
        "weakened": sum(
            1 for u in state.updates if u.new_weight < u.prior_weight
        ),
        "refusals": refusal_counts,
        "static": before["means"],
        "adapted": after["means"],
        "replay_reproduces_weights": state.weights_at(len(state.updates))
        == state.current_weights(),
        "rollback_reproduces_base": state.weights_at(0) == state.base_weights,
    }


# -- E5-H: reinforcement pathology -------------------------------------------


def e5h_reinforcement_pathology(graph, cases, config) -> dict:
    """Can repeated retrieval of a wrong association make it self-confirming?

    The corrupted graph carries a false SUPPORTED_BY edge. Two update
    policies are run over the same repeated cue: frequency-driven
    reinforcement, which the book refuses, and outcome-gated
    reinforcement with evidence gates, which it proposes. The comparison
    is the point; neither is a recommendation on its own.
    """
    by_id = {case.case_id: case for case in cases}
    case = by_id["c-adv-tempting"]
    rounds = 8
    outcome_report: dict[str, dict] = {}

    for policy in ("frequency-only", "outcome-gated"):
        corrupted = graph.with_injected_error(
            edge_id="false-001",
            source="claim:evt-205",
            target="source:incident-106",
            relation="SUPPORTED_BY",
            association=0.6,
        )
        learning = LearningConfig(enabled=True)
        learn_config = replace(config, learning=learning)
        state = AssociationState.from_graph(corrupted, learning.policy_version)
        memory = AssociativeMemory(
            graph=corrupted, config=learn_config, strategy="spreading",
            association_state=state,
        )
        learner = PathwayLearner(learning, state, corrupted)
        history = []
        for round_index in range(rounds):
            result = memory.retrieve(case.cue)
            admitted = result.admitted_sources()
            distractor_admitted = any(
                source in admitted for source in case.distractor_sources
            )
            used_edges: set[str] = set()
            for memory_item in result.admitted:
                edges = path_edge_ids(result.state, memory_item)
                used_edges.update(edges)
                if policy == "frequency-only":
                    learner.frequency_only_update(edges)
                else:
                    expected = set(case.expected_sources)
                    useful = bool(expected & set(memory_item.source_ids))
                    learner.record_outcome(
                        OutcomeRecord(
                            cue=case.cue,
                            outcome=GOOD if useful else BAD,
                            path_edges=edges,
                        )
                    )
            if policy == "outcome-gated":
                learner.decay_unused(used_edges)
            state.apply_to(corrupted)
            history.append(
                {
                    "round": round_index,
                    "false_edge_weight": round(
                        state.current_weights().get("false-001", 0.0), 4
                    ),
                    "distractor_admitted": distractor_admitted,
                    "admitted": admitted,
                }
            )
        refusals: dict[str, int] = {}
        for _edge_id, why in learner.refusals:
            refusals[why] = refusals.get(why, 0) + 1
        health = check_graph(corrupted, state)
        outcome_report[policy] = {
            "history": history,
            "final_false_edge_weight": history[-1]["false_edge_weight"],
            "initial_false_edge_weight": 0.6,
            "updates": len(state.updates),
            "refusals": refusals,
            "health_flags": [issue.check for issue in health.issues],
        }
    return {
        "experiment": "E5-H",
        "question": "Can repeated wrong retrieval create self-reinforcing "
        "error, and do the safeguards stop it?",
        "cue": case.cue,
        "rounds": rounds,
        "policies": outcome_report,
    }


# -- suite ---------------------------------------------------------------


EXPERIMENTS = {
    "E5-A": e5a_direct_vs_associative,
    "E5-B": e5b_conditioned_branching,
    "E5-C": e5c_multi_hop,
    "E5-D": e5d_precision_cost,
    "E5-E": e5e_hub_resistance,
    "E5-F": e5f_false_edge,
    "E5-G": e5g_static_vs_adaptive,
    "E5-H": e5h_reinforcement_pathology,
}


def _code_commit() -> str:
    """Freeze the commit a run was produced at, per the run contract."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        return proc.stdout.strip() or "unspecified"
    except Exception:
        return "unspecified"


def run_suite(
    config: AssociativeConfig | None = None,
    only: tuple[str, ...] | None = None,
) -> dict:
    config = config or AssociativeConfig()
    if config.code_commit == "unspecified":
        config = replace(config, code_commit=_code_commit())
    graph = build_graph()
    cases = build_cases()
    wanted = only or tuple(EXPERIMENTS)
    started = time.perf_counter()
    results = {
        name: EXPERIMENTS[name](graph, cases, config)
        for name in wanted
        if name in EXPERIMENTS
    }
    health = check_graph(graph)
    return {
        "suite_version": SUITE_VERSION,
        "graph_version": graph.version,
        "corpus_version": graph.corpus_version,
        "cue_set_version": "assoc-cues-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wall_seconds": round(time.perf_counter() - started, 3),
        "config": config.to_dict(),
        "graph_health": dataclasses.asdict(health),
        "limitation": (
            "Retrieval-level only: no reader, no generated answers. Answer "
            "correctness against the Chapter 3 baseline and the Chapter 4 "
            "graph requires those chapters' frozen runs and is not claimed "
            "here. Seeding uses a deterministic hashing embedder, which "
            "preserves no semantics; embedding-seeded conditions are a "
            "lower bound, not a measurement of dense seeding."
        ),
        "experiments": results,
    }


def save_suite(report: dict, runs_root: Path, run_id: str) -> Path:
    run_dir = Path(runs_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "e5-suite.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return run_dir
