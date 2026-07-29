"""DataHub Skill orchestration tests (#12). All layers mocked — no network/LLM."""
import json
from unittest.mock import MagicMock

from semantic_guardian.models import (
    ChangeSnapshot,
    ColumnDelta,
    ColumnSnapshot,
    Dataset,
    FileChange,
    PRDiff,
    SchemaField,
)
from semantic_guardian.skill import SkillResult, review_change

DS = "urn:li:dataset:(urn:li:dataPlatform:dbt,fct_revenue,PROD)"


class _Reasoner:
    def reason(self, prompt):
        return json.dumps({"classification": "breaking", "change_class": "unit_scale",
                           "explanation": "revenue /100 breaks USD contract",
                           "hypotheses": ["dollars->cents"], "confidence": {"code": 0.9}})


def _client():
    c = MagicMock()
    c.get_dataset.return_value = Dataset(
        urn=DS, name="fct_revenue", platform="dbt",
        fields={"revenue": SchemaField(field_path="revenue", native_type="int",
                                       description="Revenue in USD dollars (not cents)")},
    )
    c.get_related.return_value = []  # keep blast radius simple here
    c.get_owners.return_value = []
    c._graph = MagicMock()
    c._graph.execute_graphql.return_value = {"upsertCustomAssertion": {"urn": "urn:li:assertion:z"}}
    return c


def _diff():
    return PRDiff(files=[FileChange(path="models/fct_revenue.sql",
                                    patch="- revenue,\n+ revenue / 100 as revenue,")])


def test_review_change_runs_full_workflow(monkeypatch):
    # stub the extractor so we don't depend on SQL parsing here
    import semantic_guardian.trigger as trig
    monkeypatch.setattr(trig, "extract_snapshots", lambda ds, d: [ColumnDelta(
        column=ColumnSnapshot(field_path="revenue", declared_type="int",
                              description="Revenue in USD dollars (not cents)"),
        change=ChangeSnapshot(field_path="revenue", before_expr="revenue",
                              after_expr="revenue / 100 as revenue", change_kind="unit_scale"),
    )])

    res = review_change(_client(), DS, _diff(), reasoner=_Reasoner(), event="local")
    assert isinstance(res, SkillResult)
    # the skill composed every stage into one result
    assert res.changed_fields == ["revenue"]
    assert res.findings[0].classification == "breaking"
    assert res.blast_radius is not None
    assert res.escalated is True  # a breaking finding escalates


def test_review_change_no_changes_short_circuits(monkeypatch):
    import semantic_guardian.trigger as trig
    monkeypatch.setattr(trig, "extract_snapshots", lambda ds, d: [])
    res = review_change(_client(), DS, PRDiff(files=[]), reasoner=_Reasoner(), event="local")
    assert res.findings == []
    assert res.escalated is False


def test_review_change_does_not_write_back_without_approval(monkeypatch):
    """The Skill reasons + reports but must NOT write to the graph unless asked (human-gated)."""
    import semantic_guardian.trigger as trig
    monkeypatch.setattr(trig, "extract_snapshots", lambda ds, d: [ColumnDelta(
        column=ColumnSnapshot(field_path="revenue", description="Revenue in USD dollars"),
        change=ChangeSnapshot(field_path="revenue", before_expr="revenue",
                              after_expr="revenue / 100 as revenue"),
    )])
    client = _client()
    review_change(client, DS, _diff(), reasoner=_Reasoner(), event="local",
                  write_back_on_breaking=False)
    # no assertion / incident mutation fired
    assert client._graph.execute_graphql.call_count == 0
