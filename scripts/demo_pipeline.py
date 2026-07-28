"""End-to-end Semantic Guardian pipeline demo (all stages, live DataHub).

Runs a real change through every stage: trigger -> anomaly -> engine -> blast radius ->
owner decision -> durable contract + remediation. The engine's LLM call is stubbed here so
the demo runs with no API key; swap in reasoners.get_reasoner() once a model is available.

Run:  python scripts/demo_pipeline.py
"""
from __future__ import annotations

import json

from semantic_guardian.anomaly import ColumnProfile, detect, should_investigate
from semantic_guardian.blast_radius import blast_radius
from semantic_guardian.clients.datahub import DataHubClient
from semantic_guardian.clients.git import GitClient
from semantic_guardian.contract import compile_contract, propose_remediation
from semantic_guardian.decision import OwnerDecision, apply_decision, build_packet
from semantic_guardian.engine import reason_about_change
from semantic_guardian.trigger import build_review_request

URN = "urn:li:dataset:(urn:li:dataPlatform:dbt,fct_revenue,PROD)"


class _StubReasoner:
    """Stands in for Bedrock/Anthropic until a model is available (see reasoners.py)."""

    def reason(self, prompt: str) -> str:
        return json.dumps({
            "classification": "breaking",
            "change_class": "unit_scale",
            "explanation": "revenue divided by 100 breaks the declared USD-dollars contract",
            "hypotheses": ["dollars->cents unit change", "intentional rescale"],
            "confidence": {"code": 0.95, "catalog": 0.9, "stats": 0.0},
        })


def main() -> int:
    client = DataHubClient()

    req = build_review_request(
        client, URN, GitClient().get_local_diff("scenario/changes/unit_scale.diff"), event="local"
    )
    print(f"1 TRIGGER  : {req.event}  changed={req.changed_fields}")

    before = ColumnProfile(field_path="revenue", mean=842, median=610, stdev=930,
                           row_count=50000, null_count=120)
    after = ColumnProfile(field_path="revenue", mean=8.4, median=6.1, stdev=9.3,
                          row_count=50000, null_count=118)
    sigs = detect(before, after)
    print(f"2 ANOMALY  : investigate={should_investigate(sigs)} ({sigs[0].kind if sigs else '-'})")

    # Use the real model if a provider is configured, else the stub (offline demo).
    try:
        from semantic_guardian.reasoners import get_reasoner
        reasoner = get_reasoner()
    except Exception:
        reasoner = _StubReasoner()
    finding = reason_about_change(reasoner, req.deltas[0])
    print(f"3 ENGINE   : {finding.classification} / {finding.change_class}")
    print(f"           : {finding.explanation[:110]}")

    br = blast_radius(client, URN)
    print(f"4 BLAST    : severity {br.severity}, impacted {sum(br.counts.values())}")

    packet = build_packet(finding, br)
    resolved = apply_decision(packet, OwnerDecision(
        verdict="breaking", decided_by="jdoe",
        correct_semantics="revenue must stay in USD dollars (not cents)",
    ))
    print(f"5 DECISION : {resolved.classification} (human-validated)")

    aurn = compile_contract(client, URN, resolved, platform="dbt")
    patch = propose_remediation(resolved, req.deltas[0].change.before_expr,
                                req.deltas[0].change.after_expr)
    print(f"6 CONTRACT : {aurn}  fix={patch.suggested_after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
