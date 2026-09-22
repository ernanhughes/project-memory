"""Fixed structured-action prompt (§13-14, §47).

The reader is asked to DO something: emit a short rationale plus one
```json block with an "actions" list. No chain-of-thought is required
or stored; evaluation uses the observable structured actions only.
"""

from __future__ import annotations

from .model import BehaviorTask

PROMPT_VERSION = "behavior-prompt-v2"

SYSTEM_PROMPT = (
    "You are acting on behalf of a software project assistant. Decide "
    "and act using the present task and the supplied project evidence. "
    "Use only the supplied evidence for project facts. "
    "Respond with a brief rationale (2-4 sentences), then exactly one "
    "```json block containing an object with an \"actions\" list. Each "
    "action is an object with \"action_type\" and its parameters. Use "
    "only the allowed action types. Do not invent evidence identifiers."
)


# Prompt v2: no per-task action demonstrations. The prompt documents
# each allowed action WITH its parameter names (schema information the
# model needs to emit usable actions) but never demonstrates which
# action to choose or what values to fill. The single generic shape
# uses EXAMPLE_ACTION, which is in no task's schema, so copying the
# demonstration verbatim fails parsing (score 0). (Prompt v1 showed
# one valid action per task — HOLD, REJECT, MIGRATE+KEEP — which
# biased B0 toward the correct direction. Documenting parameters
# without demonstrating direction keeps B0 honest: the v1 failure
# mode it repairs is real — a first v2 draft with bare param_name
# placeholders collapsed every score, because models copied the
# literal key and graders saw no usable params.)
ACTION_PARAMS = {
    "SET_BACKEND": ("backend",),
    "CONFIGURE_SEARCH": ("mechanism",),
    "KEEP_FACADE": (),
    "DELETE_FACADE": (),
    "UPDATE_DOCS": ("scope",),
    "DEFER_DOCS": ("until",),
    "REGENERATE_FIXTURES": ("scope",),
    "MIGRATE_CALLERS": ("scope",),
    "REPORT_BLOCKERS": ("items",),
    "ADOPT_MECHANISM": ("name", "reason_refs"),
    "REJECT_MECHANISM": ("name", "reason_refs"),
    "SHIP_CHAPTER": ("chapter",),
    "HOLD_CHAPTER": ("chapter", "reason", "blockers"),
    "CITE_RULE": ("rule_id",),
    "ECHO_PRESENT": ("items",),
    "ABSTAIN": ("reason",),
    # Transfer-only aliases (see real_transfer.TRANSFER_ALIASES).
    "REPORT_RESULT": (),
    "REJECT_PROPOSAL": ("name", "reason"),
    "IMPLEMENT_ABSTENTION_PATH": ("abstention_path", "fallback"),
}

FORMAT_SHAPE = ('{"action_type": "EXAMPLE_ACTION", '
                '"example_parameter": "example_value"}')


def action_docs(schema: tuple[str, ...]) -> str:
    """One line per allowed action: name with its parameter names."""
    lines = []
    for atype in schema:
        params = ", ".join(ACTION_PARAMS.get(atype, ()))
        lines.append(f"- {atype}({params})" if params else f"- {atype}()")
    return "\n".join(lines)


def build_prompt(task: BehaviorTask, context: str) -> str:
    body = (f"Work objective: {task.work_objective}\n\n"
            f"Present task state:\n{task.present_state}\n\n")
    if context.strip():
        body += f"Project evidence:\n\n{context}\n\n"
    else:
        body += ("Project evidence: none supplied. "
                 "Decide from the present task state alone.\n\n")
    body += (f"Allowed actions (name with its parameters — fill values "
             f"from the task and the evidence):\n"
             f"{action_docs(task.action_schema)}\n\n"
             f"Respond with a brief rationale, then exactly one ```json "
             f"block with an \"actions\" list. Shape (the action shown "
             f"is a placeholder and NOT valid — choose from the allowed "
             f"actions above):\n"
             f"```json\n{{\"actions\": [{FORMAT_SHAPE}]}}\n```")
    return body


def parse_actions(answer_text: str,
                  allowed: tuple[str, ...]) -> tuple[list[dict], bool]:
    """Extract the actions list. Returns (actions, parse_ok).

    parse_ok is False when no JSON object with an actions list is
    found, or an action type falls outside the schema.
    """
    import json
    start = answer_text.find("```json")
    if start == -1:
        start = answer_text.find("{")
        if start == -1:
            return [], False
        blob = answer_text[start:]
    else:
        blob = answer_text[start + len("```json"):]
        end = blob.find("```")
        blob = blob[:end] if end != -1 else blob
    try:
        payload = json.loads(_balance(blob.strip()))
    except (ValueError, TypeError):
        return [], False
    actions = payload.get("actions") if isinstance(payload, dict) else None
    if not isinstance(actions, list):
        return [], False
    cleaned: list[dict] = []
    for action in actions:
        if not isinstance(action, dict):
            return [], False
        # Accept "type" as an alias: the contract is the action kind,
        # not the key spelling. Unknown kinds still fail.
        atype = action.get("action_type", action.get("type"))
        if atype not in allowed:
            return [], False
        normalized = {str(k): v for k, v in action.items()
                      if k != "type"}
        normalized["action_type"] = atype
        cleaned.append(normalized)
    return cleaned, True


def _balance(blob: str) -> str:
    """Tolerate a missing run of closing braces at end of output."""
    opens = blob.count("{") - blob.count("}")
    closeds = blob.count("[") - blob.count("]")
    return blob + "]" * max(0, closeds) + "}" * max(0, opens)
