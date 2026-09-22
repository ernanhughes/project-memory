"""Verification: VeriTrail-style reverse traces with error localisation.

For each claim, verification walks backward through the recorded
pipeline stages:

    final claim -> reader output -> context memory -> derived graph
    object -> intermediate extraction -> raw source span

At each stage it asks whether the stage output is supported by its
inputs (ledger truth on fixtures). Verdicts use the VeriTrail
taxonomy, mapped onto book language:

    FULLY_SUPPORTED / NOT_FULLY_SUPPORTED / INCONCLUSIVE

Error localisation: the first stage (from the source upward) whose
output is not supported by its inputs is the likely introduction
stage. A fluent final answer that merely repeats an unsupported
summary localises to the summary, not to the reader.

This is reconstructed support where the ledger is the hypothesis and
recorded process lineage where the pipeline captured it; the two are
marked differently (``basis`` field). Reconstructed causality is
never presented as recorded causality.
"""

from __future__ import annotations

from dataclasses import dataclass, field

STAGES = ("source", "extraction", "graph_node", "summary",
          "context", "reader")


@dataclass
class StageRecord:
    stage: str
    node_id: str
    # Whether this stage output is supported by its inputs.
    supported_by_inputs: bool | None  # None = unknown/inconclusive
    basis: str = "recorded"  # recorded | reconstructed
    detail: str = ""


@dataclass
class Verification:
    claim_id: str
    stages: list[StageRecord] = field(default_factory=list)
    final_verdict: str = "INCONCLUSIVE"
    error_stage: str | None = None
    evidence_trail: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "final_verdict": self.final_verdict,
            "error_stage": self.error_stage,
            "evidence_trail": self.evidence_trail,
            "stages": [
                {"stage": s.stage, "node": s.node_id,
                 "supported_by_inputs": s.supported_by_inputs,
                 "basis": s.basis, "detail": s.detail}
                for s in self.stages
            ],
        }


def verify_backward(claim_id: str,
                    stage_support: dict[str, bool | None],
                    node_ids: dict[str, str] | None = None,
                    basis: str = "reconstructed") -> Verification:
    """Reverse verification over the six pipeline stages.

    ``stage_support`` maps stage name -> supported-by-inputs (True /
    False / None for unknown). Missing stages are INCONCLUSIVE.
    """
    node_ids = node_ids or {}
    verification = Verification(claim_id=claim_id)
    trail: list[str] = []
    # Walk from the terminal claim back toward the source, collecting
    # interim verdicts exactly as VeriTrail does.
    interim: list[tuple[str, bool | None]] = []
    for stage in reversed(STAGES):
        value = stage_support.get(stage)
        interim.append((stage, value))
        verification.stages.append(StageRecord(
            stage=stage,
            node_id=node_ids.get(stage, f"{claim_id}::{stage}"),
            supported_by_inputs=value,
            basis=("recorded" if stage == "source" else basis),
        ))
    verification.stages.reverse()
    supported_stages = [s for s, v in interim if v is True]
    failed_stages = [s for s, v in interim if v is False]
    # Final verdict: terminal claim supported only if every stage
    # from source to reader holds.
    if all(stage_support.get(s) is True for s in STAGES):
        verification.final_verdict = "FULLY_SUPPORTED"
        verification.evidence_trail = [
            node_ids.get(s, f"{claim_id}::{s}") for s in STAGES]
    elif any(stage_support.get(s) is False for s in STAGES):
        verification.final_verdict = "NOT_FULLY_SUPPORTED"
        # Error stage: the earliest stage whose output is unsupported
        # by its inputs — where the error likely entered.
        for stage in STAGES:
            if stage_support.get(stage) is False:
                verification.error_stage = stage
                break
        verification.evidence_trail = [
            node_ids.get(s, f"{claim_id}::{s}") for s in supported_stages]
    else:
        verification.final_verdict = "INCONCLUSIVE"
        verification.evidence_trail = trail
    _ = failed_stages
    return verification
