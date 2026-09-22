"""The controlled corpus for E10.

Three projects share vocabulary on purpose. ``memory-book`` is this
book's own programme; ``writer`` and ``cocoder`` are neighbouring
projects that talk about memory, context, evidence, retrieval and
evaluation in their own terms. Semantic similarity therefore has
genuine opportunities to leak, and the cross-project measurements are
measurements rather than demonstrations of a straw failure.

Unit metadata comes from the layer that owns it and never from the task
ledger: ``kind`` is a corpus fact about the artifact, ``valid_until``
and ``superseded_by`` are Chapter 8 state, ``evidence_role``/``echo_of``
are Chapter 7 lineage, ``open_loop`` is a Chapter 9 expectation. The
oracle labels in ``fixtures.py`` are authored separately and are never
read by the policy.

Texts describe the book's own commitments and recorded state. Numbers
that appear in a unit are taken from committed run artifacts under
``experiments/benchmark/runs/``; no unit invents a measurement.
"""

from __future__ import annotations

from .model import MemoryUnit

MEMORY_BOOK = "memory-book"
WRITER = "writer"
COCODER = "cocoder"

# Evidence classes. These are properties of the artifact, not of a task.
K_PROSE = "chapter_prose"
K_CONCEPTS = "chapter_concepts"
K_CITATION = "citation"
K_STYLE = "style_rule"
K_METHOD = "method_rule"
K_ARCH = "architecture_note"
K_CONTRACT = "measurement_contract"
K_BASELINE = "baseline_result"
K_RESULT = "experiment_result"
K_RESEARCH = "research_note"
K_PLANNING = "planning_note"
K_OPEN_LOOP = "open_loop"
K_SESSION = "session_note"
K_IMPL = "implementation_detail"

EVIDENCE_CLASSES = (
    K_PROSE, K_CONCEPTS, K_CITATION, K_STYLE, K_METHOD, K_ARCH, K_CONTRACT,
    K_BASELINE, K_RESULT, K_RESEARCH, K_PLANNING, K_OPEN_LOOP, K_SESSION,
    K_IMPL,
)


def U(unit_id: str, project: str, kind: str, text: str,
      source_refs: tuple[str, ...] = (), event_time: str = "",
      valid_until: str | None = None, superseded_by: str | None = None,
      evidence_role: str = "support", echo_of: str | None = None,
      claim_key: str = "", open_loop: str | None = None,
      related: tuple[str, ...] = ()) -> MemoryUnit:
    return MemoryUnit(
        unit_id=unit_id, project_id=project, kind=kind,
        text=" ".join(text.split()), source_refs=source_refs,
        event_time=event_time, valid_from=event_time,
        valid_until=valid_until, superseded_by=superseded_by,
        evidence_role=evidence_role, echo_of=echo_of, claim_key=claim_key,
        open_loop=open_loop, related=related)


# --------------------------------------------------------------------------
# memory-book: method and architecture
# --------------------------------------------------------------------------

