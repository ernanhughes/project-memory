"""Building a WorkFrame from work signals.

A WorkFrame is not a prompt. It is built from whatever signals the
system actually has: a user message, an event, a tool result, a failing
test, a scheduled job, a state change. ``build`` is deliberately the
only place where free-form text becomes structure, and it is required to
cite the signals that licensed each field, so an inferred frame can be
audited against the observations behind it.

Two builders:

* ``infer_work_frame`` uses the reader model to choose a work type from
  the ones the ProjectFrame declares and to phrase the objective. It is
  the realistic path, and it is the one that can be wrong.
* ``keyword_work_frame`` is the deterministic fallback: no service, no
  model, same interface. It is weaker and is labelled as such.

The declared frames in ``fixtures.py`` are the third case: a frame a
person wrote. The experiments compare all three, because a frame the
system infers badly is the layer's most dangerous failure mode.
"""

from __future__ import annotations

import json
import re

from .model import ProjectFrame, WorkFrame, WorkSignal

# Deterministic fallback cues. One line per work type, drawn from the
# vocabulary of the work itself rather than from any task fixture.
CUES: dict[str, tuple[str, ...]] = {
    "publication_review": ("publish", "publication", "prose", "citation",
                           "front matter", "reads", "wording", "draft",
                           "proofread", "style"),
    "architecture_review": ("architecture", "belongs", "next step",
                            "right step", "baseline", "measured", "decide "
                            "whether", "design", "structure"),
    "release_readiness": ("release", "outstanding", "blocking", "left to do",
                          "ready", "cut", "sweep", "checklist"),
    "experiment_analysis": ("experiment", "run", "metric", "result",
                            "measurement", "benchmark", "score"),
    "implementation_review": ("implementation", "code", "store", "failed",
                              "connection", "module", "improve the",
                              "refactor", "test"),
}


def keyword_work_frame(work_frame_id: str, project: ProjectFrame,
                       signals: tuple[WorkSignal, ...], as_of: str,
                       objective: str = "") -> WorkFrame:
    """Cue-count classification over the signal texts. No model needed."""
    blob = " ".join(s.text.lower() for s in signals)
    known = project.known_work_types()
    scores = {wt: sum(1 for cue in CUES.get(wt, ()) if cue in blob)
              for wt in known}
    best = max(known, key=lambda wt: (scores.get(wt, 0), wt)) if known else "default"
    if not scores.get(best):
        best = known[0] if known else "default"
    refs = tuple(s.signal_id for s in signals)
    return WorkFrame(
        work_frame_id=work_frame_id, project_id=project.project_id,
        objective=objective or _first_sentence(signals),
        work_type=best, as_of=as_of, signals=signals,
        provenance=(("objective", refs), ("work_type", refs)),
        derivation="inferred")


def _first_sentence(signals: tuple[WorkSignal, ...]) -> str:
    for signal in signals:
        if signal.kind in ("user_message", "agent_task", "scheduled_job"):
            return signal.text.split(".")[0].strip()
    return signals[0].text.split(".")[0].strip() if signals else ""


PROMPT = """A project's standing policy declares these work types:
{types}

Observations available right now:
{observations}

Reply with JSON only, no prose:
{{"work_type": "<one of the listed types>",
  "objective": "<one sentence naming what is being done now>",
  "signals_used": ["<signal ids that justify the choice>"]}}"""


def infer_work_frame(work_frame_id: str, project: ProjectFrame,
                     signals: tuple[WorkSignal, ...], as_of: str,
                     reader) -> WorkFrame:
    """Model-inferred frame, constrained to the declared work types."""
    known = project.known_work_types()
    observations = "\n".join(
        f"- [{s.signal_id}] ({s.kind}) {s.text}" for s in signals)
    prompt = PROMPT.format(types="\n".join(f"- {t}" for t in known),
                           observations=observations)
    raw = reader.ask(prompt)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    work_type, objective, used = "", "", []
    if match:
        try:
            parsed = json.loads(match.group(0))
            work_type = str(parsed.get("work_type", "")).strip()
            objective = str(parsed.get("objective", "")).strip()
            used = [str(x) for x in parsed.get("signals_used", [])]
        except json.JSONDecodeError:
            pass
    if work_type not in known:
        # An unusable reply falls back rather than inventing a work type.
        return keyword_work_frame(work_frame_id, project, signals, as_of,
                                  objective)
    valid = {s.signal_id for s in signals}
    refs = tuple(x for x in used if x in valid) or tuple(
        s.signal_id for s in signals)
    return WorkFrame(
        work_frame_id=work_frame_id, project_id=project.project_id,
        objective=objective or _first_sentence(signals), work_type=work_type,
        as_of=as_of, signals=signals,
        provenance=(("objective", refs), ("work_type", refs)),
        derivation="inferred")
