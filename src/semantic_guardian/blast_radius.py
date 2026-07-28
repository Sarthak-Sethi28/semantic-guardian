"""Blast-radius (#6): downstream ML impact of a reviewed change.

Given a changed dataset, traverse DataHub lineage to the ML entities that consume it
(features, primary keys, feature tables, models) and the owners who need to know. Turns
a flagged change into "this feeds N features / a model owned by X" — the weight behind
Semantic Guardian's verdict and the input to owner routing (#7).

Reuses the DataHub read client only (no SDK here). BFS is generic so it reaches a model
whenever an edge exists; in the current sample graph the real, demoable radius is
dataset -> features/keys (one DerivedFrom hop), verified live.
"""
from __future__ import annotations

from pydantic import BaseModel

from semantic_guardian.models import Owner

# ML entity kinds we count as impact, keyed by a URN marker -> canonical type name.
_ML_KINDS = {
    "mlModel": "mlModel",
    "mlFeatureTable": "mlFeatureTable",
    "mlFeature": "mlFeature",
    "mlPrimaryKey": "mlPrimaryKey",
}
# Relationship types that carry "consumes / derived from" downstream of a dataset/feature.
_DOWNSTREAM_TYPES = ["DerivedFrom", "DownstreamOf", "Consumes", "Produces", "MemberOf", "TrainedBy"]


class ImpactedEntity(BaseModel):
    urn: str
    entity_type: str  # canonical: mlFeature | mlPrimaryKey | mlFeatureTable | mlModel
    relationship: str
    owners: list[Owner] = []


class BlastRadius(BaseModel):
    source_urn: str
    field_path: str | None = None
    impacted: list[ImpactedEntity] = []
    owners_to_notify: list[Owner] = []
    counts: dict[str, int] = {}
    severity: str = "none"  # high | medium | low | none


def _classify(urn: str) -> str | None:
    """Canonical ML entity type from a URN, or None if it isn't an ML impact entity."""
    for marker, name in _ML_KINDS.items():
        if marker in urn:
            return name
    return None


def _severity(counts: dict[str, int]) -> str:
    """Derived from structural facts, not tuned constants. A model in the radius is the
    worst case; otherwise any features/keys is a real (medium) exposure; nothing is none."""
    if counts.get("mlModel", 0) > 0:
        return "high"
    if any(counts.get(k, 0) > 0 for k in ("mlFeature", "mlPrimaryKey", "mlFeatureTable")):
        return "medium"
    return "none"


def blast_radius(
    client, dataset_urn: str, field_path: str | None = None, max_hops: int = 3
) -> BlastRadius:
    """Traverse downstream lineage from a changed dataset and report ML impact + owners.

    BFS with a hop cap and a visited-set (cycle-safe). Each hop asks the client for
    downstream related entities; ML entities are collected, classified, and their owners
    fetched and de-duplicated into a notify-set.
    """
    visited: set[str] = {dataset_urn}
    frontier = [dataset_urn]
    impacted: dict[str, ImpactedEntity] = {}

    hops = 0
    while frontier and hops < max_hops:
        next_frontier: list[str] = []
        for urn in frontier:
            for rel in client.get_related(urn, _DOWNSTREAM_TYPES, "INCOMING"):
                if rel.urn in visited:
                    continue
                visited.add(rel.urn)
                next_frontier.append(rel.urn)  # keep walking (features may lead to models)
                kind = _classify(rel.urn)
                if kind is not None and rel.urn not in impacted:
                    impacted[rel.urn] = ImpactedEntity(
                        urn=rel.urn,
                        entity_type=kind,
                        relationship=rel.relationship,
                        owners=client.get_owners(rel.urn),
                    )
        frontier = next_frontier
        hops += 1

    entities = list(impacted.values())

    counts: dict[str, int] = {}
    for e in entities:
        counts[e.entity_type] = counts.get(e.entity_type, 0) + 1

    # de-duplicate owners across all impacted entities by urn
    notify: dict[str, Owner] = {}
    for e in entities:
        for o in e.owners:
            notify.setdefault(o.urn, o)

    return BlastRadius(
        source_urn=dataset_urn,
        field_path=field_path,
        impacted=entities,
        owners_to_notify=list(notify.values()),
        counts=counts,
        severity=_severity(counts),
    )
