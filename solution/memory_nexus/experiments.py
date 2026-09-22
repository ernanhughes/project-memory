"""The Chapter 6 experiment suite, E6-A through E6-H.

Everything here reads the measured task-by-capability matrix. That
ordering is the chapter's method: establish whether specialisation exists
before building anything that exploits it, and report honestly if it does
not.

E6-A  fixed-strategy matrix — does specialisation exist at all?
E6-B  oracle routing — how much value is available to perfect routing?
E6-C  rule router — the minimum viable Nexus
E6-D  generative router — does reading the question help?
E6-E  bounded decision router — is a classifier enough?
E6-F  sequential escalation — does observe-then-choose beat one shot?
E6-G  stop policy — premature stopping against needless continuation
E6-H  transfer — held-out question families
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .capabilities.registry import (
    ASSOCIATIVE,
    GRAPH_BASIC,
    GRAPH_GLOBAL,
    GRAPH_LOCAL,
    NONE,
    RAG,
    RAW_EVIDENCE,
)
from .control.controller import NexusController
from .evaluation.regret import (
    headroom,
    pareto_frontier,
    score_routes,
)
from .evaluation.utility import Utility
from .policies.classifier import ClassifierPolicy, LogisticRouter
from .policies.fixed import FixedPolicy, RandomPolicy
from .policies.oracle import (
    CheapestAdequateOracle,
    OraclePolicy,
    best_by_utility,
    cheapest_adequate,
)
from .policies.rules import LeakyFamilyPolicy, RulePolicy
from .policies.sequential import SequentialPolicy
from .state.features import audit_state
from .training.dataset import (
    build_samples,
    check_no_answer_tokens,
    split_by_family,
)

SUITE_VERSION = "E6-v0.1"

# Families held out for the transfer test. Whole families, never
# individual questions: this benchmark's tasks share wording within a
# family, so a random split would leak paraphrases across the boundary.
HOLDOUT_FAMILIES = ("indirect", "no-memory")


def _routes_from_policy(policy, states, registry, one_shot=True):
    """Collect one-shot route choices without executing any capability."""
    chosen: dict[str, str] = {}
    started = time.perf_counter()
    for state in states:
        action = policy.decide(state, registry)
        chosen[state.query_id] = action.capability
    return chosen, (time.perf_counter() - started) * 1000.0


# -- E6-A: does specialisation exist? ------------------------------------


def e6a_fixed_matrix(matrix, utility) -> dict:
    """Every capability on every task. The falsification condition."""
    fixed = matrix.fixed_policy_scores(utility)
    dominance = matrix.dominance(utility)
    per_task: dict[str, dict] = {}
    for query_id, cells in matrix.by_query().items():
        measured = [cell for cell in cells if cell.measured]
        if not measured:
            continue
        per_task[query_id] = {
            cell.capability_id: utility.dimensions(cell) for cell in measured
        }
    frontier = pareto_frontier(
        {
            capability_id: (record["quality"], record["cost_units"])
            for capability_id, record in fixed.items()
        }
    )
    return {
        "experiment": "E6-A",
        "question": "Do different memory capabilities win different tasks, "
        "or does one dominate?",
        "fixed_policies": fixed,
        "dominance": dominance,
        "quality_cost_frontier": frontier,
        "per_task": per_task,
    }


# -- E6-B: oracle headroom -----------------------------------------------


def e6b_oracle(matrix, utility) -> dict:
    """How much is perfect routing worth over the best fixed policy?"""
    room = headroom(matrix, utility)
    best = best_by_utility(matrix, utility)
    cheapest = cheapest_adequate(
        matrix, utility.weights.adequacy_threshold, utility
    )
    agreement = sum(
        1 for query_id in best if cheapest.get(query_id) == best[query_id]
    )
    return {
        "experiment": "E6-B",
        "question": "How much value could perfect routing provide?",
        "headroom": room,
        "oracle_best_utility_routes": dict(sorted(best.items())),
        "oracle_cheapest_adequate_routes": dict(sorted(cheapest.items())),
        "oracles_agree_on": agreement,
        "oracle_route_diversity": len(set(best.values())),
    }


# -- E6-C .. E6-E: one-shot routers ---------------------------------------


def e6c_to_e6e_routers(
    matrix, utility, states, registry, config, routing_families,
    llm_policy=None,
) -> dict:
    """Rule, random, fixed, leaked-label, classifier, and generative routers."""
    threshold = utility.weights.adequacy_threshold
    reports: dict[str, dict] = {}
    state_by_query = {state.query_id: state for state in states}

    def evaluate(policy, name, one_shot=True):
        chosen, latency_ms = _routes_from_policy(policy, states, registry)
        report = score_routes(
            policy.policy_type, policy.policy_version, chosen, matrix,
            utility, threshold,
        )
        payload = report.to_dict()
        payload["router_latency_ms_total"] = round(latency_ms, 3)
        payload["router_latency_ms_per_query"] = round(
            latency_ms / max(1, len(states)), 4
        )
        payload["manifest"] = policy.manifest()
        reports[name] = payload
        return payload

    for capability_id in (
        NONE, RAG, GRAPH_BASIC, GRAPH_LOCAL, GRAPH_GLOBAL, ASSOCIATIVE,
        RAW_EVIDENCE,
    ):
        if capability_id in registry:
            evaluate(FixedPolicy(capability_id), f"fixed:{capability_id}")
    evaluate(RandomPolicy(seed=7), "random")
    evaluate(RulePolicy(), "rules")
    evaluate(
        LeakyFamilyPolicy(routing_families), "leaky-family-control"
    )
    evaluate(
        OraclePolicy(best_by_utility(matrix, utility)), "oracle"
    )
    evaluate(
        CheapestAdequateOracle(
            cheapest_adequate(matrix, threshold, utility)
        ),
        "oracle-cheapest-adequate",
    )

    # Classifier, trained on held-in families only.
    samples, dataset_report = build_samples(
        matrix, utility, state_by_query,
        label_rule="cheapest_adequate",
        routing_families=routing_families,
    )
    dataset_report["sanity"] = check_no_answer_tokens(samples, None)
    train, test = split_by_family(samples, HOLDOUT_FAMILIES)
    labels = sorted({sample.label for sample in samples})
    classifier_report = {"trained": False}
    if train and labels:
        router = LogisticRouter(labels, config.classifier)
        classifier_report = router.fit(
            [(sample.features, sample.label) for sample in train]
        )
        policy = ClassifierPolicy(router, config.classifier)
        evaluate(policy, "classifier")
        # Held-out families only: the transfer condition.
        holdout_states = [
            state_by_query[sample.query_id] for sample in test
            if sample.query_id in state_by_query
        ]
        if holdout_states:
            transfer_policy = ClassifierPolicy(router, config.classifier)
            chosen, _ = _routes_from_policy(
                transfer_policy, holdout_states, registry
            )
            transfer = score_routes(
                "classifier-transfer", config.classifier.model_version,
                chosen, matrix, utility, threshold,
            )
            reports["classifier-transfer"] = transfer.to_dict()

    if llm_policy is not None:
        evaluate(llm_policy, "llm")

    return {
        "experiment": "E6-C..E",
        "question": "Can a router recover the oracle's headroom, and how "
        "much machinery does it take?",
        "routers": reports,
        "dataset": dataset_report,
        "classifier_training": classifier_report,
        "holdout_families": list(HOLDOUT_FAMILIES),
        "train_size": len(train) if 'train' in dir() else 0,
        "test_size": len(test) if 'test' in dir() else 0,
    }


# -- E6-F/E6-G: sequential control ------------------------------------------


def e6f_sequential(
    matrix, utility, states, registry, config, systems, reader, tasks
) -> dict:
    """Cheap-first escalation, executed for real against the live systems."""
    controller = NexusController(registry, config)
    policy = SequentialPolicy(
        context_budget=config.context_budget,
        max_actions=config.controller.max_actions,
    )
    by_id = {task.task_id: task for task in tasks}
    episodes = []
    records = []
    for state in states:
        episode = controller.run(policy, state, one_shot=False)
        episodes.append(episode)
        task = by_id[state.query_id]
        answer = reader(task.prompt, episode.evidence_text)
        from .evaluation.matrix import _map_citations
        from memory_measurement.scorers import score_task
        from memory_measurement.tasks import SystemOutput

        cited = _map_citations(answer, systems.history_source_ids)
        output = SystemOutput(
            task_id=task.task_id,
            answer=answer.text or None,
            cited_sources=tuple(cited),
            retrieved_ids=tuple(episode.source_ids),
            abstained=answer.abstained
            or episode.terminal in ("ABSTAIN", "ASK_HUMAN"),
            context_tokens=episode.cost.context_tokens,
        )
        observations = score_task(
            task, output, tuple(systems.history_source_ids)
        )
        metrics = {
            o.metric: (
                1.0 if o.value is True else 0.0 if o.value is False else o.value
            )
            for o in observations
        }
        records.append(
            {
                "query_id": state.query_id,
                "actions": list(episode.actions),
                "terminal": episode.terminal,
                "stopped_because": episode.stopped_because,
                "router_failures": list(episode.router_failures),
                "metrics": metrics,
                "cost": episode.cost.to_dict(),
                "router_latency_ms": round(episode.router_latency_ms, 3),
                "answer": output.answer,
                "sources": list(episode.source_ids),
            }
        )

    quality_metrics = [
        r["metrics"] for r in records
    ]

    def mean_of(names):
        values = [
            metrics[name]
            for metrics in quality_metrics
            for name in names
            if name in metrics and metrics[name] is not None
        ]
        return round(sum(values) / len(values), 4) if values else None

    from .evaluation.utility import EVIDENCE_METRICS, QUALITY_METRICS

    actions_per_query = [len(r["actions"]) for r in records]
    escalations = sum(1 for count in actions_per_query if count > 1)
    return {
        "experiment": "E6-F",
        "question": "Does observing a cheap result before choosing again "
        "beat one-shot routing?",
        "policy_version": policy.policy_version,
        "records": records,
        "summary": {
            "tasks": len(records),
            "mean_actions": round(
                sum(actions_per_query) / max(1, len(actions_per_query)), 3
            ),
            "escalated": escalations,
            "escalation_rate": round(
                escalations / max(1, len(records)), 3
            ),
            "quality": mean_of(QUALITY_METRICS),
            "evidence": mean_of(EVIDENCE_METRICS),
            "mean_cost_units": round(
                sum(r["cost"]["cost_units"] for r in records)
                / max(1, len(records)), 3
            ),
            "mean_latency_ms": round(
                sum(r["cost"]["latency_ms"] for r in records)
                / max(1, len(records)), 1
            ),
            "mean_context_tokens": round(
                sum(r["cost"]["context_tokens"] for r in records)
                / max(1, len(records)), 1
            ),
            "router_failures": _count_failures(records),
            "terminals": _count_terminals(records),
        },
        "episodes": [episode.to_dict() for episode in episodes],
    }


def _count_failures(records) -> dict:
    counts: dict[str, int] = {}
    for record in records:
        for failure in record["router_failures"]:
            counts[failure] = counts.get(failure, 0) + 1
    return dict(sorted(counts.items()))


def _count_terminals(records) -> dict:
    counts: dict[str, int] = {}
    for record in records:
        counts[record["terminal"]] = counts.get(record["terminal"], 0) + 1
    return dict(sorted(counts.items()))


def e6g_stop_policy(sequential_report, matrix, utility) -> dict:
    """Premature stopping against needless continuation.

    A stop is premature when the episode stopped with quality below the
    adequacy threshold while an unused capability in the matrix would have
    cleared it. A continuation is needless when the episode escalated and
    the first action had already reached the threshold.
    """
    threshold = utility.weights.adequacy_threshold
    premature = []
    needless = []
    correct = []
    for record in sequential_report["records"]:
        query_id = record["query_id"]
        cells = [
            cell for cell in matrix.by_query().get(query_id, [])
            if cell.measured
        ]
        if not cells:
            continue
        by_capability = {cell.capability_id: cell for cell in cells}
        achieved = [
            record["metrics"].get(name)
            for name in ("decision_exactness", "current_state_accuracy",
                         "historical_state_accuracy",
                         "abstention_correctness")
            if record["metrics"].get(name) is not None
        ]
        episode_quality = (
            sum(achieved) / len(achieved) if achieved else 0.0
        )
        unused = [
            cell for capability_id, cell in by_capability.items()
            if capability_id not in record["actions"]
        ]
        best_unused = max(
            (utility.quality(cell) for cell in unused), default=0.0
        )
        first = record["actions"][0] if record["actions"] else None
        first_quality = (
            utility.quality(by_capability[first])
            if first in by_capability else 0.0
        )
        if episode_quality < threshold and best_unused >= threshold:
            premature.append(query_id)
        elif len(record["actions"]) > 1 and first_quality >= threshold:
            needless.append(query_id)
        else:
            correct.append(query_id)
    total = len(premature) + len(needless) + len(correct)
    return {
        "experiment": "E6-G",
        "question": "Does the controller stop at the right moment?",
        "adequacy_threshold": threshold,
        "premature_stops": sorted(premature),
        "needless_continuations": sorted(needless),
        "correct_stops": sorted(correct),
        "stop_accuracy": round(len(correct) / total, 4) if total else None,
    }


# -- suite ---------------------------------------------------------------


def run_suite(
    matrix, utility, states, registry, config, routing_families,
    systems=None, reader=None, tasks=None, llm_policy=None,
    include_sequential=True,
) -> dict:
    started = time.perf_counter()
    leakage = sorted({
        field for state in states for field in audit_state(state)
    })
    results = {
        "E6-A": e6a_fixed_matrix(matrix, utility),
        "E6-B": e6b_oracle(matrix, utility),
        "E6-CDE": e6c_to_e6e_routers(
            matrix, utility, states, registry, config, routing_families,
            llm_policy=llm_policy,
        ),
    }
    if include_sequential and systems is not None and reader is not None:
        sequential = e6f_sequential(
            matrix, utility, states, registry, config, systems, reader, tasks
        )
        results["E6-F"] = sequential
        results["E6-G"] = e6g_stop_policy(sequential, matrix, utility)
    return {
        "suite_version": SUITE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wall_seconds": round(time.perf_counter() - started, 2),
        "config": config.to_dict(),
        "registry": registry.manifest(),
        "router_state_leakage": leakage,
        "matrix_manifest": matrix.manifest,
        "experiments": results,
    }


def save_suite(report: dict, runs_root: Path, run_id: str) -> Path:
    run_dir = Path(runs_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "e6-suite.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return run_dir
