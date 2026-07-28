"""Change trigger (#16): ingest a PR / pipeline change as the review EVENT.

The reframe's foundation — Semantic Guardian runs ON a change, not on a schedule. This
turns a diff (a PR or a local diff against the seeded repo) into a typed ReviewRequest:
the dataset in play, the per-column deltas (from the signal extractor #4, each joined to
its DataHub-declared meaning), and the changed field list. That request is the causal
event the semantic-delta engine (#5) reasons over and blast-radius (#6) acts on.

No LLM here — pure assembly. Reuses the DataHub read client + the extractor.
"""
from __future__ import annotations

from pydantic import BaseModel

from semantic_guardian.extractor import extract_snapshots
from semantic_guardian.models import ColumnDelta, PRDiff


class ReviewRequest(BaseModel):
    """The normalized review event handed to the engine (#5) and blast-radius (#6)."""

    event: str  # "local" | "pr:<n>" — where the change came from
    dataset_urn: str
    deltas: list[ColumnDelta] = []

    @property
    def changed_fields(self) -> list[str]:
        """Columns actually changed by this diff — drives targeted reasoning + impact."""
        seen: list[str] = []
        for d in self.deltas:
            if d.change.field_path not in seen:
                seen.append(d.change.field_path)
        return seen


def build_review_request(client, dataset_urn: str, diff: PRDiff, event: str) -> ReviewRequest:
    """Assemble a ReviewRequest from a diff against a dataset.

    Resolves the dataset's declared schema from DataHub, runs the signal extractor to fuse
    the diff's changed columns with their declared semantics, and bundles the result.
    """
    dataset = client.get_dataset(dataset_urn)
    deltas: list[ColumnDelta] = extract_snapshots(dataset, diff)
    return ReviewRequest(event=event, dataset_urn=dataset_urn, deltas=deltas)
