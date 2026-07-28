# Plan — #6 Blast-radius

Spec: `006-blast-radius.md`. Branch `feat/6-blast-radius`. TDD, small commits, pause at merge.

## Verified live (before building)
- Dataset → ML features/keys via `DerivedFrom` INCOMING — works (7 entities on fct_users_created).
- Feature → model edge: does NOT exist in sample data (feature only points back to its dataset).
- So: core = one-hop dataset→features; BFS stays generic for models but isn't required to pass.

## Files
```
src/semantic_guardian/blast_radius.py     # ImpactedEntity, BlastRadius, blast_radius(), severity
tests/test_blast_radius.py                # unit, mocked client
tests/integration/test_blast_radius_live.py  # gated, real DataHub
```
(Owner/RelatedEntity already in models.py; reuse.)

## Steps (each = 1 commit, test-first)

**Step 1 — models + severity (commit: `feat(blast): typed impact report + derived severity (#6)`)**
- Test: `ImpactedEntity`, `BlastRadius` construct; `_severity(counts)` → high if mlModel>0, medium if
  features/keys>0, none if empty; scales note by count. Pure, no client.
- Then: models in `blast_radius.py` + `_severity`.

**Step 2 — traversal (commit: `feat(blast): BFS lineage traversal + owners (#6)`)**
- Test (mocked client): client.get_related returns downstream by urn; BFS from dataset collects ML
  entities (features/keys), classifies by URN, dedupes owners via client.get_owners; multi-hop mock
  (dataset→feature→model) reaches model; max_hops cap honored; cycle terminates; no-owner entity
  included but not in notify-set; empty downstream → severity none.
- Then: `blast_radius(client, urn, field_path=None, max_hops=3)` — BFS with visited-set, per-node
  get_related (INCOMING DerivedFrom + the downstream types), classify, fetch owners, build report.

**Step 3 — live integration (commit: `test(blast): gated live radius on real DataHub (#6)`)**
- `-m integration`: blast_radius(real client, fct_users_created) → known features present, jdoe in
  owners, severity medium (features, no model). Skips if GMS down.

**Step 4 — verify + demo (commit: `chore(blast): green + ruff/mypy (#6)` if needed)**
- ruff + mypy clean; full test run; a quick live print of the radius for the demo record.

## Definition of done
Spec acceptance boxes checked; unit + live green; ruff+mypy clean; PR opened referencing #6
(does not close until batch-merge). Reuses client only — no SDK here.
