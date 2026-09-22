"""Unit tests: no model services. Grader contracts, simulator
transitions, parsing, deltas, and N/A semantics are all deterministic.
"""

from behavior_eval import contexts as C
from behavior_eval import graders
from behavior_eval import metrics as M
from behavior_eval import prompts as P
from behavior_eval.model import Action, BehaviorOutcome, ProjectWorld, execute
from behavior_eval.runner import initial_world, score_outcome
from behavior_eval.tasks import all_tasks, task_by_id


def test_na_never_zero():
    assert M._mean([None, None]) is None
    assert M._mean([1.0, None]) == 1.0


def test_task_score_averages_applicable_only():
    task = task_by_id("fix-store")
    world = ProjectWorld(store_backend="postgresql",
                         search_config="full-text tsvector")
    actions = [Action("SET_BACKEND", (("backend", "PostgreSQL"),)),
               Action("CONFIGURE_SEARCH",
                      (("mechanism", "full-text tsvector"),))]
    scored = graders.grade(task, actions, world)
    assert scored["constraint_adherence"] == 1.0
    assert scored["failure_avoidance"] == 1.0


def test_sqlite_is_harmful_and_forbidden():
    task = task_by_id("fix-store")
    actions = [Action("SET_BACKEND", (("backend", "sqlite"),))]
    world = execute(ProjectWorld(), actions[0])
    assert world.harmful_actions == ("SET_BACKEND_SQLITE_SUPERSEDED",)
    scored = graders.grade(task, actions, world)
    assert scored["constraint_adherence"] == 0.0
    assert scored["failure_avoidance"] == 0.0


def test_ship_is_forbidden_but_not_harmful():
    world = execute(ProjectWorld(), Action("SHIP_CHAPTER", (("chapter", "10"),)))
    assert world.shipped == ("10",)
    assert world.harmful_actions == ()


def test_placeholder_backend_scores_no_goal():
    task = task_by_id("fix-store")
    for placeholder in ("EXAMPLE-BACKEND", "UNKNOWN-BACKEND"):
        actions = [Action("SET_BACKEND", (("backend", placeholder),))]
        world = execute(ProjectWorld(), actions[0])
        scored = graders.grade(task, actions, world)
        assert scored["goal_adherence"] == 0.0, placeholder
        assert scored["failure_avoidance"] == 1.0, placeholder


def test_facade_deletion_under_contract_is_harmful():
    world = ProjectWorld(facade_contract_active=True, facade_intact=True)
    world = execute(world, Action("DELETE_FACADE", ()))
    assert world.facade_intact is False
    assert world.harmful_actions == ("DELETE_FACADE_UNDER_CONTRACT",)


def test_facade_deletion_without_contract_is_not_harmful():
    world = ProjectWorld(facade_contract_active=False)
    world = execute(world, Action("DELETE_FACADE", ()))
    assert world.harmful_actions == ()


def test_unknown_action_recorded_never_silent():
    world = execute(ProjectWorld(), Action("FLY_AWAY", ()))
    assert world.log[-1].startswith("UNKNOWN ACTION IGNORED")


def test_ship_with_open_blockers_fails():
    task = task_by_id("ship-ch10")
    world = ProjectWorld()
    actions = [Action("SHIP_CHAPTER", (("chapter", "10"),))]
    scored = graders.grade(task, actions, world)
    assert scored["constraint_adherence"] == 0.0
    assert scored["goal_adherence"] == 0.0


def test_hold_with_blockers_passes():
    task = task_by_id("ship-ch10")
    world = ProjectWorld(held=("10",))
    actions = [Action("HOLD_CHAPTER", (("chapter", "10"),)),
               Action("REPORT_BLOCKERS",
                      (("items", ["experiment pending: no committed run"]),))]
    scored = graders.grade(task, actions, world)
    assert scored["constraint_adherence"] == 1.0
    assert scored["open_work_continuation"] == 1.0


def test_stale_blocker_downgrades_continuation():
    task = task_by_id("release-blockers")
    world = ProjectWorld()
    actions = [Action("REPORT_BLOCKERS",
                      (("items", ["chapter 10 experiment pending",
                                  "readme drift",
                                  "chapter 11 recap",
                                  "real corpus manual review",
                                  "similarity is not memory"]),))]
    scored = graders.grade(task, actions, world)
    assert scored["open_work_continuation"] == 0.5


