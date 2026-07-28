# Spec — Issue #3: Seed scenario (dbt-style repo + DataHub graph + change fixtures)

- **Issue:** #3 (P0) · Depth-first: land the **unit/scale (dollars→cents)** scenario end to end;
  scaffold the other two fixtures (null↔sentinel, categorical remap) as diffs but don't wire their
  contracts until we broaden.
- **Status:** SPEC — rate before planning.

## Problem
The agent reviews a *code change* against *approved semantics*. To build and demo that, we need a
reproducible world: (a) a small pipeline repo whose changes arrive as real diffs, and (b) a DataHub
graph carrying the declared semantics (a **contract**: "revenue is USD dollars") and the
data→feature lineage for blast radius. Without this substrate nothing downstream can run.

## Goals
- G1. A tiny **dbt-style SQL repo** under `scenario/pipeline/` producing a `fct_revenue` model with a
  `revenue` column, so the dollars→cents change is a real unified diff.
- G2. A **seed script** (`scenario/seed.py`) that idempotently emits into local DataHub: the
  `fct_revenue` dataset + schema, a **glossary term / contract** declaring `revenue` = USD dollars,
  and a **dataset→mlFeature** lineage edge so blast radius has a downstream target.
- G3. **Before/after change fixtures** as unified diffs under `scenario/changes/`:
  1. `unit_scale.diff` — adds `/ 100` to `revenue` (the demo hero). **Fully wired.**
  2. `null_sentinel.diff` — `COALESCE(x, 0)` (scaffold; contract wired when we broaden).
  3. `categorical_remap.diff` — inverts a CASE (scaffold).
  4. `benign.diff` — a legitimate change (negative control: e.g. add a comment / rename alias).
- G4. **One command** (`semantic-guardian seed` or `python scenario/seed.py`) sets up the graph
  idempotently; re-running doesn't duplicate or error.

## Non-goals (this pass)
- Column profiles/value distributions — our thesis is diff-evidence, not stats (consistent with #2's
  deferral). Skip unless #5 needs corroboration.
- Full feature→model→deployment chain — one dataset→feature edge is enough to demo blast radius; the
  model edge is a nice-to-have we add only if time allows (findings note scienceModel has no edges).
- The other two change classes fully wired — depth-first on unit/scale.

## Key decisions
- **D1. Reuse the existing sample datasets where possible, add one clean demo dataset.** The sample
  `fct_users_created` is deliberately messy (booleans typed varchar) — good for realism but noisy for
  a first demo. We emit a *new* `fct_revenue` dataset we fully control, so the dollars→cents story is
  crisp. Lineage edge points at an existing/new mlFeature.
- **D2. The contract is a glossary term + description**, emitted via the SDK, attached to the
  `revenue` field: term `Money.USD_Dollars` + field description "Revenue in USD dollars (not cents)".
  This is what #2's `get_glossary_terms` / `SchemaField.description` reads back — closing the loop.
- **D3. Fixtures are committed unified diffs**, readable by #2's `GitClient.get_local_diff`. The
  `unit_scale.diff` reuses the shape already in `tests/fixtures/sample.diff`, promoted into the
  scenario as the canonical demo input.
- **D4. Idempotent seed:** emit via `DataHubGraph.emit_mcp`; re-running upserts the same URNs (DataHub
  aspects are last-write-wins), so no duplication. Script prints what it wrote and verifies readback.
- **D5. Scenario lives in `scenario/`** (not `src/`), since it's demo substrate, not library code.
- **D6. Emit capability is proven (not assumed).** Verified live before speccing the seed: emitting a
  `DatasetPropertiesClass` via `emit_mcp` succeeds and reads back on the local GMS, and
  `hard_delete_entity` cleans up. So `seed.py` uses `emit_mcp` with confidence; the write risk is
  retired.
- **D7. Blast-radius target = a NEW, believable feature we emit.** Rather than borrow the unrelated
  `is_premium_user`, seed emits an `mlFeature` `revenue_forecast.predicted_revenue` and a
  `DerivedFrom` edge `fct_revenue.revenue → predicted_revenue`. This makes the demo causal and
  self-explanatory: "changing revenue's unit breaks the revenue-forecast feature." Owner set to a
  corpuser so routing (#7) has a real target.
- **D8. The negative control is unambiguously benign.** `benign.diff` is a **comment + whitespace
  only** change to `fct_revenue.sql` (no column expression touched), so a correct agent MUST pass it.
  A rename/alias is explicitly avoided — it could read as a semantic change and muddy the
  false-positive story.

## Architecture / flow
```
scenario/
  pipeline/models/fct_revenue.sql      # the "before" state (revenue in dollars)
  changes/unit_scale.diff              # dollars -> cents  (hero)
  changes/null_sentinel.diff           # scaffold
  changes/categorical_remap.diff       # scaffold
  changes/benign.diff                  # negative control
  seed.py                              # emit dataset + contract + lineage, idempotent

seed.py ──emit_mcp──► DataHub :8081 :  fct_revenue dataset + schema
                                        + glossary term Money.USD_Dollars on revenue
                                        + description "USD dollars (not cents)"
                                        + DerivedFrom edge -> mlFeature (blast-radius target)
then readback via DataHubClient (#2) to VERIFY it's queryable.
```

## Testing / acceptance
- **Idempotency test:** run seed twice; second run adds no new entities (asserted by reading back
  counts / the specific URN's aspects), exit 0 both times.
- **Readback test (integration, gated):** after seed, `DataHubClient.get_dataset(fct_revenue)` shows
  the `revenue` field with the USD description; `get_glossary_terms`/field terms include the USD term;
  `get_downstream_ml` returns the seeded feature edge.
- **Fixture test (unit):** `GitClient.get_local_diff(scenario/changes/unit_scale.diff)` parses to a
  `PRDiff` whose patch contains `revenue / 100`; benign.diff parses and contains no semantic change to
  a contracted column.
- **Acceptance (issue):**
  - [ ] One command seeds DataHub + repo state idempotently
  - [ ] `revenue` USD contract + dataset→feature lineage queryable via the #2 client
  - [ ] unit_scale + benign fixtures are real diffs the agent can read (other two scaffolded)

## Risks
- **Emit API shape / MCP builder** — RETIRED (D6): verified `emit_mcp(DatasetPropertiesClass)` writes
  and reads back live, with `hard_delete_entity` cleanup.
- **Token write permission** — confirmed writable on local quickstart (D6). Seed still prints a clear
  error pointing at `datahub init` if a future write is rejected.
- **mlFeature edge direction** — #2 confirmed features attach via `DerivedFrom` INCOMING to the
  dataset; seed emits the matching upstreamLineage on the new `predicted_revenue` feature so
  `get_downstream_ml(fct_revenue)` returns it (verify in the readback test).
