"""Durable-contract + remediation tests (#9). Graph mocked — no network."""
from unittest.mock import MagicMock

from semantic_guardian.contract import (
    RemediationPatch,
    compile_contract,
    propose_remediation,
)
from semantic_guardian.engine import Finding

DS = "urn:li:dataset:(urn:li:dataPlatform:dbt,fct_revenue,PROD)"


def _finding(cls="breaking", kind="unit_scale", field="revenue"):
    return Finding(
        field_path=field, classification=cls, change_class=kind,
        explanation="revenue divided by 100 breaks the USD-dollars contract",
        hypotheses=["dollars->cents"], confidence={"code": 0.95},
    )


def _client():
    c = MagicMock()
    c._graph = MagicMock()
    c._graph.execute_graphql.return_value = {
        "upsertCustomAssertion": {"urn": "urn:li:assertion:xyz"}
    }
    return c


# ── durable contract ──────────────────────────────────────────────────────────


def test_compile_contract_creates_assertion_for_breaking_finding():
    client = _client()
    urn = compile_contract(client, DS, _finding(), platform="dbt")
    assert urn == "urn:li:assertion:xyz"
    # sent an upsertCustomAssertion with the required platform + fieldPath
    _, kwargs = client._graph.execute_graphql.call_args
    inp = kwargs["variables"]["input"]
    assert inp["entityUrn"] == DS
    assert inp["fieldPath"] == "revenue"
    assert inp["platform"]["urn"].endswith("dbt")
    assert "revenue" in inp["description"].lower() or "revenue" in inp["type"].lower()


def test_compile_contract_skips_non_breaking():
    client = _client()
    urn = compile_contract(client, DS, _finding(cls="compatible"), platform="dbt")
    assert urn is None
    assert client._graph.execute_graphql.call_count == 0  # nothing written for compatible


def test_compile_contract_skips_abstain():
    client = _client()
    f = _finding(cls="insufficient-context")
    assert compile_contract(client, DS, f, platform="dbt") is None


# ── remediation patch (deterministic per class) ─────────────────────────────────


def test_remediation_for_unit_scale_reverses_the_scale():
    patch = propose_remediation(_finding(kind="unit_scale"),
                                before_expr="revenue", after_expr="revenue / 100 as revenue")
    assert isinstance(patch, RemediationPatch)
    # the fix should restore the original scale (multiply back / drop the /100)
    assert "* 100" in patch.suggested_after or patch.suggested_after.strip() == "revenue"
    assert patch.rationale


def test_remediation_for_null_sentinel_restores_null():
    patch = propose_remediation(_finding(kind="null_sentinel"),
                                before_expr="revenue",
                                after_expr="coalesce(revenue, 0) as revenue")
    # fix removes the coalesce that masked nulls
    assert "coalesce" not in patch.suggested_after.lower()


def test_remediation_unknown_class_is_advisory_not_a_silent_guess():
    patch = propose_remediation(_finding(kind="other"),
                                before_expr="x", after_expr="weird(x)")
    # we don't fabricate a fix for a class we can't safely reverse
    assert patch.suggested_after is None
    assert "manual" in patch.rationale.lower() or "review" in patch.rationale.lower()
