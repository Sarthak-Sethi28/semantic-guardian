"""Review-UI (GitHub-native comment) tests (#13). Pure rendering — no network."""

from semantic_guardian.blast_radius import BlastRadius, ImpactedEntity
from semantic_guardian.engine import Finding
from semantic_guardian.models import Owner
from semantic_guardian.review_ui import render_review
from semantic_guardian.skill import SkillResult


def _breaking_result():
    f = Finding(
        field_path="account_status",
        classification="breaking",
        change_class="categorical_remap",
        explanation="CASE inverts the active/deleted encoding",
        hypotheses=["intentional recode", "accidental inversion"],
        confidence={"code": 0.97, "stats": 0.0, "catalog": 0.8},
    )
    br = BlastRadius(
        source_urn="urn:li:dataset:(x,fct,PROD)",
        severity="medium",
        impacted=[
            ImpactedEntity(
                urn="urn:li:mlFeature:(t,f)",
                entity_type="mlFeature",
                relationship="DerivedFrom",
                owners=[Owner(urn="urn:li:corpuser:jdoe", username="jdoe")],
            )
        ],
        owners_to_notify=[Owner(urn="urn:li:corpuser:jdoe", username="jdoe")],
        counts={"mlFeature": 1},
    )
    return SkillResult(
        event="pr:42",
        dataset_urn="urn:li:dataset:(x,fct,PROD)",
        changed_fields=["account_status"],
        findings=[f],
        blast_radius=br,
        escalated=True,
    )


def test_render_breaking_review_is_markdown_with_the_essentials():
    md = render_review(_breaking_result())
    assert "Semantic Guardian" in md
    assert "BREAKING" in md.upper()
    assert "account_status" in md
    assert "categorical_remap" in md
    # evidence + hypotheses + blast + owner all surfaced
    assert "inverts" in md.lower()
    assert "intentional recode" in md
    assert "medium" in md.lower()
    assert "jdoe" in md
    # stats-blind point is made (the differentiator)
    assert "0.00" in md or "stats" in md.lower()


def test_render_clean_result_says_no_breaking_change():
    res = SkillResult(
        event="pr:7",
        dataset_urn="urn:li:dataset:(x,fct,PROD)",
        changed_fields=["revenue"],
        findings=[Finding(field_path="revenue", classification="compatible")],
        escalated=False,
    )
    md = render_review(res)
    assert "no breaking" in md.lower() or "compatible" in md.lower()
    # no ALARM headline (the breaking-finding section header)
    assert "**BREAKING semantic change**" not in md


def test_render_no_changes():
    res = SkillResult(
        event="local",
        dataset_urn="urn:li:dataset:(x,fct,PROD)",
        changed_fields=[],
        findings=[],
        escalated=False,
    )
    md = render_review(res)
    assert "no column changes" in md.lower()


def test_render_abstain_is_labeled_not_a_false_alarm():
    res = SkillResult(
        event="pr:9",
        dataset_urn="urn:li:dataset:(x,fct,PROD)",
        changed_fields=["score"],
        findings=[Finding(field_path="score", classification="insufficient-context")],
        escalated=False,
    )
    md = render_review(res)
    assert "insufficient" in md.lower() or "abstain" in md.lower()