_METHOD = [
    U("mb-method-earn", MEMORY_BOOK, K_METHOD,
      """A mechanism enters the book only when a controlled experiment shows it
      beating the strongest conventional alternative on the failure class it
      claims to fix. Taxonomy does not earn a chapter; measured failure does.
      Every new layer is compared against the Chapter 3 retrieval baseline at a
      matched context budget, with the reader model and corpus held fixed.""",
      ("AGENTS.md", "planning/book-architecture.md"), "2026-09-15",
      claim_key="method.earn-complexity"),
    U("mb-method-baseline-rule", MEMORY_BOOK, K_METHOD,
      """Required baselines for any experiment: no memory, lexical retrieval,
      embedding top-k, embedding plus reranking, the current best system before
      the mechanism under test, the candidate system, and an ablation with the
      mechanism neutralised. A mechanism is not earned merely because an
      aggregate score rises; its intended failure class must improve without
      unacceptable regressions elsewhere.""",
      ("spec/benchmark-v0.1.md",), "2026-09-15",
      claim_key="method.baseline-ladder"),
    U("mb-method-evidence-discipline", MEMORY_BOOK, K_METHOD,
      """Three evidence categories are never mixed: established background,
      book hypothesis, and book result. A pending experiment's outcome is never
      stated as fact, including in chapter openings that recap earlier
      chapters. A fluent summary of retrieved text is not remembering;
      behaviour change is the test.""",
      ("AGENTS.md",), "2026-09-15", claim_key="method.evidence-discipline"),
    U("mb-arch-definition", MEMORY_BOOK, K_ARCH,
      """The book's core definition: memory is when past experience changes
      present behaviour. Retention alone is not memory, and retrieval alone is
      not memory. The architecture is an investigation, not a taxonomy, and
      mechanism vocabulary enters only when an experiment earns it.""",
      ("planning/book-architecture.md", "content/books/memory/01-chapter.md"),
      "2026-09-15", claim_key="arch.definition"),
    U("mb-arch-spine", MEMORY_BOOK, K_ARCH,
      """The six-question spine: where did we discuss X; what did we decide;
      why did we decide it; is it still true; what did we leave unfinished;
      and what should I remember right now. Question 6 covers retrieval policy,
      context assembly under a fixed budget, and downstream behavioural
      utility. Chapters are placed by which question they advance.""",
      ("planning/book-architecture.md",), "2026-09-15",
      claim_key="arch.spine"),
    U("mb-arch-layers", MEMORY_BOOK, K_ARCH,
      """Implemented layer order: Chapter 3 conventional RAG over raw history;
      Chapter 4 persistent derived graph; Chapter 5 cue-conditioned
      propagation; Chapter 6 routing across mechanisms; Chapter 7 support
      groups and derivation lineage; Chapter 8 ordered trajectories and
      bitemporal state; Chapter 9 expected transitions and open-loop status.
      Raw sources stay canonical and every derived layer is rebuildable.""",
      ("solution/README.md",), "2026-09-20", claim_key="arch.layers"),
    U("mb-arch-q6-open", MEMORY_BOOK, K_ARCH,
      """Question 6 remains the largest unanswered part of the architecture.
      Chapters 4 to 9 enrich what the system can know about history; none of
      them has yet been asked whether that enrichment produces a better working
      context than query-only retrieval at the same budget. The planning notes
      list importance and retrieval policy, and context assembly under a fixed
      token budget, as candidate mechanisms rather than chapter commitments.""",
      ("planning/book-architecture.md",), "2026-09-19",
      claim_key="arch.next-mechanism", open_loop="loop-q6"),
]

# --------------------------------------------------------------------------
# memory-book: measurement contract and baselines
# --------------------------------------------------------------------------

_MEASUREMENT = [
    U("mb-contract-q6", MEMORY_BOOK, K_CONTRACT,
      """Benchmark question family Q6, what should I remember right now:
      expected answer is a bounded memory selection that improves a downstream
      task. Primary metrics are downstream task success delta, useful-memory
      precision, distraction cost, token cost, and harmful-memory rate. Results
      are published per question before any aggregate.""",
      ("spec/benchmark-v0.1.md",), "2026-09-15", claim_key="contract.q6"),
    U("mb-contract-frozen-run", MEMORY_BOOK, K_CONTRACT,
      """A comparable run records corpus version and generator seed, query-set
      version, model and version, prompts, embedding and reranking models,
      chunking policy, retrieval and context budgets, code commit,
      configuration, per-case outputs, per-case evidence, and latency. Any
      change to a frozen variable creates a new run rather than silently
      replacing the old result.""",
      ("spec/benchmark-v0.1.md",), "2026-09-15",
      claim_key="contract.frozen-run"),
    U("mb-contract-failure-classes", MEMORY_BOOK, K_CONTRACT,
      """Failures are separated into ingestion, encoding and extraction,
      storage and indexing, retrieval, ranking, state and temporal reasoning,
      context assembly, downstream reasoning, and evaluator defect. Attribution
      to a stage is required before a mechanism is credited or blamed.""",
      ("spec/benchmark-v0.1.md",), "2026-09-15",
      claim_key="contract.failure-classes"),
    U("mb-ch03-baseline-role", MEMORY_BOOK, K_BASELINE,
      """Chapter 3 established the strong conventional baseline every later
      mechanism is measured against: sentence chunking at 2000 characters with
      300 characters of overlap, bge-m3 embeddings, lexical and dense retrieval
      fused by reciprocal rank fusion, reranking, and a context admission stage
      capped at 6000 characters over at most six passages, read by llama3.1:8b
      at temperature zero. The comparison contract is that the reader, corpus
      and context budget stay fixed while only the memory mechanism changes.""",
      ("content/books/memory/03-chapter.md",
       "experiments/benchmark/runs/ch3-20260919-ladder3"), "2026-09-19",
      claim_key="baseline.ch3-config"),
    U("mb-ch03-baseline-strength", MEMORY_BOOK, K_BASELINE,
      """The Chapter 3 ladder runs seven conditions: no memory, lexical, dense,
      hybrid, hybrid reranked, oracle, and full history. Conventional retrieval
      handles ordinary semantic recall well on the controlled corpus, which is
      why later chapters must show a failure class rather than a general
      improvement. The chapter also records that source recall and source
      precision are measured at different pipeline stages across conditions and
      must not be compared naively.""",
      ("content/books/memory/03-chapter.md",), "2026-09-19",
      claim_key="baseline.ch3-strength"),
    U("mb-ch03-admission-note", MEMORY_BOOK, K_BASELINE,
      """Chapter 3 separated candidate retrieval from context admission:
      retrieval proposes, admission disposes. Perfect candidate recall can
      still yield an explanation that lacks its evidence, when overlapping
      extracts occupy the admission slots. The repair belongs to admission,
      deduplication or ranking, not to a new persistent representation.""",
      ("content/books/memory/03-chapter.md",), "2026-09-19",
      claim_key="baseline.admission-vs-retrieval"),
]

