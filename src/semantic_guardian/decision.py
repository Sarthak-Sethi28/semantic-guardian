"""Owner decision layer (#7) — human-in-the-loop, rich not binary.

The costly work is deciding WHAT'S TRUE, not clicking approve. So we present the owner a
full ReviewPacket (the finding, diff-grounded explanation, competing hypotheses, blast
radius, affected owners) and capture a structured OwnerDecision (breaking vs intentional,
the corrected semantics, who decided). apply_decision folds that human judgment back into
the Finding — which then feeds write-back (#8) and the durable contract (#9).

Routing: the packet is assigned to the owner DataHub says is responsible (from the blast
radius' owner set). Human validation is recorded as max-confidence, so the durable contract
compiled from it no longer depends on the model.
"""
from __future__ import annotations

from pydantic import BaseModel

from semantic_guardian.blast_radius import BlastRadius
from semantic_guardian.engine import Finding
from semantic_guardian.models import Owner


class ReviewPacket(BaseModel):
    """Everything an owner needs to decide — assembled, not a bare yes/no prompt."""

    finding: Finding
    hypotheses: list[str] = []
    severity: str = "none"
    owners: list[Owner] = []
    assigned_owner: str | None = None  # username DataHub says is responsible


class OwnerDecision(BaseModel):
    """The structured human decision. Rich enough to compile a contract from."""

    verdict: str  # breaking | intentional | not-a-change
    decided_by: str
    correct_semantics: str  # the owner's statement of what the column should mean
    change_class: str | None = None  # owner may correct/confirm the class


def build_packet(finding: Finding, blast: BlastRadius) -> ReviewPacket:
    """Bundle the finding + impact into a routed review packet for the owner."""
    assigned = blast.owners_to_notify[0].username if blast.owners_to_notify else None
    return ReviewPacket(
        finding=finding,
        hypotheses=finding.hypotheses,
        severity=blast.severity,
        owners=blast.owners_to_notify,
        assigned_owner=assigned,
    )


_VERDICT_TO_CLASSIFICATION = {
    "breaking": "breaking",
    "intentional": "compatible",  # owner says the change is deliberate + acceptable
    "not-a-change": "compatible",
}


def apply_decision(packet: ReviewPacket, decision: OwnerDecision) -> Finding:
    """Fold the owner's structured decision back into a resolved Finding.

    The result carries the owner's corrected semantics and is marked human-validated
    (max confidence) — this is what write-back (#8) and the durable contract (#9) consume.
    """
    if not decision.decided_by:
        raise ValueError("decided_by is required — a decision must be attributable to an owner")

    base = packet.finding
    classification = _VERDICT_TO_CLASSIFICATION.get(decision.verdict, base.classification)
    confidence = dict(base.confidence)
    confidence["human"] = 1.0  # a human validated it; the contract no longer needs the model

    return Finding(
        field_path=base.field_path,
        classification=classification,
        change_class=decision.change_class or base.change_class,
        explanation=decision.correct_semantics or base.explanation,
        hypotheses=base.hypotheses,
        confidence=confidence,
    )