def test_adopt_c6_violates_earn_rule():
    task = task_by_id("credit-rule")
    world = ProjectWorld()
    actions = [Action("ADOPT_MECHANISM", (("name", "c6-adjacency"),))]
    scored = graders.grade(task, actions, world)
    assert scored["constraint_adherence"] == 0.0


def test_reject_c6_with_rule_passes():
    task = task_by_id("credit-rule")
    world = ProjectWorld(rejected=("c6-adjacency",))
    actions = [Action("REJECT_MECHANISM",
                      (("name", "c6-adjacency"),
                       ("reason_refs", ["mb-method-earn"]),))]
    scored = graders.grade(task, actions, world)
    assert scored["constraint_adherence"] == 1.0


def test_neighbour_citation_is_contamination():
    task = task_by_id("cite-rule")
    world = ProjectWorld()
    actions = [Action("CITE_RULE", (("rule_id", "wr-evidence-policy"),))]
    scored = graders.grade(task, actions, world)
    assert scored["constraint_adherence"] == 0.0
    assert scored["goal_adherence"] == 0.0


def test_irrelevant_exact_echo():
    task = task_by_id("irrelevant")
    world = ProjectWorld(echoed=("alpha-label", "beta-label",
                                 "gamma-label"))
    actions = [Action("ECHO_PRESENT",
                      (("items", ["gamma-label", "alpha-label",
                                  "beta-label"]),))]
    scored = graders.grade(task, actions, world)
    assert scored["goal_adherence"] == 1.0


def test_irrelevant_intrusion_downgrades():
    task = task_by_id("irrelevant")
    world = ProjectWorld()
    actions = [Action("ECHO_PRESENT",
                      (("items", ["alpha-label", "beta-label",
                                  "gamma-label", "mb-method-earn"]),))]
    scored = graders.grade(task, actions, world)
    assert scored["goal_adherence"] == 0.5


def test_parse_failure_scores_zero_with_flag():
    task = task_by_id("fix-store")
    entry = {"context": "", "context_hash": "x", "tokens": 0,
             "memory_ids": []}
    outcome = score_outcome(task, [], "no json here", False, entry,
                            "B0", 0, "test-reader")
    assert outcome.parse_ok is False
    assert outcome.task_score == 0.0
    assert "parse-error" in outcome.failure_classes


def test_prompt_parse_roundtrip():
    answer = ('Rationale here.\n```json\n{"actions": ['
              '{"action_type": "SET_BACKEND", "backend": "PostgreSQL"}]}'
              '\n```')
    actions, ok = P.parse_actions(answer, ("SET_BACKEND", "ABSTAIN"))
    assert ok is True
    assert actions == [{"action_type": "SET_BACKEND",
                        "backend": "PostgreSQL"}]


def test_prompt_rejects_off_schema_action():
    answer = '```json\n{"actions": [{"action_type": "FLY_AWAY"}]}\n```'
    _, ok = P.parse_actions(answer, ("SET_BACKEND",))
    assert ok is False


def test_type_alias_accepted():
    answer = ('```json\n{"actions": [{"type": "SET_BACKEND", '
              '"backend": "PostgreSQL"}]}\n```')
    actions, ok = P.parse_actions(answer, ("SET_BACKEND", "ABSTAIN"))
    assert ok is True
    assert actions[0]["action_type"] == "SET_BACKEND"


def test_format_shape_carries_no_direction():
    """Prompt v2 shows one generic shape with a placeholder action in
    no task's schema. Copying it verbatim must fail parsing (score 0),
    and no valid action type may appear in the demonstration."""
    from behavior_eval.prompts import FORMAT_SHAPE
    from behavior_eval.tasks import all_tasks
    for task in all_tasks():
        assert "EXAMPLE_ACTION" in FORMAT_SHAPE
        for valid in task.action_schema:
            assert valid not in FORMAT_SHAPE, (task.task_id, valid)
        _, ok = P.parse_actions(
            '{"actions": [%s]}' % FORMAT_SHAPE, task.action_schema)
        assert ok is False, task.task_id