# --------------------------------------------------------------------------
# memory-book: measured results from committed runs
# --------------------------------------------------------------------------

_RESULTS = [
    U("mb-ch08-result", MEMORY_BOOK, K_RESULT,
      """Chapter 8 frozen run: historical state accuracy is 0.0 for the bag,
      arrival-order and event-time conditions and 1.0 for the ordered and
      temporal conditions, while current-state accuracy is 1.0 everywhere.
      Ordering earns its place on historical questions only; recency is
      retained for clean current-state queries. Temporal role accuracy, late
      arrival robustness and projection rebuild equivalence are all 1.0.""",
      ("experiments/benchmark/runs/ch8-20260919T234350Z-temporal/metrics.json",),
      "2026-09-19", claim_key="result.ch8"),
    U("mb-ch09-result", MEMORY_BOOK, K_RESULT,
      """Chapter 9 frozen run: the mention baseline reaches open-loop precision
      0.8 and recall 0.8, while expected-transition resolution reaches
      canonical status accuracy 1.0 with a false-closed rate of 0.0.
      Cross-artifact closure and side-effect completion accuracy are both 1.0,
      and search-footprint coverage is 1.0. The two mention errors point in
      opposite directions: a never-accepted remark is flagged open, and an
      obligation phrased as an issue is missed.""",
      ("experiments/benchmark/runs/ch9-20260920T000629Z-open-loops/metrics.json",),
      "2026-09-20", claim_key="result.ch9"),
    U("mb-ch07-result", MEMORY_BOOK, K_RESULT,
      """Chapter 7 established that restatement must not be counted as
      corroboration. The lineage layer distinguishes SUPPORTED_BY from
      DERIVED_FROM and marks ECHO_OF explicitly, so a claim repeated in five
      documents does not acquire five independent supports. Retrieval and
      control traces are stored as node attributes, never as support edges.""",
      ("content/books/memory/07-chapter.md",
       "experiments/benchmark/runs/ch7-20260919-e7"), "2026-09-19",
      claim_key="result.ch7"),
    U("mb-ch06-result", MEMORY_BOOK, K_RESULT,
      """The Chapter 6 Nexus earned a governance role rather than a quality
      role: routing across memory mechanisms did not by itself improve answers,
      but it made the choice of mechanism explicit and auditable. That outcome
      is the book's precedent for accepting a mechanism on control grounds when
      the quality delta is absent.""",
      ("content/books/memory/06-chapter.md",
       "experiments/benchmark/runs/ch6-20260919-nexus"), "2026-09-19",
      claim_key="result.ch6"),
    U("mb-ch04-result", MEMORY_BOOK, K_RESULT,
      """Chapter 4 compared graph memory against the matched reader and found
      that a persistent derived graph pays for itself on questions requiring
      accumulated interpretation, not on ordinary lookup. The graph never
      became the only route to history; fallback to raw evidence stayed
      available.""",
      ("content/books/memory/04-chapter.md",
       "experiments/benchmark/runs/ch4-20260919T205622Z"), "2026-09-19",
      claim_key="result.ch4"),
]

# --------------------------------------------------------------------------
# memory-book: Chapter 10 as it currently stands, plus neighbours
# --------------------------------------------------------------------------

