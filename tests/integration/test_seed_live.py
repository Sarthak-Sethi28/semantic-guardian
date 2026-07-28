"""Live seed readback (#3) — requires local DataHub. Run: pytest -m integration."""
from __future__ import annotations

import pytest

from semantic_guardian.clients.datahub import DataHubClient

pytestmark = pytest.mark.integration

DATASET = "urn:li:dataset:(urn:li:dataPlatform:dbt,fct_revenue,PROD)"


@pytest.fixture(scope="module")
def client():
    c = DataHubClient()
    if not c.health():
        pytest.skip("Local DataHub not reachable")
    return c


@pytest.fixture(scope="module", autouse=True)
def _seed(client):
    from scenario.seed import seed

    seed()  # idempotent


def test_revenue_contract_readable(client):
    rev = client.get_dataset(DATASET).fields["revenue"]
    assert "dollars" in (rev.description or "").lower()
    assert any(t.name == "USD_Dollars" for t in rev.glossary_terms)


def test_blast_radius_target_present(client):
    ml = client.get_downstream_ml(DATASET)
    assert any("predicted_revenue" in r.urn for r in ml)


def test_seed_is_idempotent(client):
    from scenario.seed import seed

    before = len(client.get_downstream_ml(DATASET))
    seed()
    assert len(client.get_downstream_ml(DATASET)) == before
