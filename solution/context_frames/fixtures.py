"""E10 fixtures: frames, tasks, and the hidden context ledger.

Each task carries an oracle ledger over corpus units:

``MUST``        evidence without which the work cannot be done correctly
``SHOULD``      evidence that materially helps
``OPTIONAL``    admissible, neither required nor harmful
``DISTRACTOR``  in-scope but not useful for this objective
``HARMFUL``     superseded or out-of-project material that misleads

Units not named in a ledger default to ``DISTRACTOR`` for that task.

The ledgers are authored per task. The ``ProjectFrame`` preference table
is authored once per project and shared by every task of a work type, so
it cannot encode a particular task's answer. That separation is the
design's main guard against circularity, and the frame-capture and
inferred-frame experiments measure what happens when it is violated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .corpus import (COCODER, MEMORY_BOOK, WRITER, K_ARCH, K_BASELINE,
                     K_CITATION, K_CONCEPTS, K_CONTRACT, K_IMPL, K_METHOD,
                     K_OPEN_LOOP, K_PLANNING, K_PROSE, K_RESEARCH, K_RESULT,
                     K_SESSION, K_STYLE)
from .model import ProjectFrame, WorkFrame, WorkSignal

MUST = "MUST"
SHOULD = "SHOULD"
OPTIONAL = "OPTIONAL"
DISTRACTOR = "DISTRACTOR"
HARMFUL = "HARMFUL"

# Work types. A work type is a shape of work, not a task.
WT_PUBLICATION = "publication_review"
WT_ARCHITECTURE = "architecture_review"
WT_RELEASE = "release_readiness"
WT_EXPERIMENT = "experiment_analysis"
WT_IMPLEMENTATION = "implementation_review"

AS_OF = "2026-09-20T12:00:00Z"


# --------------------------------------------------------------------------
# Project frames: durable, versioned configuration.
# --------------------------------------------------------------------------

def PF_MEMORY_BOOK() -> ProjectFrame:
    return ProjectFrame(
        project_id=MEMORY_BOOK,
        version="v1",
        purpose="Build and empirically test an architecture for AI memory.",
        objectives=(
            "mechanisms earn their complexity experimentally",
            "compare every layer against the Chapter 3 retrieval baseline",
            "preserve provenance and historical truth",
            "distinguish hypothesis from result",
        ),
        constraints=(
            "same reader, corpus and context budget across conditions",
            "publish per-question results before any aggregate",
            "prefer the simpler mechanism when results tie",
        ),
        include_projects=(MEMORY_BOOK,),
        evidence_preferences=(
            (WT_PUBLICATION,
             (K_PROSE, K_CONCEPTS, K_CITATION, K_STYLE, K_PLANNING)),
            (WT_ARCHITECTURE,
             (K_METHOD, K_BASELINE, K_CONTRACT, K_RESULT, K_ARCH, K_PROSE)),
            (WT_RELEASE,
             (K_OPEN_LOOP, K_STYLE, K_RESULT, K_PROSE, K_IMPL)),
            (WT_EXPERIMENT,
             (K_RESULT, K_BASELINE, K_CONTRACT, K_METHOD)),
            (WT_IMPLEMENTATION,
             (K_IMPL, K_RESULT, K_ARCH, K_METHOD)),
            ("default", (K_RESULT, K_ARCH, K_PROSE)),
        ),
    )


def PF_WRITER() -> ProjectFrame:
    return ProjectFrame(
        project_id=WRITER, version="v1",
        purpose="Draft and revise long documents with cited sources.",
        objectives=("keep every claim traceable to a source passage",
                    "reduce redundant context per section"),
        constraints=("surface contradictory sources rather than reconcile",),
        include_projects=(WRITER,),
        evidence_preferences=(
            (WT_IMPLEMENTATION, (K_IMPL, K_PLANNING, K_BASELINE, K_RESULT)),
            ("default", (K_IMPL, K_PLANNING, K_RESULT)),
        ),
    )


def PF_COCODER() -> ProjectFrame:
    return ProjectFrame(
        project_id=COCODER, version="v1",
        purpose="Assist code changes inside a repository under a token budget.",
        objectives=("raise patch acceptance", "cut unused admitted context"),
        constraints=("every edit names the files and symbols that justify it",),
        include_projects=(COCODER,),
        evidence_preferences=(
            (WT_IMPLEMENTATION, (K_IMPL, K_PLANNING, K_RESULT, K_METHOD)),
            ("default", (K_IMPL, K_PLANNING, K_RESULT)),
        ),
    )


PROJECT_FRAMES = {MEMORY_BOOK: PF_MEMORY_BOOK, WRITER: PF_WRITER,
                  COCODER: PF_COCODER}


# --------------------------------------------------------------------------
# Work frames.
# --------------------------------------------------------------------------

def _wf(work_frame_id: str, project: str, objective: str, work_type: str,
        signals: tuple[WorkSignal, ...],
        constraints: tuple[str, ...] = (),
        derivation: str = "declared") -> WorkFrame:
    ids = tuple(s.signal_id for s in signals)
    return WorkFrame(
        work_frame_id=work_frame_id, project_id=project, objective=objective,
        work_type=work_type, as_of=AS_OF, active_constraints=constraints,
        signals=signals,
        provenance=(("objective", ids), ("work_type", ids)),
        derivation=derivation)


S_PUB = WorkSignal("sig-pub-1", "user_message",
                   "Chapter 10 is in the publication queue for this release; "
                   "check the prose, the citations and the front matter.",
                   AS_OF)
S_PUB_STATE = WorkSignal("sig-pub-2", "project_state",
                         "Release branch open; hugo build gate must pass.",
                         AS_OF)
S_ARCH = WorkSignal("sig-arch-1", "user_message",
                    "I am not sure Chapter 10 is the right next step. Decide "
                    "whether it belongs in the architecture at all, measured "
                    "against what we already beat.", AS_OF)
S_ARCH_STATE = WorkSignal("sig-arch-2", "project_state",
                          "Chapters 8 and 9 have committed runs; Chapter 10 "
                          "has none.", AS_OF)
S_NOISE = WorkSignal("sig-noise", "event",
                     "Nightly dependency audit finished with no findings.",
                     AS_OF)


def WF_T1_PUBLICATION() -> WorkFrame:
    return _wf("wf-t1-pub", MEMORY_BOOK,
               "Prepare Chapter 10 for publication.", WT_PUBLICATION,
               (S_PUB, S_PUB_STATE),
               ("front matter and build gate must pass",))


def WF_T1_ARCHITECTURE() -> WorkFrame:
    return _wf("wf-t1-arch", MEMORY_BOOK,
               "Decide whether Chapter 10 is the correct next architectural "
               "step for the book.", WT_ARCHITECTURE,
               (S_ARCH, S_ARCH_STATE),
               ("remain grounded in the definition of memory",
                "improve measurably over the retrieval baseline"))


def WF_T2(project: str) -> WorkFrame:
    signal = WorkSignal(f"sig-ctx-{project}", "user_message",
                        "How should we improve the context system?", AS_OF)
    return _wf(f"wf-t2-{project}", project,
               "Improve the context system.", WT_IMPLEMENTATION, (signal,))


def WF_T3() -> WorkFrame:
    signals = (
        WorkSignal("sig-t3-1", "user_message",
                   "Return to the retrieval baseline and ask what the next "
                   "mechanism actually improves.", AS_OF),
        WorkSignal("sig-t3-2", "project_state",
                   "Preceding sessions discussed intention extraction at "
                   "length.", AS_OF),
    )
    return _wf("wf-t3", MEMORY_BOOK,
               "Re-evaluate the architecture from the retrieval baseline.",
               WT_ARCHITECTURE, signals)


def WF_T4() -> WorkFrame:
    signal = WorkSignal("sig-t4", "test_failure",
                        "Baseline ingest test failed: connection refused on "
                        "the configured store.", AS_OF)
    return _wf("wf-t4", MEMORY_BOOK,
               "Fix the baseline store configuration.", WT_IMPLEMENTATION,
               (signal,))


def WF_T5() -> WorkFrame:
    signal = WorkSignal("sig-t5", "agent_task",
                        "State what the book requires before a mechanism is "
                        "credited with an improvement.", AS_OF)
    return _wf("wf-t5", MEMORY_BOOK,
               "State the evidence requirements for crediting a mechanism.",
               WT_ARCHITECTURE, (signal,))


def WF_T6() -> WorkFrame:
    signal = WorkSignal("sig-t6", "user_message",
                        "What rule governs whether a new memory layer enters "
                        "the book?", AS_OF)
    return _wf("wf-t6", MEMORY_BOOK,
               "Restate the rule governing entry of a new memory layer.",
               WT_ARCHITECTURE, (signal,))


def WF_T7_RELEASE() -> WorkFrame:
    signal = WorkSignal("sig-t7-rel", "scheduled_job",
                        "Release readiness sweep: report outstanding work "
                        "before the cut.", AS_OF)
    return _wf("wf-t7-rel", MEMORY_BOOK,
               "Report outstanding work blocking the release.", WT_RELEASE,
               (signal,))


def WF_T7_PUBLICATION() -> WorkFrame:
    signal = WorkSignal("sig-t7-pub", "user_message",
                        "What is left to do on Chapter 10 before it reads "
                        "properly?", AS_OF)
    return _wf("wf-t7-pub", MEMORY_BOOK,
               "Finish the prose of Chapter 10.", WT_PUBLICATION, (signal,))


# --------------------------------------------------------------------------
# Tasks.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Task:
    task_id: str
    query: str
    work_frame: WorkFrame
    ledger: dict[str, str]
    key_claims: tuple[tuple[str, tuple[str, ...]], ...] = ()
    forbidden_claims: tuple[tuple[str, tuple[str, ...]], ...] = ()
    family: str = ""
    note: str = ""

    @property
    def project_id(self) -> str:
        return self.work_frame.project_id

    def label(self, unit_id: str) -> str:
        return self.ledger.get(unit_id, DISTRACTOR)

    def required(self) -> set[str]:
        return {u for u, lab in self.ledger.items() if lab == MUST}

    def useful(self) -> set[str]:
        return {u for u, lab in self.ledger.items()
                if lab in (MUST, SHOULD)}

    def harmful(self) -> set[str]:
        return {u for u, lab in self.ledger.items() if lab == HARMFUL}

    def to_dict(self) -> dict:
        return {"task_id": self.task_id, "query": self.query,
                "family": self.family, "note": self.note,
                "work_frame": self.work_frame.to_dict(),
                "ledger": dict(sorted(self.ledger.items()))}


def _ledger(**groups: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for label, ids in groups.items():
        for unit_id in ids:
            out[unit_id] = label
    return out


_STALE_ALL = ("mb-stale-ch06-title", "mb-stale-ch10-plan",
              "mb-stale-nexus-selects", "mb-stale-sqlite")

REVIEW_QUERY = "Review Chapter 10 and tell me what we should do with it."


def T1_PUBLICATION() -> Task:
    return Task(
        task_id="T1-publication", query=REVIEW_QUERY,
        work_frame=WF_T1_PUBLICATION(),
        family="same-query-different-goal",
        note="Publication review: the chapter's own text and its apparatus.",
        ledger=_ledger(
            MUST=("mb-ch10-prose-opening", "mb-ch10-prose-schema",
                  "mb-ch10-refs", "mb-style-conventions"),
            SHOULD=("mb-ch10-concepts", "mb-ch10-priority-refusal",
                    "mb-ch10-experiment-pending", "mb-ch09-handoff",
                    "mb-ch11-opening", "mb-style-frontmatter",
                    "mb-style-citations", "mb-style-build"),
            OPTIONAL=("mb-research-prospective", "mb-research-intention-schema",
                      "mb-arch-spine"),
            HARMFUL=_STALE_ALL,
        ),
        key_claims=(("chapter-10-text", ("intention", "chapter 10")),
                    ("apparatus", ("citation", "reference", "front matter",
                                   "style"))),
        forbidden_claims=(("stale-ch6", ("similarity is not memory",)),),
    )


def T1_ARCHITECTURE() -> Task:
    return Task(
        task_id="T1-architecture", query=REVIEW_QUERY,
        work_frame=WF_T1_ARCHITECTURE(),
        family="same-query-different-goal",
        note="Architectural review: the same query, a different decision.",
        ledger=_ledger(
            MUST=("mb-method-earn", "mb-ch03-baseline-role", "mb-contract-q6",
                  "mb-ch09-result", "mb-ch10-experiment-pending",
                  "mb-arch-spine"),
            SHOULD=("mb-ch08-result", "mb-arch-q6-open", "mb-arch-definition",
                    "mb-ch10-priority-refusal", "mb-method-baseline-rule",
                    "mb-ch06-result", "mb-method-evidence-discipline",
                    "mb-ch10-prose-opening"),
            OPTIONAL=("mb-ch03-baseline-strength", "mb-ch07-result",
                      "mb-contract-failure-classes", "mb-arch-layers"),
            HARMFUL=_STALE_ALL,
        ),
        key_claims=(("no-result", ("no committed run", "experiment pending",
                                   "no run", "not been executed",
                                   "pending")),
                    ("baseline", ("baseline", "chapter 3", "rag")),
                    ("earn-rule", ("earn", "beat", "improve over"))),
        forbidden_claims=(("stale-plan", ("chapter 11 is open loops",)),),
    )


def T2(project: str) -> Task:
    query = "How should we improve the context system?"
    ledgers = {
        MEMORY_BOOK: _ledger(
            MUST=("mb-arch-q6-open", "mb-ch03-admission-note",
                  "mb-contract-q6"),
            SHOULD=("mb-research-context-engineering", "mb-ch03-baseline-role",
                    "mb-arch-layers", "mb-method-earn"),
            OPTIONAL=("mb-research-goal-conditioned", "mb-ch06-result"),
            HARMFUL=("mb-stale-nexus-selects",),
        ),
        WRITER: _ledger(
            MUST=("wr-context-runtime", "wr-improve-context", "wr-rag-baseline"),
            SHOULD=("wr-retrieval-eval", "wr-memory-store"),
            OPTIONAL=("wr-evidence-policy",),
        ),
        COCODER: _ledger(
            MUST=("cc-context-window", "cc-improve-context"),
            SHOULD=("cc-eval-harness", "cc-memory-notes"),
            OPTIONAL=("cc-evidence-refs",),
        ),
    }
    claims = {
        MEMORY_BOOK: (("budget", ("budget", "admission", "context")),),
        WRITER: (("writer", ("redundancy", "embedding", "candidate", "budget")),),
        COCODER: (("cocoder", ("symbol", "token budget", "file")),),
    }
    return Task(task_id=f"T2-{project}", query=query, work_frame=WF_T2(project),
                ledger=ledgers[project], family="same-query-different-project",
                note="Shared vocabulary across three projects.",
                key_claims=claims[project])


def T3() -> Task:
    return Task(
        task_id="T3-goal-switch",
        query="What should the next chapter do?",
        work_frame=WF_T3(), family="goal-switch-against-recency",
        note="The most recent history is no longer the most useful history.",
        ledger=_ledger(
            MUST=("mb-method-earn", "mb-ch03-baseline-role", "mb-arch-q6-open",
                  "mb-arch-spine"),
            SHOULD=("mb-ch09-result", "mb-ch08-result", "mb-contract-q6",
                    "mb-session-pivot", "mb-method-baseline-rule"),
            OPTIONAL=("mb-arch-definition", "mb-ch10-experiment-pending"),
            DISTRACTOR=("mb-session-intent-1", "mb-session-intent-2",
                        "mb-session-intent-3", "mb-research-intention-schema",
                        "mb-research-prospective"),
            HARMFUL=("mb-stale-ch10-plan", "mb-stale-nexus-selects"),
        ),
        key_claims=(("baseline", ("baseline", "retrieval", "rag")),
                    ("question-six", ("context", "what should i remember",
                                      "question 6", "selection"))),
        forbidden_claims=(("intention-anchor",
                           ("intention record", "intention schema")),),
    )


def T4() -> Task:
    return Task(
        task_id="T4-current-vs-stale",
        query="What store does the baseline use, and how is search done?",
        work_frame=WF_T4(), family="current-versus-stale",
        note="A superseded design remains highly similar to the query.",
        ledger=_ledger(
            MUST=("mb-impl-postgres",),
            SHOULD=("mb-ch03-baseline-role", "mb-impl-test-paths"),
            OPTIONAL=("mb-arch-layers", "mb-impl-graphrag"),
            HARMFUL=("mb-stale-sqlite",),
        ),
        key_claims=(("postgres", ("postgres", "pgvector")),
                    ("search", ("hnsw", "tsvector", "full-text", "lexical"))),
        forbidden_claims=(("sqlite-current", ("uses sqlite", "stores .* in sqlite",
                                              "sqlite so the baseline")),),
    )


def T5() -> Task:
    return Task(
        task_id="T5-support-vs-topicality",
        query="What does the book require before a mechanism is credited with "
              "an improvement?",
        work_frame=WF_T5(), family="support-versus-topicality",
        note="Topical neighbours from other projects must not substitute for "
             "the book's own rule.",
        ledger=_ledger(
            MUST=("mb-method-evidence-discipline", "mb-method-baseline-rule",
                  "mb-contract-failure-classes"),
            SHOULD=("mb-method-earn", "mb-contract-frozen-run",
                    "mb-contract-q6"),
            OPTIONAL=("mb-ch06-result", "mb-refutes-ch9-scope"),
            DISTRACTOR=("wr-evidence-policy", "cc-evidence-refs",
                        "wr-retrieval-eval", "cc-eval-harness"),
            HARMFUL=_STALE_ALL,
        ),
        key_claims=(("baselines", ("baseline", "ablation")),
                    ("failure-class", ("failure class", "attribution",
                                       "regression"))),
    )


def T6() -> Task:
    return Task(
        task_id="T6-echo-coalescing",
        query="What rule governs whether a new memory layer enters the book?",
        work_frame=WF_T6(), family="redundancy-and-echo",
        note="Four restatements of one rule must not occupy four slots.",
        ledger=_ledger(
            MUST=("mb-method-earn",),
            SHOULD=("mb-method-baseline-rule", "mb-ch03-baseline-role",
                    "mb-method-evidence-discipline"),
            OPTIONAL=("mb-echo-baseline-1", "mb-echo-baseline-2",
                      "mb-echo-baseline-3", "mb-echo-baseline-4",
                      "mb-arch-spine", "mb-contract-q6"),
            HARMFUL=_STALE_ALL,
        ),
        key_claims=(("earn", ("earn", "beat", "baseline")),),
    )


def T7_RELEASE() -> Task:
    return Task(
        task_id="T7-release", query="What is left to do?",
        work_frame=WF_T7_RELEASE(), family="open-loop-conditioned",
        note="Open loops matter here because the work type makes them matter.",
        ledger=_ledger(
            MUST=("mb-loop-ch10-experiment", "mb-loop-readme-drift",
                  "mb-loop-ch11-recap"),
            SHOULD=("mb-loop-real-corpus", "mb-ch10-experiment-pending",
                    "mb-style-build"),
            OPTIONAL=("mb-arch-q6-open", "mb-style-citations"),
            HARMFUL=_STALE_ALL,
        ),
        key_claims=(("loops", ("readme", "chapter 10", "recap", "run")),),
    )


def T7_PUBLICATION() -> Task:
    return Task(
        task_id="T7-publication", query="What is left to do?",
        work_frame=WF_T7_PUBLICATION(), family="open-loop-conditioned",
        note="The same query under a prose objective: loops stop dominating.",
        ledger=_ledger(
            MUST=("mb-ch10-prose-opening", "mb-ch10-prose-schema",
                  "mb-style-conventions"),
            SHOULD=("mb-ch10-refs", "mb-ch10-concepts", "mb-style-frontmatter",
                    "mb-ch11-opening", "mb-ch09-handoff"),
            OPTIONAL=("mb-loop-ch10-experiment", "mb-loop-ch11-recap",
                      "mb-style-build", "mb-style-citations"),
            HARMFUL=_STALE_ALL,
        ),
        key_claims=(("prose", ("chapter 10", "prose", "intention")),),
    )


def all_tasks() -> list[Task]:
    return [T1_PUBLICATION(), T1_ARCHITECTURE(), T2(MEMORY_BOOK), T2(WRITER),
            T2(COCODER), T3(), T4(), T5(), T6(), T7_RELEASE(),
            T7_PUBLICATION()]


def task_by_id(task_id: str) -> Task:
    for task in all_tasks():
        if task.task_id == task_id:
            return task
    raise KeyError(task_id)


@dataclass
class LedgerAudit:
    """Sanity checks the ledgers must pass before any run is believed."""
    unknown_units: list[str] = field(default_factory=list)
    out_of_scope_required: list[str] = field(default_factory=list)
    empty_required: list[str] = field(default_factory=list)


def audit_ledgers() -> LedgerAudit:
    from .corpus import by_id
    units = by_id()
    audit = LedgerAudit()
    for task in all_tasks():
        for unit_id in task.ledger:
            if unit_id not in units:
                audit.unknown_units.append(f"{task.task_id}:{unit_id}")
        if not task.required():
            audit.empty_required.append(task.task_id)
        scope = PROJECT_FRAMES[task.project_id]().scope()
        for unit_id in task.required():
            unit = units.get(unit_id)
            if unit is not None and unit.project_id not in scope:
                audit.out_of_scope_required.append(
                    f"{task.task_id}:{unit_id}")
    return audit