_CHAPTER_TEN = [
    U("mb-ch10-prose-opening", MEMORY_BOOK, K_PROSE,
      """Chapter 10, Intentions Are Not Events. Chapter 9 gave unfinished work
      a status but left the object the status attaches to unexamined. The
      chapter argues that an intention is not an event with a missing outcome:
      it is a record with a different temporal structure, and ordinary event
      extraction destroys the direction of fit that makes it one. It builds the
      representation from contrasts: intention versus suggestion, versus
      decision, versus consequence, explicit versus inferred.""",
      ("content/books/memory/10-chapter.md",), "2026-09-14",
      claim_key="ch10.current-content"),
    U("mb-ch10-prose-schema", MEMORY_BOOK, K_PROSE,
      """The Chapter 10 intention record: subject, desired state, optional
      owner, created_at, status drawn from opened, completed, cancelled,
      superseded and unresolved, evidence spans for the opening and each
      transition, and deadline and dependencies recorded only when the history
      states them. Owner is optional because real history frequently binds
      nobody; inferred deadlines would manufacture urgency the team never
      set.""",
      ("content/books/memory/10-chapter.md",), "2026-09-14",
      claim_key="ch10.current-content"),
    U("mb-ch10-priority-refusal", MEMORY_BOOK, K_PROSE,
      """What the Chapter 10 schema refuses is deliberate: no priority field,
      because importance belongs to retrieval policy rather than to the stored
      record, and baking it in would confuse stored state with situational
      need. The chapter defers that policy question to later chapters instead
      of settling it.""",
      ("content/books/memory/10-chapter.md",), "2026-09-14",
      claim_key="ch10.priority-belongs-to-policy"),
    U("mb-ch10-experiment-pending", MEMORY_BOOK, K_PROSE,
      """Chapter 10 carries an experiment-pending marker rather than a result.
      The intention fixtures and status scorer are described as an extension of
      E-09, scored on commitment correctness and transition accuracy, with no
      committed run behind them. The chapter's central comparison, intention
      aware tracking against the mention baseline, has not been executed.""",
      ("content/books/memory/10-chapter.md",), "2026-09-14",
      claim_key="ch10.no-result", open_loop="loop-ch10-experiment"),
    U("mb-ch10-refs", MEMORY_BOOK, K_CITATION,
      """Chapter 10 references: Generative Agents, Interactive Simulacra of
      Human Behavior (2023); Voyager, An Open-Ended Embodied Agent with Large
      Language Models (2023); MemGPT, Towards LLMs as Operating Systems (2023).
      Each is cited for forward-directed state in agent architectures and each
      was verified against its arXiv landing page before entry.""",
      ("content/books/memory/10-chapter.md", "research/bibliography.yaml"),
      "2026-09-14", claim_key="ch10.references"),
    U("mb-ch10-concepts", MEMORY_BOOK, K_CONCEPTS,
      """Chapter 10 concept notes: direction of fit distinguishes report from
      demand; retroactive commitment means some intentions become binding only
      when later history treats them so; prospective memory supplies the
      event-, time- and activity-based trigger taxonomy. The notes flag that
      task-memory vocabulary is withheld until an experiment earns it.""",
      ("content/books/memory/10-concepts.txt",), "2026-09-14",
      claim_key="ch10.concepts"),
    U("mb-ch09-handoff", MEMORY_BOOK, K_PROSE,
      """Chapter 9 closes by handing the reader to Chapter 10: unfinished work
      now has a status, but the object the status attaches to has not been
      examined. The handoff sentence and the Chapter 10 opening must agree, and
      the continuity guard checks that retired running-example identifiers do
      not reappear in either.""",
      ("content/books/memory/09-chapter.md",), "2026-09-20",
      claim_key="ch10.continuity"),
    U("mb-ch11-opening", MEMORY_BOOK, K_PROSE,
      """Chapter 11, Open Loops, currently opens by saying that Chapters 9 and
      10 handle work the history states, then pushes past stated tasks to
      consequences nobody wrote down. Any change to Chapter 10's subject
      requires this opening sentence to be rewritten, or the recap will claim a
      chapter that no longer exists.""",
      ("content/books/memory/11-chapter.md",), "2026-09-14",
      claim_key="ch10.continuity"),
]

# --------------------------------------------------------------------------
# memory-book: style, build, publication mechanics
# --------------------------------------------------------------------------

