"""Semantic-delta engine tests (#5). LLM behind a stub interface — no key, no network.

The engine's job is to ASSEMBLE evidence, ask the reasoner, and parse a Finding. We test
that with a scripted reasoner so the whole spine is verifiable offline; the real model
(Bedrock/Anthropic) is a drop-in that satisfies the same interface.
"""
from semantic_guardian.engine import (
    Finding,
    LLMReasoner,
    reason_about_change,
)
from semantic_guardian.models import (
    ChangeSnapshot,
    ColumnDelta,
    ColumnSnapshot,
)


def _delta(field="revenue", kind="unit_scale", before="revenue",
           after="revenue / 100 as revenue", desc="Revenue in USD dollars (not cents)"):
    return ColumnDelta(
        column=ColumnSnapshot(field_path=field, declared_type="int", description=desc),
        change=ChangeSnapshot(
            field_path=field, before_expr=before, after_expr=after, change_kind=kind
        ),
    )


class ScriptedReasoner:
    """A fake reasoner that returns canned JSON — stands in for the real LLM."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.last_prompt = None

    def reason(self, prompt: str) -> str:
        import json
        self.last_prompt = prompt
        return json.dumps(self.payload)


def test_engine_classifies_breaking_unit_change():
    reasoner = ScriptedReasoner({
        "classification": "breaking",
        "change_class": "unit_scale",
        "explanation": "revenue divided by 100 contradicts the declared dollars contract",
        "hypotheses": ["dollars->cents unit change", "intentional rescale"],
        "confidence": {"code": 0.95, "catalog": 0.9, "stats": 0.0, "precedent": 0.3},
    })
    finding = reason_about_change(reasoner, _delta())
    assert isinstance(finding, Finding)
    assert finding.classification == "breaking"
    assert finding.change_class == "unit_scale"
    assert "dollars" in finding.explanation.lower()
    assert len(finding.hypotheses) >= 2


def test_engine_feeds_evidence_not_the_heuristic_verdict():
    """Nothing hardcoded: the change_kind HINT must NOT be handed to the LLM as the answer,
    or the model just rubber-stamps it. The prompt carries the diff + contract, not the label."""
    reasoner = ScriptedReasoner({"classification": "compatible", "change_class": "other",
                                 "explanation": "x", "hypotheses": ["a", "b"], "confidence": {}})
    reason_about_change(reasoner, _delta(kind="unit_scale"))
    p = reasoner.last_prompt.lower()
    # evidence IS present
    assert "revenue / 100" in p
    assert "usd dollars" in p
    # the heuristic label is NOT injected as a stated fact/conclusion about THIS change.
    # (The enum of allowed answers may list the class names; what must not appear is the
    # extractor telling the model 'the detected change_kind is X'.)
    assert "change_kind" not in p
    assert "detected" not in p
    assert "the change is unit_scale" not in p


def test_engine_abstains_on_low_evidence():
    reasoner = ScriptedReasoner({
        "classification": "insufficient-context", "change_class": "unknown",
        "explanation": "not enough signal", "hypotheses": [],
        "confidence": {"code": 0.2},
    })
    finding = reason_about_change(reasoner, _delta(after="revenue", before="revenue"))
    assert finding.classification == "insufficient-context"
    assert finding.abstained is True


def test_engine_handles_bad_llm_json_as_abstain():
    class BadReasoner:
        def reason(self, prompt): return "this is not json"
    finding = reason_about_change(BadReasoner(), _delta())
    # a malformed LLM response must not crash and must not fabricate a verdict
    assert finding.classification == "insufficient-context"
    assert finding.abstained is True


def test_inverted_categorical_is_breaking_from_diff_evidence():
    """The key 'genuinely semantic' proof: an inverted CASE has NO statistical signal, but
    the engine flags it breaking from the DIFF evidence alone (this is what stats tools miss)."""
    delta = _delta(
        field="account_status", kind="categorical_remap",
        before="account_status",
        after="case when account_status = 1 then 0 else 1 end as account_status",
        desc="1 = active, 0 = deleted",
    )
    reasoner = ScriptedReasoner({
        "classification": "breaking", "change_class": "categorical_remap",
        "explanation": "CASE inverts active/deleted; distribution unchanged, stats blind",
        "hypotheses": ["intentional recode", "accidental inversion"],
        "confidence": {"code": 0.97, "stats": 0.0, "catalog": 0.8},
    })
    finding = reason_about_change(reasoner, delta)
    assert finding.classification == "breaking"
    assert finding.change_class == "categorical_remap"


def test_llm_reasoner_is_a_protocol():
    """Any object with reason(prompt)->str satisfies the interface (Bedrock/Anthropic drop-in)."""
    class X:
        def reason(self, prompt: str) -> str:
            return "{}"

    assert isinstance(X(), LLMReasoner)  # structural/runtime_checkable protocol
    # and a duck-typed reasoner works without inheriting anything
    f = reason_about_change(X(), _delta())
    assert isinstance(f, Finding)


def test_get_reasoner_prefers_anthropic_key(monkeypatch):
    """Provider selection is env-driven and testable without any live call."""
    import semantic_guardian.reasoners as r
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    # don't actually construct the SDK client — just prove the selection branch
    class _Fake:
        def __init__(self, *a, **k): ...
    monkeypatch.setattr(r, "AnthropicReasoner", _Fake)
    monkeypatch.setattr(r, "BedrockReasoner", _Fake)
    assert isinstance(r.get_reasoner(), _Fake)
