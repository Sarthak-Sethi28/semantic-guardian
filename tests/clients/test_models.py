"""Typed model tests (#2). Pure, no I/O."""
from __future__ import annotations

from semantic_guardian.models import (
    Contract,
    Dataset,
    FileChange,
    GlossaryTerm,
    Owner,
    PRDiff,
    RelatedEntity,
    SchemaField,
)


def test_schema_field_carries_semantics():
    f = SchemaField(
        field_path="revenue",
        native_type="int",
        description="Revenue in dollars",
        glossary_terms=[GlossaryTerm(urn="urn:li:glossaryTerm:Money", name="Money")],
    )
    assert f.field_path == "revenue"
    assert f.glossary_terms[0].name == "Money"


def test_dataset_fields_keyed_by_path():
    ds = Dataset(
        urn="urn:li:dataset:(urn:li:dataPlatform:hive,fct,PROD)",
        name="fct",
        platform="hive",
        fields={
            "revenue": SchemaField(field_path="revenue", native_type="int"),
            "user_id": SchemaField(field_path="user_id", native_type="varchar(100)"),
        },
    )
    # D7: join a changed column straight to its declared semantics
    assert ds.fields["revenue"].native_type == "int"
    assert set(ds.fields) == {"revenue", "user_id"}


def test_related_entity_and_owner():
    r = RelatedEntity(
        urn="urn:li:mlFeature:(user_features,is_premium_user)",
        entity_type="mlFeature",
        relationship="DerivedFrom",
    )
    assert r.entity_type == "mlFeature"
    assert Owner(urn="urn:li:corpuser:jdoe", username="jdoe").username == "jdoe"


def test_contract_defaults_empty_and_pr_diff_shape():
    assert Contract(urn="urn:li:assertion:x", description="rev in dollars").description
    diff = PRDiff(
        files=[FileChange(path="models/fct.sql", patch="@@ -1 +1 @@\n- revenue\n+ revenue/100")],
        raw="...",
    )
    assert diff.files[0].path.endswith(".sql")
    assert "revenue/100" in diff.files[0].patch
