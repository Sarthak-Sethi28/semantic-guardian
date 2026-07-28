"""Live integration test (#2) — requires a running local DataHub on :8081.

Run with:  pytest -m integration
Skipped automatically if GMS is unreachable, so the default suite stays offline.
"""
from __future__ import annotations

import pytest

from semantic_guardian.clients.datahub import DataHubClient

pytestmark = pytest.mark.integration

FCT_USERS = "urn:li:dataset:(urn:li:dataPlatform:hive,fct_users_created,PROD)"


@pytest.fixture(scope="module")
def client():
    c = DataHubClient()
    if not c.health():
        pytest.skip("Local DataHub GMS not reachable on :8081")
    return c


def test_health_true(client):
    assert client.health() is True


def test_get_dataset_has_known_fields(client):
    ds = client.get_dataset(FCT_USERS)
    assert "user_id" in ds.fields
    assert "user_name" in ds.fields


def test_downstream_ml_features_present(client):
    ml = client.get_downstream_ml(FCT_USERS)
    urns = " ".join(r.urn for r in ml)
    # confirmed ML features from docs/datahub-environment-findings.md
    assert "is_premium_user" in urns
    assert "number_of_visits" in urns
    assert all(r.relationship for r in ml)


def test_owners_present(client):
    owners = {o.username for o in client.get_owners(FCT_USERS)}
    assert "jdoe" in owners
