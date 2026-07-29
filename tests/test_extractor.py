"""Signal extractor tests (#4). Pure — no network. Uses scenario fixtures + built models."""
from __future__ import annotations

from pathlib import Path

from semantic_guardian.clients.git import GitClient
from semantic_guardian.extractor import extract_snapshots
from semantic_guardian.models import Dataset, GlossaryTerm, SchemaField

CHANGES = Path(__file__).resolve().parents[1] / "scenario" / "changes"


def _fct_revenue() -> Dataset:
    return Dataset(
        urn="urn:li:dataset:(urn:li:dataPlatform:dbt,fct_revenue,PROD)",
        name="fct_revenue",
        platform="dbt",
        fields={
            "order_id": SchemaField(field_path="order_id", native_type="varchar(64)"),
            "customer_id": SchemaField(field_path="customer_id", native_type="varchar(64)"),
            "revenue": SchemaField(
                field_path="revenue",
                native_type="int",
                description="Revenue in USD dollars (not cents).",
                glossary_terms=[
                    GlossaryTerm(
                        urn="urn:li:glossaryTerm:Money.USD_Dollars", name="USD_Dollars"
                    )
                ],
            ),
            "created_at": SchemaField(field_path="created_at", native_type="timestamp"),
        },
    )


def _load(name: str):
    return GitClient().get_local_diff(CHANGES / f"{name}.diff")


def test_unit_scale_joins_semantics_and_classifies():
    deltas = extract_snapshots(_fct_revenue(), _load("unit_scale"))
    rev = [d for d in deltas if d.change.field_path == "revenue"]
    assert len(rev) == 1
    d = rev[0]
    assert d.change.change_kind == "unit_scale"
    assert "/ 100" in d.change.after_expr
    assert d.change.before_expr == "revenue"
    # joined to declared semantics (the contract)
    assert "dollars" in (d.column.description or "").lower()
    assert any(t.name == "USD_Dollars" for t in d.column.glossary_terms)


def test_null_sentinel_classified():
    deltas = extract_snapshots(_fct_revenue(), _load("null_sentinel"))
    d = next(d for d in deltas if d.change.field_path == "revenue")
    assert d.change.change_kind == "null_sentinel"
    assert "coalesce" in d.change.after_expr.lower()


def test_categorical_remap_classified():
    ds = Dataset(
        urn="urn:li:dataset:(urn:li:dataPlatform:dbt,dim_account,PROD)",
        name="dim_account",
        fields={"account_status": SchemaField(field_path="account_status", native_type="int")},
    )
    deltas = extract_snapshots(ds, _load("categorical_remap"))
    d = next(d for d in deltas if d.change.field_path == "account_status")
    assert d.change.change_kind == "categorical_remap"


def test_benign_change_yields_no_real_delta():
    # comment-only change must not produce a semantic column delta (false-positive guard)
    deltas = extract_snapshots(_fct_revenue(), _load("benign"))
    real = [d for d in deltas if d.change.change_kind != "none"]
    assert real == []


def test_unmatched_column_not_dropped():
    ds = Dataset(urn="urn:li:dataset:(x,empty,PROD)", name="empty", fields={})
    deltas = extract_snapshots(ds, _load("unit_scale"))
    d = next(d for d in deltas if d.change.field_path == "revenue")
    assert d.column.declared_type is None  # not in schema, still surfaced
    assert d.change.change_kind == "unit_scale"


def test_deterministic():
    ds, diff = _fct_revenue(), _load("unit_scale")
    assert extract_snapshots(ds, diff) == extract_snapshots(ds, diff)
