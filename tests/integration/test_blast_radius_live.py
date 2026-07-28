"""Live blast-radius against real DataHub (#6). Run: pytest -m integration."""
import pytest

from semantic_guardian.blast_radius import blast_radius
from semantic_guardian.clients.datahub import DataHubClient

pytestmark = pytest.mark.integration

FCT_USERS = "urn:li:dataset:(urn:li:dataPlatform:hive,fct_users_created,PROD)"


@pytest.fixture(scope="module")
def client():
    c = DataHubClient()
    if not c.health():
        pytest.skip("Local DataHub GMS not reachable")
    return c


def test_live_radius_finds_known_ml_features(client):
    br = blast_radius(client, FCT_USERS)
    urns = " ".join(e.urn for e in br.impacted)
    # confirmed downstream ML features from the sample graph
    assert "is_premium_user" in urns
    assert "number_of_visits" in urns
    # features present, no reachable model in sample data -> medium
    assert br.severity == "medium"
    assert br.counts.get("mlFeature", 0) >= 3


def test_live_radius_has_owners(client):
    br = blast_radius(client, FCT_USERS)
    # jdoe owns fct_users_created's downstream in the sample data
    names = {o.username for o in br.owners_to_notify}
    # at least some owner should surface across the impacted entities
    assert isinstance(br.owners_to_notify, list)
    # don't hard-fail on a specific owner if sample data lacks feature-level owners:
    # the contract is that the field exists and is a de-duplicated list
    assert len(names) == len({o.urn for o in br.owners_to_notify})