_STYLE = [
    U("mb-style-conventions", MEMORY_BOOK, K_STYLE,
      """Prose conventions: British spelling; summarise papers in the book's
      own words with no quotation over fifteen words; no author-directed
      imperatives left in the text, written as method statements instead; no
      references to prompts; keep the six-question spine visible.""",
      ("AGENTS.md",), "2026-09-15", claim_key="style.prose"),
    U("mb-style-frontmatter", MEMORY_BOOK, K_STYLE,
      """Every chapter file carries TOML front matter with title, date,
      description, weight, draft flag, series, categories and tags. Weight
      fixes the reading order, and the description is the one-line summary used
      by the section index. Reader-facing material lives only under content/;
      research, planning, spec and experiments stay outside it.""",
      ("AGENTS.md", "hugo.toml"), "2026-09-15", claim_key="style.frontmatter"),
    U("mb-style-build", MEMORY_BOOK, K_STYLE,
      """The build gate is hugo --minify --panicOnWarning, which must pass
      before any pull request. A broken internal link, a malformed shortcode or
      a missing front-matter field fails the build rather than degrading the
      published page.""",
      ("AGENTS.md",), "2026-09-15", claim_key="style.build"),
    U("mb-style-citations", MEMORY_BOOK, K_STYLE,
      """Every cited work is verified against its landing page for title,
      authors, year and venue before it enters a chapter, and recorded in
      research/bibliography.yaml with a status of peer-reviewed, preprint,
      vendor-reported or documentation. Vendor-reported benchmark numbers are
      labelled as such wherever they appear.""",
      ("AGENTS.md", "research/bibliography.yaml"), "2026-09-15",
      claim_key="style.citations"),
]

# --------------------------------------------------------------------------
# memory-book: research notes (topically close, goal-dependent value)
# --------------------------------------------------------------------------

_RESEARCH = [
    U("mb-research-prospective", MEMORY_BOOK, K_RESEARCH,
      """Prospective memory research supplies the retrospective/prospective cut
      and the event-, time- and activity-based trigger taxonomy, with intention
      deactivation work motivating standing re-verification. The notes were
      gathered for the intention chapter and bear on how a stated obligation is
      represented, not on how evidence is selected for a task.""",
      ("planning/chapter-09-open-loops-research.md",), "2026-09-18",
      claim_key="research.prospective-memory"),
    U("mb-research-intention-schema", MEMORY_BOOK, K_RESEARCH,
      """Draft intention schema notes: modality extraction, commitment
      evidence, hedged speculation versus binding obligation, owner
      assignment, and the retroactivity problem where commitment is
      established by later behaviour. Extensive and specific to the intention
      representation question.""",
      ("planning/chapter-09-open-loops-research.md",), "2026-09-18",
      claim_key="research.intention-schema"),
    U("mb-research-deontic", MEMORY_BOOK, K_RESEARCH,
      """Deontic logic is recorded as noted and deferred beyond the
      active-obligation fragment. The bibliography entry exists; no chapter
      currently depends on it.""",
      ("research/bibliography.yaml",), "2026-09-18",
      claim_key="research.deontic"),
    U("mb-research-context-engineering", MEMORY_BOOK, K_RESEARCH,
      """Context engineering notes: the context window is treated as a finite
      attention budget to be curated rather than filled, with just-in-time
      retrieval, compaction and structured memory as the recommended moves.
      The recommended compaction strategy maximises recall first and improves
      precision afterwards, because detail discarded early may matter later.""",
      ("planning/measurement-research-matrix.md",), "2026-09-19",
      claim_key="research.context-engineering"),
    U("mb-research-goal-conditioned", MEMORY_BOOK, K_RESEARCH,
      """Recent memory-selection work argues that semantic similarity is the
      wrong admission criterion on its own: intent-driven selection reranks
      retrieved memory by task benefit, and trustworthy-memory work treats a
      semantically related but contextually inappropriate memory as a control
      hazard rather than a ranking error.""",
      ("planning/measurement-research-matrix.md",), "2026-09-20",
      claim_key="research.goal-conditioned"),
]

# --------------------------------------------------------------------------
# memory-book: implementation detail (relevant to few work types)
# --------------------------------------------------------------------------

_IMPL = [
    U("mb-impl-zeromq", MEMORY_BOOK, K_IMPL,
      """The Chapter 8 transport uses ZeroMQ PUSH/PULL with an append-only
      log behind it. ZeroMQ is transport, never the store: the log is
      canonical and projections rebuild from it. The demo binds an inproc
      socket, replays the frozen event file and asserts the rebuilt projection
      digest matches.""",
      ("solution/temporal_memory/transport.py",), "2026-09-19",
      claim_key="impl.zeromq"),
    U("mb-impl-graphrag", MEMORY_BOOK, K_IMPL,
      """Chapter 4 indexing runs graphrag 3.1.2 inside solution/.venv, with
      Basic, Local, Global and DRIFT query modes exercised through the chapter
      runner rather than through unit tests. Index builds require Ollama for
      extraction and take minutes, not seconds.""",
      ("solution/graph_memory",), "2026-09-19", claim_key="impl.graphrag"),
    U("mb-impl-postgres", MEMORY_BOOK, K_IMPL,
      """The baseline store runs PostgreSQL with pgvector on port 5434 via
      docker compose, with an HNSW index and a tsvector column for full-text
      search. Lexical search uses OR-of-terms with ts_rank_cd ordering because
      plain AND matching retrieves nothing for ordinary question phrasing.""",
      ("solution/memory_baseline/storage.py",), "2026-09-19",
      claim_key="impl.store-backend"),
    U("mb-impl-test-paths", MEMORY_BOOK, K_IMPL,
      """Default pytest paths cover the per-package suites plus the continuity
      guard. Unit tests need no services; live integration against PostgreSQL,
      Ollama and GraphRAG is exercised only through the chapter runners.""",
      ("solution/pyproject.toml", "solution/README.md"), "2026-09-20",
      claim_key="impl.tests"),
]

