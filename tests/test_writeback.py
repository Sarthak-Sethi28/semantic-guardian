"""Write-back tests (#8). SDK/graph mocked — no network. Verifies the calls made."""
from unittest.mock import MagicMock, patch

from semantic_guardian.writeback import WriteBackResult, write_back


def _client():
    """A DataHubClient stand-in exposing the raw graph for emit/graphql."""
    c = MagicMock()
    c._graph = MagicMock()
    c._graph.execute_graphql.return_value = {"raiseIncident": "urn:li:incident:abc"}
    return c


DS = "urn:li:dataset:(urn:li:dataPlatform:dbt,fct_revenue,PROD)"


def test_write_back_tags_and_incident():
    client = _client()
    with patch("semantic_guardian.writeback.MetadataChangeProposalWrapper") as MCP:
        res = write_back(
            client, DS,
            tags=["semantic-shift", "needs-review"],
            summary="revenue changed from dollars to cents",
            incident_title="revenue unit change",
        )
    assert isinstance(res, WriteBackResult)
    # a tags aspect was emitted
    assert client._graph.emit_mcp.called
    assert MCP.called
    # an incident was raised
    assert res.incident_urn == "urn:li:incident:abc"
    assert set(res.tags_applied) == {"semantic-shift", "needs-review"}


def test_write_back_incident_uses_custom_type():
    client = _client()
    with patch("semantic_guardian.writeback.MetadataChangeProposalWrapper"):
        write_back(client, DS, tags=[], summary="x", incident_title="t")
    # the raiseIncident mutation must send customType (live GMS requires it for CUSTOM)
    _, kwargs = client._graph.execute_graphql.call_args
    inp = kwargs["variables"]["input"]
    assert inp["type"] == "CUSTOM"
    assert inp["customType"]
    assert inp["resourceUrn"] == DS


def test_write_back_no_incident_when_title_none():
    client = _client()
    with patch("semantic_guardian.writeback.MetadataChangeProposalWrapper"):
        res = write_back(client, DS, tags=["semantic-shift"], summary="x", incident_title=None)
    assert res.incident_urn is None
    assert client._graph.execute_graphql.call_count == 0  # no incident mutation


def test_write_back_incident_failure_is_captured_not_raised():
    client = _client()
    client._graph.execute_graphql.side_effect = RuntimeError("gms down")
    with patch("semantic_guardian.writeback.MetadataChangeProposalWrapper"):
        res = write_back(client, DS, tags=["semantic-shift"], summary="x", incident_title="t")
    # tags still applied; incident failure recorded, not crashed
    assert res.tags_applied == ["semantic-shift"]
    assert res.incident_urn is None
    assert res.errors and "gms down" in res.errors[0]


def test_write_back_empty_tags_skips_tag_but_still_sets_description():
    client = _client()
    res = write_back(client, DS, tags=[], summary="revenue is USD dollars", incident_title=None)
    # no tags applied, but the validated meaning is still written as a description
    assert res.tags_applied == []
    assert res.description_set is True
