"""Durable contract + remediation (#9) — the 'gets smarter each time' loop.

Once a breaking finding is validated, we do two things so the knowledge is durable:
1. compile_contract: write a DataHub custom assertion capturing the validated meaning, so
   the SAME break is caught deterministically next time — WITHOUT the LLM. Every validated
   finding makes the system rely on the model less. (upsertCustomAssertion, verified live.)
2. propose_remediation: generate a scoped, deterministic fix for the detected change class
   (reverse a /100 unit shift, drop a null-masking coalesce, ...). For classes we can't
   safely auto-reverse, we advise manual review rather than fabricate a patch.

The external "open a PR on the pipeline repo" step needs a GitHub token + target repo; this
module produces the patch + rationale (the content of that PR) and leaves the push as a seam.
"""
from __future__ import annotations

import re

import datahub.emitter.mce_builder as builder
from pydantic import BaseModel

from semantic_guardian.engine import Finding


class RemediationPatch(BaseModel):
    field_path: str
    change_class: str
    original_before: str | None = None
    broken_after: str | None = None
    suggested_after: str | None = None  # None = we won't guess; needs manual review
    rationale: str = ""


def compile_contract(client, entity_urn: str, finding: Finding, platform: str) -> str | None:
    """Write a durable DataHub assertion for a validated BREAKING finding. Returns the
    assertion URN, or None if the finding isn't breaking (nothing to enforce)."""
    if finding.classification != "breaking":
        return None
    graph = client._graph
    mutation = (
        "mutation($input:UpsertCustomAssertionInput!){ "
        "upsertCustomAssertion(urn:null, input:$input){ urn } }"
    )
    res = graph.execute_graphql(
        mutation,
        variables={
            "input": {
                "entityUrn": entity_urn,
                "type": f"Semantic contract: {finding.field_path} ({finding.change_class})",
                "description": (
                    f"Validated semantic contract for `{finding.field_path}`. "
                    f"{finding.explanation} This assertion catches a recurrence "
                    f"deterministically, without re-invoking the model."
                ),
                "fieldPath": finding.field_path,
                "platform": {"urn": builder.make_data_platform_urn(platform)},
            }
        },
    )
    return ((res or {}).get("upsertCustomAssertion") or {}).get("urn")


def propose_remediation(
    finding: Finding, before_expr: str | None, after_expr: str | None
) -> RemediationPatch:
    """Deterministically reverse the detected change class where it is safe to do so."""
    kind = finding.change_class
    patch = RemediationPatch(
        field_path=finding.field_path,
        change_class=kind,
        original_before=before_expr,
        broken_after=after_expr,
    )

    if kind == "unit_scale" and after_expr:
        # reverse a `/ N` (or `* N`) rescale. Simplest safe fix: restore the original expr.
        m = re.search(r"/\s*(\d+(\.\d+)?)", after_expr)
        if m:
            n = m.group(1)
            patch.suggested_after = f"{finding.field_path} * {n} as {finding.field_path}"
            patch.rationale = (
                f"The change divided `{finding.field_path}` by {n}, altering its unit. "
                f"Multiplying back by {n} restores the declared scale."
            )
        else:
            patch.suggested_after = before_expr
            patch.rationale = "Restore the original expression to undo the unit change."
        return patch

    if kind == "null_sentinel" and after_expr:
        # drop a coalesce/ifnull that masked NULLs with a sentinel
        patch.suggested_after = before_expr or finding.field_path
        patch.rationale = (
            "The change wrapped the column in COALESCE/IFNULL, silently replacing NULLs "
            "with a sentinel. Removing it restores genuine NULL semantics."
        )
        return patch

    if kind == "categorical_remap":
        # a remap (esp. an inversion) is meaning-dependent — do not auto-reverse blindly
        patch.suggested_after = None
        patch.rationale = (
            "A categorical remap changes encoded meaning; auto-reversing risks compounding "
            "the error. Flag for owner review with the diff evidence."
        )
        return patch

    patch.suggested_after = None
    patch.rationale = "Change class not safely auto-reversible; manual review recommended."
    return patch
