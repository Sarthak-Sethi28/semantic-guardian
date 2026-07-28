# Spec — #6: Blast-radius (downstream ML impact of a reviewed change)

- **Issue:** #6 (P0) · Uses the DataHub read client (#2). Live-verifiable. No LLM/key.
- **Status:** SPEC — rate to 10 before planning.

## Problem
When Semantic Guardian flags a semantic change to a column/dataset, the reviewer (and the owner-
routing in #7) needs to know **what it breaks**: which downstream ML features, feature tables, and
models consume it, and **who owns them**. Without this, a flagged change is a warning with no weight;
with it, it's "this ÷100 on `revenue` feeds 3 features in the churn model owned by jdoe."

## Goals
- G1. Given a changed **dataset URN** (and optionally the specific changed field), traverse DataHub
  lineage to the downstream entities that consume it: **mlFeature, mlPrimaryKey, mlFeatureTable,
  mlModel** — reusing the client's `DerivedFrom`-based `get_downstream_ml` and `get_related`.
- G2. Attach **owners** to each impacted entity (and roll up a de-duplicated set of owners to notify).
- G3. Return a typed `BlastRadius` report: the source, the impacted entities grouped by type, the
  owner set, and simple **severity** derived from impact size (how many models/features touched).
- G4. **Reach as far as the graph actually connects.** VERIFIED LIVE: in this DataHub, a dataset's
  downstream ML entities (features, primary keys) attach via `DerivedFrom` INCOMING — one hop, and it
  works. Features do **not** carry an edge to a model in the sample data (a feature's only relationship
  is back to its dataset; `scienceModel` has zero relationships). So the **core radius is dataset →
  ML features/keys**, which is real and demoable. Reaching an `mlModel` is an **optional enrichment**:
  the traversal is generic BFS (so it *will* include a model if an edge exists), and the seed (#3) can
  emit a feature→model edge to light up the full chain — but #6 is correct and tested WITHOUT it.

## Non-goals
- Deciding *whether* the change is breaking (that's the anomaly layer #18 + engine #5).
- Owner *notification/routing* (that's #7) — we produce the owner set; #7 acts on it.
- Fixing the sample-data gap where `scienceModel` has no edge to features (documented; the seed #3
  can emit that edge — but this ticket must not *depend* on it to be correct/tested).

## Key decisions
- **D1. Pure traversal over the client.** `blast_radius(client, dataset_urn, field_path=None)` calls
  the client's read methods; no direct SDK/GraphQL here. Fully unit-testable with a mocked client.
- **D2. Entity classification by URN.** `mlFeature`, `mlPrimaryKey`, `mlFeatureTable`, `mlModel` are
  identified by URN substring (matches how the client already filters). One place, reused.
- **D3. Multi-hop with a cap + visited-set.** BFS from the source over downstream relationships,
  `max_hops` default 3, cycle-safe. Stops early once no new ML entities appear. This is how we reach
  `mlModel` even when it's one hop past `mlFeature`.
- **D4. Severity is derived from structural facts, and grounded in what's reachable.** Since models
  aren't reachable in the sample graph, severity is driven by **feature impact**: any impacted `mlModel`
  → high; else impacted ML features/keys → medium (scaled by count — more downstream features = more
  exposure); nothing downstream → none. A documented table on structural facts (model? features? how
  many?), not tuned constants — and every tier is actually achievable on the real graph (medium/none
  today, high when the model edge is seeded), so severity is never theater.
- **D5. Owners fetched per impacted entity via `get_owners`, deduped into a notify-set** (urn+username).
- **D6. Degrade gracefully:** an entity with no owners → impacted but unowned (flagged, not dropped);
  DataHub unreachable → typed error bubbles from the client, not a silent empty radius.

## Interface
```
class ImpactedEntity(BaseModel): urn; entity_type; relationship; owners: list[Owner]
class BlastRadius(BaseModel):
    source_urn: str
    field_path: str | None
    impacted: list[ImpactedEntity]        # all downstream ML entities reached
    owners_to_notify: list[Owner]         # de-duplicated across impacted
    counts: dict[str,int]                 # {mlFeature: n, mlModel: n, ...}
    severity: str                         # high | medium | low | none
def blast_radius(client, dataset_urn, field_path=None, max_hops=3) -> BlastRadius
```

## Testing / acceptance
- **Unit (mocked client):**
  - dataset → 3 mlFeatures + 1 mlModel: report groups by type, counts correct, severity `high`
    (a model is touched), owners deduped across entities.
  - dataset → features only, no model: severity `medium`.
  - dataset → nothing downstream: severity `none`, empty impacted, empty notify-set.
  - **multi-hop (BFS generality):** with a mocked client where dataset →(hop1) feature →(hop2) model,
    the model IS reached — proving the traversal is real BFS, not single-hop, and will light up the
    full chain the moment the graph carries a model edge. A 4th-hop entity beyond `max_hops` is NOT
    included (cap honored). (This is the mocked-graph test; the LIVE test asserts the real one-hop
    dataset→features result, so we never claim a live capability the data doesn't have.)
  - **cycle safety:** a relationship graph with a loop terminates (visited-set), no infinite walk.
  - entity with no owners → included in `impacted`, absent from `owners_to_notify`, no crash.
- **Live integration (gated, real DataHub):** `blast_radius(client, fct_users_created_urn)` returns
  the known downstream ML features (`is_premium_user`, `number_of_visits`, …) and jdoe among owners.
- **Acceptance (issue #6):** downstream ML impact of a reviewed change is produced with owners; unit-
  tested; verified live.

## Risks
- **Traversal direction/relationship types** — verified in #2 that ML features attach via `DerivedFrom`
  INCOMING to the dataset. Plan step re-confirms the multi-hop feature→model edge shape live before
  building the BFS, so the hop logic matches reality (same "verify live before build" discipline).
- **Runaway traversal on a big graph** — `max_hops` + visited-set + early-exit; documented.
