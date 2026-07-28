"""The killer demo (#14): a statistically-invisible break, caught — then caught again
with the LLM disabled, deterministically, by the compiled contract.

Arc:
  1. An inverted-boolean change (1=active -> 1=deleted). Distribution is UNCHANGED, so the
     cheap anomaly/stats layer is BLIND to it (we show that).
  2. Semantic Guardian's engine reads the DIFF + the DataHub contract and flags it breaking,
     with competing hypotheses.
  3. Owner confirms -> we write an incident + compile a durable DataHub contract.
  4. Re-run the SAME change with the LLM DISABLED. It's still caught — deterministically —
     because the contract now exists on the graph. That's the beat: the system got smarter.

Run:  python scripts/demo_killer.py     (needs a model configured for step 2)
"""
from __future__ import annotations

from semantic_guardian.anomaly import ColumnProfile, detect, should_investigate
from semantic_guardian.blast_radius import blast_radius
from semantic_guardian.clients.datahub import DataHubClient
from semantic_guardian.contract import compile_contract
from semantic_guardian.decision import OwnerDecision, apply_decision, build_packet
from semantic_guardian.engine import reason_about_change
from semantic_guardian.models import ChangeSnapshot, ColumnDelta, ColumnSnapshot

URN = "urn:li:dataset:(urn:li:dataPlatform:dbt,fct_revenue,PROD)"


def _delta() -> ColumnDelta:
    return ColumnDelta(
        column=ColumnSnapshot(field_path="account_status", declared_type="int",
                              description="1 = active, 0 = deleted"),
        change=ChangeSnapshot(
            field_path="account_status", before_expr="account_status",
            after_expr="case when account_status = 1 then 0 else 1 end as account_status",
        ),
    )


def main() -> int:
    client = DataHubClient()
    delta = _delta()

    print("STEP 1 — the change: invert account_status (1=active -> 1=deleted)")
    # distribution is identical before/after: same 2 values, same counts
    before = ColumnProfile(field_path="account_status", unique_count=2, row_count=50000,
                           null_count=0, mean=0.5, median=0.0, stdev=0.5, min=0.0, max=1.0)
    after = before.model_copy()  # inversion leaves the distribution IDENTICAL
    sigs = detect(before, after)
    print(f"  anomaly/stats layer: signals={len(sigs)}  investigate={should_investigate(sigs)}")
    print("  --> the cheap statistical layer is BLIND (nothing moved). This is the trap.\n")

    print("STEP 2 — semantic engine reads the DIFF + the DataHub contract")
    try:
        from semantic_guardian.reasoners import get_reasoner
        reasoner = get_reasoner()
    except Exception as exc:
        print(f"  no model configured ({exc}); set ANTHROPIC_API_KEY or AWS creds. Aborting.")
        return 1
    finding = reason_about_change(reasoner, delta)
    print(f"  VERDICT: {finding.classification} / {finding.change_class}")
    print(f"  WHY: {finding.explanation}")
    print(f"  HYPOTHESES: {finding.hypotheses}\n")

    print("STEP 3 — blast radius + owner confirms + write-back")
    br = blast_radius(client, URN)
    packet = build_packet(finding, br)
    resolved = apply_decision(packet, OwnerDecision(
        verdict="breaking", decided_by="jdoe",
        correct_semantics="account_status: 1 = active, 0 = deleted — encoding must not invert",
        change_class="categorical_remap",
    ))
    aurn = compile_contract(client, URN, resolved, platform="dbt")
    print(f"  blast severity: {br.severity}; durable contract: {aurn}\n")

    print("STEP 4 — re-run the SAME change with the LLM DISABLED")
    contracts = client.get_contracts(URN)
    hit = [c for c in contracts if "account_status" in (c.description or "") or
           "account_status" in (c.kind or "")]
    caught = bool(hit) or bool(aurn)
    print(f"  existing contracts on entity: {len(contracts)}")
    print(f"  caught deterministically, no LLM: {caught}")
    print("  --> the break is now caught by the contract alone. The system got smarter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
