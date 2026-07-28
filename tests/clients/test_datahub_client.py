"""DataHubClient unit tests (#2). SDK fully mocked — no network."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from semantic_guardian.clients.datahub import DataHubClient, DataHubUnavailable, EntityNotFound

DS_URN = "urn:li:dataset:(urn:li:dataPlatform:hive,fct_users_created,PROD)"


def _field(path, native, desc):
    f = MagicMock()
    f.fieldPath = path
    f.nativeDataType = native
    f.description = desc
    return f


def _make_client(graph):
    with patch("semantic_guardian.clients.datahub.DataHubGraph", return_value=graph):
        return DataHubClient(gms_url="http://x:8081", token=None)


def test_get_dataset_maps_fields_keyed_by_path():
    graph = MagicMock()
    schema = MagicMock()
    schema.fields = [
        _field("revenue", "int", "Revenue in dollars"),
        _field("user_id", "varchar(100)", "Id of user"),
    ]
    graph.get_aspect.return_value = schema
    client = _make_client(graph)

    ds = client.get_dataset(DS_URN)
    assert set(ds.fields) == {"revenue", "user_id"}
    assert ds.fields["revenue"].native_type == "int"
    assert ds.fields["revenue"].description == "Revenue in dollars"


def test_get_dataset_missing_raises_entity_not_found():
    graph = MagicMock()
    graph.get_aspect.return_value = None
    client = _make_client(graph)
    with pytest.raises(EntityNotFound):
        client.get_dataset(DS_URN)


def test_get_downstream_ml_filters_to_ml_entities():
    graph = MagicMock()
    graph.execute_graphql.return_value = {
        "entity": {
            "relationships": {
                "relationships": [
                    {"type": "DerivedFrom", "entity": {"urn": "urn:li:mlFeature:(t,is_premium)", "type": "MLFEATURE"}},
                    {"type": "DerivedFrom", "entity": {"urn": "urn:li:mlPrimaryKey:(t,user_id)", "type": "MLPRIMARYKEY"}},
                    {"type": "DownstreamOf", "entity": {"urn": "urn:li:dataset:(x,fct_users_deleted,PROD)", "type": "DATASET"}},
                    {"type": "Produces", "entity": {"urn": "urn:li:dataJob:(x,task_123)", "type": "DATA_JOB"}},
                ]
            }
        }
    }
    client = _make_client(graph)
    ml = client.get_downstream_ml(DS_URN)
    urns = {r.urn for r in ml}
    assert "urn:li:mlFeature:(t,is_premium)" in urns
    assert "urn:li:mlPrimaryKey:(t,user_id)" in urns
    # dataset + dataJob are NOT ML entities -> excluded
    assert all("dataset" not in u and "dataJob" not in u for u in urns)


def test_get_owners():
    graph = MagicMock()
    own = MagicMock()
    o1 = MagicMock(); o1.owner = "urn:li:corpuser:jdoe"; o1.type = "DATAOWNER"
    own.owners = [o1]
    graph.get_aspect.return_value = own
    client = _make_client(graph)
    owners = client.get_owners(DS_URN)
    assert owners[0].username == "jdoe"


def test_get_contracts_empty_returns_list_not_error():
    graph = MagicMock()
    graph.execute_graphql.return_value = {"entity": {"assertions": {"assertions": []}}}
    client = _make_client(graph)
    assert client.get_contracts(DS_URN) == []


def test_health_false_when_graph_raises():
    graph = MagicMock()
    graph.get_config.side_effect = RuntimeError("down")
    client = _make_client(graph)
    assert client.health() is False


def test_connect_failure_raises_datahub_unavailable():
    with patch("semantic_guardian.clients.datahub.DataHubGraph", side_effect=RuntimeError("no gms")):
        with pytest.raises(DataHubUnavailable):
            DataHubClient(gms_url="http://x:8081", token=None)