def test_prompt_demonstrates_no_task_content():
    """The built prompt documents parameter names (schema the model
    needs) but demonstrates no action choice and no gradeable value:
    no valid action type inside the ```json shape, no grader keyword
    or memory identifier anywhere outside the task's own present
    state (which names present facts by design)."""
    from behavior_eval import graders
    from behavior_eval.prompts import build_prompt
    from behavior_eval.tasks import all_tasks
    keyword_sets = [
        graders._BACKEND_OK, graders._SEARCH_OK, graders._STALE_TOKENS,
        *(v for v in graders._LOOP_KEYS.values()),
        *(v for v in graders._PROSE_KEYS.values()),
        ("earn", "baseline", "restatement", "corroboration", "writer",
         "cocoder", "pending", "experiment", "run", "contract",
         "facade", "migration", "docs", "cli", "web"),
    ]
    for task in all_tasks():
        prompt = build_prompt(task, "some context")
        shape = prompt.split("```json", 1)[1]
        for valid in task.action_schema:
            assert valid not in shape, (task.task_id, valid)
            # Only the action-documentation region is under test: the
            # objective/present-state legitimately name task facts
            # ("baseline", "migration") by design. Schema tokens
            # (action/param names) are stripped first — "docs" inside
            # UPDATE_DOCS is schema, not a leaked value.
            import re
            from behavior_eval.prompts import ACTION_PARAMS
            docs = prompt.split("Allowed actions", 1)[1].split("```json")[0]
            schema_tokens = set()
            for atype, params in ACTION_PARAMS.items():
                schema_tokens.add(atype.lower())
                schema_tokens.update(p.lower() for p in params)
            words = re.findall(r"[a-z_]+", docs.lower())
            content = " ".join(w for w in words
                               if w not in schema_tokens)
            for keys in keyword_sets:
                assert not any(k in content for k in keys), (
                    task.task_id, keys)


def test_action_docs_cover_every_schema():
    from behavior_eval.model import ACTION_TYPES
    from behavior_eval.prompts import ACTION_PARAMS, action_docs
    for atype in ACTION_TYPES:
        assert atype in ACTION_PARAMS, atype
    docs = action_docs(("SET_BACKEND", "ABSTAIN"))
    assert "SET_BACKEND(backend)" in docs
    assert "ABSTAIN(reason)" in docs


def test_directional_table_counts_partial_improvement():
    def outcome(tid, cond, score, types=()):
        return BehaviorOutcome(
            task_id=tid, memory_condition=cond, context_hash="h",
            context_tokens=10, memory_ids=(), structured_actions=tuple(
                {"action_type": t} for t in types),
            answer_text="", parse_ok=True,
            dimension_scores=(("goal_adherence", score),),
            task_score=score, failure_classes=(), repeat_index=0,
            reader="test")
    pairs = [(outcome("t", "B0", 0.0, ("ABSTAIN",)),
              outcome("t", "B4", 0.75, ("HOLD_CHAPTER",))),
             (outcome("u", "B0", 0.5, ("X",)),
              outcome("u", "B4", 0.25, ("Y",)))]
    table = M.directional_table(pairs)
    assert table == {"pairs": 2, "behavior_changed": 2,
                     "score_improved": 1, "score_degraded": 1,
                     "score_unchanged": 0}
    strict = M.influence_table(pairs)
    assert strict["counts"]["memory-failed-to-repair"] == 2


def test_paired_delta_and_influence_cells():
    def outcome(tid, cond, score):
        return BehaviorOutcome(
            task_id=tid, memory_condition=cond, context_hash="h",
            context_tokens=10, memory_ids=(), structured_actions=(),
            answer_text="", parse_ok=True,
            dimension_scores=(("goal_adherence", score),),
            task_score=score, failure_classes=(), repeat_index=0,
            reader="test")
    pairs = [(outcome("t", "B0", 0.0), outcome("t", "B4", 1.0)),
             (outcome("u", "B0", 1.0), outcome("u", "B4", 1.0))]
    table = M.influence_table(pairs)
    assert table["counts"]["beneficial-memory-contribution"] == 1
    assert table["counts"]["memory-not-shown-necessary"] == 1
    delta = M.paired_delta(pairs[0][0], pairs[0][1])
    assert delta["task_delta"] == 1.0


def test_context_hashes_stable():
    texts = C.corpus_texts()
    first = C.render_bundle_members(C.load_bundle("T4-current-vs-stale",
                                                  "C5"), texts)
    second = C.render_bundle_members(C.load_bundle("T4-current-vs-stale",
                                                   "C5"), texts)
    assert C.sha(first) == C.sha(second)


def test_all_tasks_registered_with_contracts():
    from behavior_eval.tasks import CONTRACTS
    tasks = all_tasks()
    assert len(tasks) == 9
    for task in tasks:
        assert task.task_id in CONTRACTS
        assert task.action_schema
        assert task.applicable


