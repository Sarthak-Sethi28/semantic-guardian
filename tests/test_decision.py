"""Owner-decision tests (#7). Pure — no network."""
from semantic_guardian.blast_radius import BlastRadius, ImpactedEntity
from semantic_guardian.decision import (
    OwnerDecision,
    ReviewPacket,
    apply_decision,
    build_packet,
)
from semantic_guardian.engine import Finding
from semantic_guardian.models import Owner


def _finding(cls="breaking"):
    return Finding(field_path="revenue", classification=cls, change_class="unit_scale",
                   explanation="revenue /100 breaks USD contract",
                   hypotheses=["dollars->cents", "intentional rescale"], confidence={"code": 0.95})


def _blast():
    o = Owner(urn="urn:li:corpuser:jdoe", username="jdoe")
    return BlastRadius(
        source_urn="urn:li:dataset:(x,fct_revenue,PROD)", severity="high",
        impacted=[ImpactedEntity(urn="urn:li:mlFeature:(t,f)", entity_type="mlFeature",
                                 relationship="DerivedFrom", owners=[o])],
        owners_to_notify=[o], counts={"mlFeature": 1},
    )


def test_build_packet_bundles_everything_for_the_owner():
    p = build_packet(_finding(), _blast())
    assert isinstance(p, ReviewPacket)
    # the packet has the evidence a human needs to decide, not just a yes/no prompt
    assert p.finding.explanation
    assert p.hypotheses == ["dollars->cents", "intentional rescale"]
    assert p.severity == "high"
    assert "jdoe" in [o.username for o in p.owners]
    assert p.assigned_owner == "jdoe"  # routed to the DataHub-declared owner


def test_build_packet_unowned_routes_to_none():
    b = _blast()
    b.owners_to_notify = []
    p = build_packet(_finding(), b)
    assert p.assigned_owner is None  # surfaced as unowned, not crashed


def test_apply_decision_confirms_breaking_with_corrected_semantics():
    p = build_packet(_finding(), _blast())
    decision = OwnerDecision(
        verdict="breaking", decided_by="jdoe",
        correct_semantics="revenue must stay in USD dollars (not cents)",
        change_class="unit_scale",
    )
    resolved = apply_decision(p, decision)
    # the resolved finding is what feeds write-back (#8) + contract (#9)
    assert resolved.classification == "breaking"
    assert resolved.change_class == "unit_scale"
    assert "USD dollars" in resolved.explanation  # owner's corrected semantics carried through
    assert resolved.confidence.get("human") == 1.0  # human validation is max-confidence


def test_apply_decision_can_overrule_to_intentional():
    """Owner says the model was wrong — it's an intentional, compatible change."""
    p = build_packet(_finding(), _blast())
    decision = OwnerDecision(verdict="intentional", decided_by="jdoe",
                             correct_semantics="deliberate migration to cents, contract updated")
    resolved = apply_decision(p, decision)
    assert resolved.classification == "compatible"  # human overruled the 'breaking' call
    assert "deliberate" in resolved.explanation.lower()


def test_apply_decision_requires_a_decider():
    p = build_packet(_finding(), _blast())
    import pytest
    with pytest.raises(ValueError, match="decided_by"):
        apply_decision(p, OwnerDecision(verdict="breaking", decided_by="",
                                        correct_semantics="x"))