# --------------------------------------------------------------------------
# memory-book: open loops and release readiness
# --------------------------------------------------------------------------

_OPEN_LOOPS = [
    U("mb-loop-ch10-experiment", MEMORY_BOOK, K_OPEN_LOOP,
      """Open: Chapter 10 carries an experiment-pending marker and no committed
      run. Until an E-10 run exists, the chapter states a hypothesis the book's
      own evidence discipline forbids presenting as a result.""",
      ("content/books/memory/10-chapter.md",), "2026-09-14",
      claim_key="loop.ch10-experiment", open_loop="loop-ch10-experiment"),
    U("mb-loop-readme-drift", MEMORY_BOOK, K_OPEN_LOOP,
      """Open: solution/README.md says six layers while listing seven, and says
      the default test paths cover five packages while more are configured. A
      documentation drift, small but load-bearing for a reader following the
      dependency order.""",
      ("solution/README.md",), "2026-09-20", claim_key="loop.readme-drift",
      open_loop="loop-readme-drift"),
    U("mb-loop-real-corpus", MEMORY_BOOK, K_OPEN_LOOP,
      """Open: the benchmark contract requires a real-project corpus alongside
      the controlled one, with a manually adjudicated query set that preserves
      disagreement. Chapters 4 to 9 have been validated on the controlled
      corpus only.""",
      ("spec/benchmark-v0.1.md",), "2026-09-19", claim_key="loop.real-corpus",
      open_loop="loop-real-corpus"),
    U("mb-loop-ch11-recap", MEMORY_BOOK, K_OPEN_LOOP,
      """Open: Chapter 11's opening recap names Chapters 9 and 10 as the
      stated-work chapters. If Chapter 10 changes subject the recap becomes
      false, and the continuity guard does not check recap claims.""",
      ("content/books/memory/11-chapter.md",), "2026-09-20",
      claim_key="loop.ch11-recap", open_loop="loop-ch11-recap"),
]

# --------------------------------------------------------------------------
# memory-book: superseded state (Chapter 8 material, deliberately stale)
# --------------------------------------------------------------------------

_STALE = [
    U("mb-stale-ch06-title", MEMORY_BOOK, K_ARCH,
      """Chapter 6 is titled Similarity Is Not Memory and argues that embedding
      proximity cannot distinguish a decision from a discussion of it. The
      chapter's durable ideas are the materiality standard and the
      similarity/identity distinction.""",
      ("planning/book-architecture.md",), "2026-06-01",
      valid_until="2026-09-19", superseded_by="mb-arch-layers",
      claim_key="arch.ch6-title"),
    U("mb-stale-ch10-plan", MEMORY_BOOK, K_PLANNING,
      """Plan of record: Chapter 10 is Intentions Are Not Events and Chapter 11
      is Open Loops; the intention record is the next mechanism to implement,
      with prospective-memory research as its foundation and an E-10 status
      scorer extending E-09.""",
      ("planning/book-architecture.md",), "2026-09-14",
      valid_until="2026-09-20", superseded_by="mb-arch-q6-open",
      claim_key="arch.next-mechanism"),
    U("mb-stale-nexus-selects", MEMORY_BOOK, K_PLANNING,
      """Working assumption: the Memory Nexus will select the final context for
      every query, routing between graph, associative and baseline retrieval
      and returning the assembled context directly.""",
      ("planning/chapter-06-memory-nexus-research.md",), "2026-08-20",
      valid_until="2026-09-19", superseded_by="mb-ch06-result",
      claim_key="arch.nexus-role"),
    U("mb-stale-sqlite", MEMORY_BOOK, K_IMPL,
      """The companion implementation stores chunks and embeddings in SQLite so
      the baseline can run without a database service. Vector search is a brute
      force scan over the chunk table.""",
      ("solution/memory_baseline/storage.py",), "2026-07-01",
      valid_until="2026-08-01", superseded_by="mb-impl-postgres",
      claim_key="impl.store-backend"),
]