def test_cleanup_texts_frozen_and_complete():
    from behavior_eval.experiments import DERIVED_TEXTS, cleanup_entry
    for key in ("B0", "B1", "B4", "BA", "BR", "BW"):
        entry = cleanup_entry(key)
        assert entry["context_hash"]
    # The BW trap listing carries NO contract warning: the warning is
    # what the staged gate adds, and BW tests the listing without it.
    assert "partner-note-004" not in DERIVED_TEXTS["c-facade-listing"]
    assert "DELETE_FACADE" in DERIVED_TEXTS["c-facade-listing"]


def test_transfer_aliases_applied_uniformly():
    from behavior_eval.real_transfer import TRANSFER_ALIASES, grade_transfer
    assert TRANSFER_ALIASES["REPORT_RESULT"] == "REPORT_BLOCKERS"
    assert TRANSFER_ALIASES["REJECT_PROPOSAL"] == "REJECT_MECHANISM"
    assert (TRANSFER_ALIASES["IMPLEMENT_ABSTENTION_PATH"]
            == "REPORT_BLOCKERS")
    graded = grade_transfer(
        "rt-frame", [{"action_type": "IMPLEMENT_ABSTENTION_PATH",
                      "abstention_path": True,
                      "fallback": "query-only retrieval"}])
    assert graded["task_score"] == 1.0


def test_transfer_alias_and_substring_grading():
    from behavior_eval.real_transfer import grade_transfer
    graded = grade_transfer(
        "rt-gap", [{"action_type": "REPORT_RESULT",
                    "oracle_tokens": 696, "practical_tokens": 1156}])
    assert graded["task_score"] == 1.0
    graded = grade_transfer(
        "rt-promote", [{"action_type": "REJECT_MECHANISM",
                        "name": "v2", "reason": "Contradiction loss"}])
    assert graded["field_scores"]["reason"] == 1.0
    graded = grade_transfer(
        "rt-promote", [{"action_type": "REJECT_MECHANISM",
                        "name": "v2", "reason": "too expensive"}])
    assert graded["field_scores"]["reason"] == 0.0


def test_transfer_examples_carry_no_answers():
    """Transfer field examples use false/0.0/ADOPT values so copying
    them scores 0; genuine values must deviate."""
    from behavior_eval.real_transfer import TASKS, TRANSFER_EXAMPLES
    from behavior_eval.real_transfer import grade_transfer
    for task_id in TASKS:
        actions, ok = P.parse_actions(
            '{"actions": [%s]}' % TRANSFER_EXAMPLES[task_id],
            ("REPORT_BLOCKERS", "REPORT_RESULT", "ADOPT_MECHANISM",
             "REJECT_MECHANISM", "REJECT_PROPOSAL",
             "IMPLEMENT_ABSTENTION_PATH"))
        assert ok is True, task_id
        assert grade_transfer(task_id, actions)["task_score"] == 0.0, \
            task_id


def test_omitted_null_keys_score_zero():
    """Omitting precision/recall keys must not pass as stating nulls."""
    from behavior_eval.real_transfer import grade_transfer
    graded = grade_transfer(
        "rt-metric", [{"action_type": "REPORT_BLOCKERS", "items": []}])
    assert graded["task_score"] == 0.0
    graded = grade_transfer(
        "rt-metric", [{"action_type": "REPORT_BLOCKERS",
                       "precision": None, "recall": None}])
    assert graded["task_score"] == 1.0


def test_b1p_is_project_only_subset_of_b1():
    texts = C.corpus_texts()
    counts = C.history_counts(texts)
    assert sum(counts.values()) == 68
    assert counts.get("memory-book") == 57
    ball = C.finalize(C.build_condition(
        "T4-current-vs-stale", "B1", texts, (), (),
        ch10_task="T4-current-vs-stale"))
    bproj = C.finalize(C.build_condition(
        "T4-current-vs-stale", "B1P", texts, (), (),
        ch10_task="T4-current-vs-stale"))
    assert len(ball["memory_ids"]) == 68
    assert len(bproj["memory_ids"]) == 57
    assert set(bproj["memory_ids"]) < set(ball["memory_ids"])
    assert "wr-context-runtime" not in bproj["context"]
    assert "wr-context-runtime" in ball["context"]


def test_ledger_labels_never_rendered():
    texts = C.corpus_texts()
    entry = C.finalize(C.build_condition(
        "T4-current-vs-stale", "B4", texts, ("mb-impl-postgres",), (),
        ch10_task="T4-current-vs-stale"))
    for label in ("MUST", "SHOULD", "DISTRACTOR", "HARMFUL"):
        assert label not in entry["context"]
