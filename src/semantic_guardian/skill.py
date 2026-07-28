"""Semantic Guardian as a reusable DataHub Skill (#12).

One entrypoint — `review_change` — composes the whole workflow so another team can drop
it into their own DataHub agent: ingest a change, extract the semantic delta, reason about
meaning, compute blast radius, and (only when asked) write findings back to the graph.

Reusable by construction: it takes a DataHub client + a reasoner (any `LLMReasoner`) as
arguments, so it's decoupled from our app wiring. `SKILL` is the manifest a DataHub agent
registers. Write-back is human-gated by default — the Skill reports; a human approves.
"""
from __future__ import annotations

from pydantic import BaseModel

from semantic_guardian.blast_radius import BlastRadius, blast_radius
from semantic_guardian.contract import compile_contract
from semantic_guardian.engine import Finding, reason_about_change
from semantic_guardian.models import PRDiff
from semantic_guardian.trigger import build_review_request
from semantic_guardian.writeback import write_back


class SkillResult(BaseModel):
    event: str
    dataset_urn: str
    changed_fields: list[str] = []
    findings: list[Finding] = []
    blast_radius: BlastRadius | None = None
    escalated: bool = False  # did anything reach 'breaking'?
    wrote_back: bool = False
    contract_urns: list[str] = []


def review_change(
    client,
    dataset_urn: str,
    diff: PRDiff,
    reasoner,
    event: str = "local",
    write_back_on_breaking: bool = False,
    platform: str = "dbt",
) -> SkillResult:
    """Run the full semantic-review workflow for a change. The single Skill entrypoint.

    write_back_on_breaking is False by default: the Skill REPORTS; a human approves before
    anything is written to the graph (see the owner-decision layer, #7).
    """
    req = build_review_request(client, dataset_urn, diff, event=event)
    result = SkillResult(
        event=req.event, dataset_urn=dataset_urn, changed_fields=req.changed_fields
    )
    if not req.deltas:
        return result

    findings = [reason_about_change(reasoner, d) for d in req.deltas]
    result.findings = findings
    result.escalated = any(f.classification == "breaking" for f in findings)

    # only compute impact when something is actually breaking — keep the Skill cheap otherwise
    if result.escalated:
        result.blast_radius = blast_radius(client, dataset_urn)

    if write_back_on_breaking and result.escalated:
        for f in findings:
            if f.classification != "breaking":
                continue
            write_back(
                client, dataset_urn,
                tags=["semantic-shift", "needs-review"],
                summary=f.explanation,
                incident_title=f"semantic shift in {f.field_path}",
            )
            urn = compile_contract(client, dataset_urn, f, platform=platform)
            if urn:
                result.contract_urns.append(urn)
        result.wrote_back = True

    return result


# The Skill manifest a DataHub agent registers (name/description/inputs), per the skills spec.
SKILL = {
    "name": "semantic-guardian",
    "description": (
        "Reviews a pipeline change against a dataset's DataHub-declared semantics and flags "
        "silent meaning changes (unit/scale, null/sentinel, categorical remap) with evidence, "
        "blast radius, and a durable contract — before the change merges."
    ),
    "entrypoint": "semantic_guardian.skill:review_change",
    "inputs": {
        "dataset_urn": "URN of the changed dataset",
        "diff": "the code change (PRDiff)",
        "reasoner": "an LLMReasoner (Bedrock/Anthropic)",
        "write_back_on_breaking": "bool — write findings to the graph (default false, human-gated)",
    },
}