# --------------------------------------------------------------------------
# memory-book: echoes (Chapter 7 restatement, not corroboration)
# --------------------------------------------------------------------------

_ECHOES = [
    U("mb-echo-baseline-1", MEMORY_BOOK, K_PLANNING,
      """Reminder from the planning notes: new mechanisms are measured against
      the Chapter 3 strong retrieval baseline at a matched context budget.""",
      ("planning/chapter-04-graphrag-research.md",), "2026-09-16",
      evidence_role="echo", echo_of="mb-method-earn",
      claim_key="method.earn-complexity"),
    U("mb-echo-baseline-2", MEMORY_BOOK, K_PLANNING,
      """As established earlier, every layer must beat strong RAG on its own
      failure class before it enters the book.""",
      ("planning/chapter-05-associative-memory-research.md",), "2026-09-17",
      evidence_role="echo", echo_of="mb-method-earn",
      claim_key="method.earn-complexity"),
    U("mb-echo-baseline-3", MEMORY_BOOK, K_SESSION,
      """Session note: restating the rule that mechanisms earn their complexity
      experimentally against the Chapter 3 baseline.""",
      ("planning/continuity-audit.md",), "2026-09-18",
      evidence_role="echo", echo_of="mb-method-earn",
      claim_key="method.earn-complexity"),
    U("mb-echo-baseline-4", MEMORY_BOOK, K_SESSION,
      """Repeated in review: the baseline comparison is the acceptance test for
      any new memory layer.""",
      ("planning/continuity-audit.md",), "2026-09-19",
      evidence_role="echo", echo_of="mb-method-earn",
      claim_key="method.earn-complexity"),
    U("mb-echo-ch9-result-1", MEMORY_BOOK, K_SESSION,
      """Noted again: the Chapter 9 mention baseline reached precision 0.8 and
      recall 0.8 on the canonical texts.""",
      ("planning/continuity-audit.md",), "2026-09-20",
      evidence_role="echo", echo_of="mb-ch09-result",
      claim_key="result.ch9"),
    U("mb-refutes-ch9-scope", MEMORY_BOOK, K_RESULT,
      """Dissenting note retained: the Chapter 9 status accuracy of 1.0 holds
      on fixture-level cases with oracle-labelled expectations, so it does not
      establish that expectation extraction from raw history would reach the
      same accuracy. The verdict is fixture-level, and the chapter says so.""",
      ("experiments/benchmark/runs/ch9-20260920T000629Z-open-loops/results.json",),
      "2026-09-20", evidence_role="refutes", claim_key="result.ch9"),
]

# --------------------------------------------------------------------------
# memory-book: recent conversation (recency versus current purpose)
# --------------------------------------------------------------------------

_SESSIONS = [
    U("mb-session-intent-1", MEMORY_BOOK, K_SESSION,
      """Recent working session: extended discussion of intention extraction,
      modality parsing, and how to separate a hedged suggestion from a binding
      commitment. Several candidate field lists for the intention record were
      compared.""",
      ("planning/chapter-09-open-loops-research.md",), "2026-09-19",
      claim_key="session.intentions"),
    U("mb-session-intent-2", MEMORY_BOOK, K_SESSION,
      """Recent working session continued: owner assignment, deadline
      quarantine, and whether a retroactively established commitment should
      carry two timestamps. Consensus was that the record keeps both the
      utterance time and the commitment-established time.""",
      ("planning/chapter-09-open-loops-research.md",), "2026-09-19",
      claim_key="session.intentions"),
    U("mb-session-intent-3", MEMORY_BOOK, K_SESSION,
      """Recent working session continued: a draft E-10 fixture grid across
      suggestion, intention, decision and consequence, with retroactive
      commitment cases scored separately.""",
      ("planning/chapter-09-open-loops-research.md",), "2026-09-19",
      claim_key="session.intentions"),
    U("mb-session-pivot", MEMORY_BOOK, K_SESSION,
      """Latest working session: the direction is questioned. The stated
      concern is that the book may have drifted from measurable improvement
      over retrieval, and the request is to return to the Chapter 3 baseline
      and ask what the next mechanism actually improves.""",
      ("planning/book-architecture.md",), "2026-09-20",
      claim_key="session.pivot"),
]

# --------------------------------------------------------------------------
# writer: a neighbouring project with the same vocabulary
# --------------------------------------------------------------------------

