"""Blast-radius tests (#6). Client is mocked — no network. Pure traversal logic."""
from unittest.mock import MagicMock

from semantic_guardian.blast_radius import (
    BlastRadius,
    _severity,
    blast_radius,
)
from semantic_guardian.models import Owner, RelatedEntity

DS = "urn:li:dataset:(urn:li:dataPlatform:hive,fct_users_created,PROD)"
FEAT1 = "urn:li:mlFeature:(user_features,is_premium_user)"
FEAT2 = "urn:li:mlFeature:(user_features,number_of_visits)"
PK = "urn:li:mlPrimaryKey:(user_features,user_id)"
MODEL = "urn:li:mlModel:(urn:li:dataPlatform:science,churn,PROD)"


# ── severity (pure) ──────────────────────────────────────────────────────────


def test_severity_high_when_model_touched():
    assert _severity({"mlModel": 1, "mlFeature": 2}) == "high"


def test_severity_medium_when_features_only():
    assert _severity({"mlFeature": 3}) == "medium"
    assert _severity({"mlPrimaryKey": 1}) == "medium"


def test_severity_none_when_empty():
    assert _severity({}) == "none"


# ── traversal (mocked client) ────────────────────────────────────────────────


def _client(graph: dict, owners: dict | None = None):
    """graph: {urn -> [RelatedEntity]} downstream. owners: {urn -> [Owner]}."""
    owners = owners or {}
    c = MagicMock()
    c.get_related.side_effect = lambda urn, types=None, direction="INCOMING": graph.get(urn, [])
    c.get_owners.side_effect = lambda urn: owners.get(urn, [])
    return c


def _rel(urn, etype):
    return RelatedEntity(urn=urn, entity_type=etype, relationship="DerivedFrom")


def test_dataset_to_features_and_model_full_report():
    graph = {
        DS: [
            _rel(FEAT1, "MLFEATURE"), _rel(FEAT2, "MLFEATURE"),
            _rel(PK, "MLPRIMARYKEY"), _rel(MODEL, "MLMODEL"),
        ],
    }
    owners = {
        FEAT1: [Owner(urn="urn:li:corpuser:jdoe", username="jdoe")],
        MODEL: [Owner(urn="urn:li:corpuser:jdoe", username="jdoe"),
                Owner(urn="urn:li:corpuser:asmith", username="asmith")],
    }
    br = blast_radius(_client(graph, owners), DS)
    assert isinstance(br, BlastRadius)
    assert br.counts.get("mlFeature") == 2
    assert br.counts.get("mlModel") == 1
    assert br.severity == "high"
    # owners deduped across entities
    names = sorted(o.username for o in br.owners_to_notify)
    assert names == ["asmith", "jdoe"]


def test_features_only_is_medium():
    graph = {DS: [_rel(FEAT1, "MLFEATURE"), _rel(FEAT2, "MLFEATURE")]}
    br = blast_radius(_client(graph), DS)
    assert br.severity == "medium"
    assert len(br.impacted) == 2


def test_nothing_downstream_is_none():
    br = blast_radius(_client({DS: []}), DS)
    assert br.severity == "none"
    assert br.impacted == []
    assert br.owners_to_notify == []


def test_multi_hop_reaches_model_via_bfs():
    """Proves BFS generality: dataset -> feature -> model reaches the model even though it's
    two hops away. (Not present in sample data, but the traversal must support it.)"""
    graph = {
        DS: [_rel(FEAT1, "MLFEATURE")],
        FEAT1: [_rel(MODEL, "MLMODEL")],
    }
    br = blast_radius(_client(graph), DS, max_hops=3)
    urns = {e.urn for e in br.impacted}
    assert FEAT1 in urns and MODEL in urns
    assert br.severity == "high"


def test_max_hops_cap_honored():
    deep = "urn:li:mlModel:(x,deep,PROD)"
    graph = {
        DS: [_rel(FEAT1, "MLFEATURE")],
        FEAT1: [_rel(MODEL, "MLMODEL")],
        MODEL: [_rel(deep, "MLMODEL")],
    }
    br = blast_radius(_client(graph), DS, max_hops=1)  # only 1 hop from source
    urns = {e.urn for e in br.impacted}
    assert FEAT1 in urns
    assert MODEL not in urns and deep not in urns  # beyond the cap


def test_cycle_terminates():
    graph = {DS: [_rel(FEAT1, "MLFEATURE")], FEAT1: [_rel(DS, "DATASET")]}  # loop back
    br = blast_radius(_client(graph), DS, max_hops=5)  # must not hang
    assert FEAT1 in {e.urn for e in br.impacted}


def test_entity_without_owner_included_but_not_notified():
    graph = {DS: [_rel(FEAT1, "MLFEATURE")]}
    br = blast_radius(_client(graph, owners={}), DS)  # no owners anywhere
    assert len(br.impacted) == 1
    assert br.owners_to_notify == []


def test_non_ml_downstream_excluded_from_impact():
    other_ds = "urn:li:dataset:(x,fct_del,PROD)"
    graph = {DS: [_rel(FEAT1, "MLFEATURE"), _rel(other_ds, "DATASET")]}
    br = blast_radius(_client(graph), DS)
    urns = {e.urn for e in br.impacted}
    assert FEAT1 in urns
    assert other_ds not in urns  # a downstream dataset isn't ML impact
