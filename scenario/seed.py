"""Seed the Semantic Guardian demo world into local DataHub (#3).

Idempotent: emits the fct_revenue dataset + schema, a USD-dollars CONTRACT on the
`revenue` column (glossary term + field description), and a downstream mlFeature
(`predicted_revenue`) linked by DerivedFrom so blast radius has a real target.

Run:  python scenario/seed.py         (uses ~/.datahubenv / env, defaults to :8081)
Re-running upserts the same URNs (aspects are last-write-wins) — no duplicates.
"""
from __future__ import annotations

import sys

import datahub.emitter.mce_builder as builder
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.ingestion.graph.client import DatahubClientConfig, DataHubGraph
from datahub.metadata.schema_classes import (
    AuditStampClass,
    DatasetPropertiesClass,
    EditableSchemaFieldInfoClass,
    EditableSchemaMetadataClass,
    GlossaryTermAssociationClass,
    GlossaryTermInfoClass,
    GlossaryTermsClass,
    MLFeaturePropertiesClass,
    NumberTypeClass,
    OtherSchemaClass,
    SchemaFieldClass,
    SchemaFieldDataTypeClass,
    SchemaMetadataClass,
    StringTypeClass,
)

from semantic_guardian.config import resolve_datahub_config

PLATFORM = "dbt"
DATASET_URN = builder.make_dataset_urn(PLATFORM, "fct_revenue", "PROD")
TERM_URN = builder.make_term_urn("Money.USD_Dollars")
FEATURE_URN = builder.make_ml_feature_urn("revenue_forecast", "predicted_revenue")
REVENUE_CONTRACT = "Revenue in USD dollars (not cents)."


def _graph() -> DataHubGraph:
    cfg = resolve_datahub_config()
    return DataHubGraph(DatahubClientConfig(server=cfg.url, token=cfg.token or None))


def _now() -> AuditStampClass:
    # Fixed stamp keeps re-runs byte-identical (idempotent, no time import needed).
    return AuditStampClass(time=0, actor="urn:li:corpuser:semantic-guardian")


def _field(
    path: str, native: str, is_number: bool, desc: str, term_urn: str | None = None
) -> SchemaFieldClass:
    dt = NumberTypeClass() if is_number else StringTypeClass()
    terms = (
        GlossaryTermsClass(
            terms=[GlossaryTermAssociationClass(urn=term_urn)], auditStamp=_now()
        )
        if term_urn
        else None
    )
    return SchemaFieldClass(
        fieldPath=path,
        type=SchemaFieldDataTypeClass(type=dt),
        nativeDataType=native,
        description=desc,
        glossaryTerms=terms,
    )


def _emit(graph: DataHubGraph, urn: str, aspect) -> None:
    graph.emit_mcp(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))


def seed(graph: DataHubGraph | None = None) -> dict[str, str]:
    graph = graph or _graph()

    # 1. The glossary TERM (the contract vocabulary): revenue is USD dollars.
    _emit(
        graph,
        TERM_URN,
        GlossaryTermInfoClass(
            name="USD_Dollars",
            definition="Monetary amount expressed in whole US dollars, not cents.",
            termSource="INTERNAL",
        ),
    )

    # 2. The dataset + schema (the "before" world: revenue in dollars).
    _emit(graph, DATASET_URN, DatasetPropertiesClass(description="Per-order revenue fact."))
    _emit(
        graph,
        DATASET_URN,
        SchemaMetadataClass(
            schemaName="fct_revenue",
            platform=builder.make_data_platform_urn(PLATFORM),
            version=0,
            hash="",
            platformSchema=OtherSchemaClass(rawSchema=""),
            fields=[
                _field("order_id", "varchar(64)", False, "Order identifier."),
                _field("customer_id", "varchar(64)", False, "Customer identifier."),
                _field("revenue", "int", True, REVENUE_CONTRACT, term_urn=TERM_URN),
                _field("created_at", "timestamp", False, "Order creation time."),
            ],
        ),
    )

    # 3. Attach the CONTRACT to the revenue column: glossary term + editable description.
    _emit(
        graph,
        DATASET_URN,
        EditableSchemaMetadataClass(
            created=_now(),
            lastModified=_now(),
            editableSchemaFieldInfo=[
                EditableSchemaFieldInfoClass(
                    fieldPath="revenue",
                    description=REVENUE_CONTRACT,
                    glossaryTerms=GlossaryTermsClass(
                        terms=[GlossaryTermAssociationClass(urn=TERM_URN)],
                        auditStamp=_now(),
                    ),
                )
            ],
        ),
    )

    # 4. Downstream mlFeature (blast-radius target). `sources=[dataset]` IS the lineage:
    # it creates the DerivedFrom edge the #2 client reads via get_downstream_ml. mlFeature
    # has no separate upstreamLineage aspect (confirmed live).
    _emit(
        graph,
        FEATURE_URN,
        MLFeaturePropertiesClass(
            description="Predicted revenue; consumes fct_revenue.revenue.",
            dataType="CONTINUOUS",
            sources=[DATASET_URN],
        ),
    )

    return {"dataset": DATASET_URN, "term": TERM_URN, "feature": FEATURE_URN}


def main() -> int:
    try:
        graph = _graph()
    except Exception as exc:
        print(
            f"Cannot reach DataHub: {exc}. Is it running? Try `datahub docker quickstart`.",
            file=sys.stderr,
        )
        return 1
    urns = seed(graph)
    print("Seeded (idempotent):")
    for k, v in urns.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
