"""Change-trigger tests (#16). Client + diff mocked — no network."""
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
from semantic_guardian.trigger import ReviewRequest, build_review_request

DS = "urn:li:dataset:(urn:li:dataPlatform:dbt,fct_revenue,PROD)"


def _delta(field, kind, before, after):
    return ColumnDelta(
        column=ColumnSnapshot(field_path=field, declared_type="int",
                              description="Revenue in USD dollars"),
        change=ChangeSnapshot(
            field_path=field, before_expr=before, after_expr=after, change_kind=kind
        ),
    )


def _client_with_dataset():
    c = MagicMock()
    c.get_dataset.return_value = Dataset(
        urn=DS, name="fct_revenue", platform="dbt",
        fields={"revenue": SchemaField(field_path="revenue", native_type="int",
                                       description="Revenue in USD dollars")},
    )
    return c


def test_build_review_request_from_local_diff(monkeypatch):
    diff = PRDiff(files=[FileChange(path="models/fct_revenue.sql",
                                    patch="- revenue,\n+ revenue / 100 as revenue,")])
    client = _client_with_dataset()

    # stub the extractor so this test isolates the trigger's assembly
    import semantic_guardian.trigger as trig
    monkeypatch.setattr(
        trig, "extract_snapshots",
        lambda ds, d: [_delta("revenue", "unit_scale", "revenue", "revenue / 100 as revenue")],
    )

    req = build_review_request(client, dataset_urn=DS, diff=diff, event="local")
    assert isinstance(req, ReviewRequest)
    assert req.dataset_urn == DS
    assert req.event == "local"
    assert len(req.deltas) == 1
    assert req.deltas[0].change.change_kind == "unit_scale"
    # the changed columns are surfaced for the engine + blast radius
    assert req.changed_fields == ["revenue"]


def test_build_review_request_no_changes_is_empty(monkeypatch):
    import semantic_guardian.trigger as trig
    monkeypatch.setattr(trig, "extract_snapshots", lambda ds, d: [])
    req = build_review_request(_client_with_dataset(), dataset_urn=DS,
                               diff=PRDiff(files=[]), event="local")
    assert req.deltas == []
    assert req.changed_fields == []


def test_review_request_carries_dataset_for_downstream():
    """The request must carry the dataset URN so blast-radius (#6) and the engine (#5)
    can act on it without re-resolving."""
    import pytest

    import semantic_guardian.trigger as trig
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(trig, "extract_snapshots", lambda ds, d: [])
        req = build_review_request(_client_with_dataset(), dataset_urn=DS,
                                   diff=PRDiff(files=[]), event="pr:42")
    assert req.dataset_urn == DS
    assert req.event == "pr:42"