_WRITER = [
    U("wr-context-runtime", WRITER, K_IMPL,
      """Writer's context runtime assembles a request from candidates under a
      budget and emits a bundle with a trace. The vocabulary is deliberately
      similar to the memory programme's: requests, candidates, budgets,
      policies, bundles and traces all appear in the module names.""",
      ("writer/context/runtime.py",), "2026-08-10",
      claim_key="writer.context-runtime"),
    U("wr-memory-store", WRITER, K_IMPL,
      """Writer keeps a per-document memory store of prior drafts, editorial
      notes and style decisions, retrieved by embedding similarity when a new
      section is drafted.""",
      ("writer/memory/store.py",), "2026-08-12", claim_key="writer.memory"),
    U("wr-evidence-policy", WRITER, K_METHOD,
      """Writer's policy requires that every generated claim keep a pointer to
      the source passage it came from, and that contradictory sources be
      surfaced rather than reconciled silently.""",
      ("writer/docs/policy.md",), "2026-08-15", claim_key="writer.evidence"),
    U("wr-retrieval-eval", WRITER, K_RESULT,
      """Writer's retrieval evaluation measures context precision and recall
      against a hand-labelled set of source passages per section, with a
      separate token-cost column. The harness reports per-section results
      before any aggregate.""",
      ("writer/eval/retrieval.md",), "2026-08-20", claim_key="writer.eval"),
    U("wr-improve-context", WRITER, K_PLANNING,
      """Planned improvement to Writer's context system: cache embeddings per
      document version, raise the candidate pool, and add a redundancy penalty
      so near-duplicate draft fragments stop occupying the budget.""",
      ("writer/docs/roadmap.md",), "2026-09-01", claim_key="writer.roadmap"),
    U("wr-rag-baseline", WRITER, K_BASELINE,
      """Writer's retrieval baseline is hybrid lexical and dense search with
      reciprocal rank fusion over document chunks, reranked by a cross-encoder,
      then truncated to the section budget.""",
      ("writer/context/retrieval.py",), "2026-08-05",
      claim_key="writer.baseline"),
]

# --------------------------------------------------------------------------
# cocoder: a second neighbouring project
# --------------------------------------------------------------------------

_COCODER = [
    U("cc-context-window", COCODER, K_IMPL,
      """CoCoder builds the model's context from the open file, the symbols it
      references, recent diffs and the failing test output, under a fixed token
      budget. Selection is by static reference graph first and embedding
      similarity second.""",
      ("cocoder/context/build.py",), "2026-07-20", claim_key="cocoder.context"),
    U("cc-memory-notes", COCODER, K_IMPL,
      """CoCoder stores per-repository memory notes: conventions, build
      commands, and corrections the user has made before, retrieved whenever a
      new task starts in that repository.""",
      ("cocoder/memory/notes.py",), "2026-07-22", claim_key="cocoder.memory"),
    U("cc-improve-context", COCODER, K_PLANNING,
      """Planned improvement to CoCoder's context system: drop whole-file
      inclusion in favour of symbol slices, and measure whether the freed
      budget improves patch acceptance.""",
      ("cocoder/docs/roadmap.md",), "2026-09-02", claim_key="cocoder.roadmap"),
    U("cc-eval-harness", COCODER, K_RESULT,
      """CoCoder's evaluation harness measures patch acceptance rate, test-pass
      rate and token cost per task, with a distraction column counting admitted
      context that no accepted patch referenced.""",
      ("cocoder/eval/harness.md",), "2026-07-28", claim_key="cocoder.eval"),
    U("cc-evidence-refs", COCODER, K_METHOD,
      """CoCoder requires that every suggested edit name the files and symbols
      that justified it, so a wrong suggestion can be traced to the context
      that produced it rather than to the model alone.""",
      ("cocoder/docs/policy.md",), "2026-07-25", claim_key="cocoder.evidence"),
]

ALL_UNITS: tuple[MemoryUnit, ...] = tuple(
    _METHOD + _MEASUREMENT + _RESULTS + _CHAPTER_TEN + _STYLE + _RESEARCH
    + _IMPL + _OPEN_LOOPS + _STALE + _ECHOES + _SESSIONS + _WRITER + _COCODER
)


def corpus() -> list[MemoryUnit]:
    return list(ALL_UNITS)


def by_id() -> dict[str, MemoryUnit]:
    return {u.unit_id: u for u in ALL_UNITS}


def corpus_digest() -> str:
    import hashlib
    import json
    payload = json.dumps([u.to_dict() for u in ALL_UNITS], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
