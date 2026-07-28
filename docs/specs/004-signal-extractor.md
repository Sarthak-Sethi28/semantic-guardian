# Spec — Issue #4: Signal extractor (column snapshots)

- **Issue:** #4 (P0) · Pure transformation over #2's typed models. No I/O.
- **Status:** SPEC — rate before planning.

## Problem
The delta engine (#5) needs a compact, uniform object per column that fuses two things:
1. the column's **declared semantics** from DataHub (type, description, glossary term = the contract), and
2. **what the change did to it** — extracted from the PR diff.
Without this, #5 would have to re-parse diffs and DataHub models itself. The extractor packages the
evidence so #5 only reasons.

## Goals
- G1. `ColumnSnapshot` — a typed bundle per column: `field_path`, `declared_type`, `description`,
  `glossary_terms`, and (when profiles exist) `null_rate`/`cardinality`/`min`/`max`/`mean`/`samples`.
  Profile fields are **optional** (our sample data has none; consistent with #2/#3 deferral).
- G2. `ChangeSnapshot` — for a *changed* column, what the diff did: `field_path`, `before_expr`,
  `after_expr`, and a coarse `change_kind` heuristic (`unit_scale` | `null_sentinel` |
  `categorical_remap` | `other` | `none`) derived from the diff text. This is a **hint**, not the
  verdict — #5 decides; the heuristic just routes/《corroborates.
- G3. `extract_snapshots(dataset, diff)` → for each changed column, a fused
  `ColumnDelta{column: ColumnSnapshot, change: ChangeSnapshot}` joining diff→declared-semantics by
  **field path** (D7 from #2). Columns not in the diff are ignored (we review the change, not the world).
- G4. Pure + deterministic: input is #2's `Dataset` + `PRDiff` models, output is typed models. Fully
  unit-testable with fixtures, zero network.

## Non-goals
- Fetching anything — the caller passes in the `Dataset` (from `DataHubClient`) and `PRDiff` (from
  `GitClient`). The extractor imports neither client.
- Being the classifier — `change_kind` is a cheap regex/heuristic hint; the real judgment is #5 (LLM).
- Historical profile diffing beyond a simple before/after when both snapshots are supplied (profiles
  are absent in sample data; we structure for it but don't depend on it).

## Key decisions
- **D1. Join diff→semantics by field path.** The diff yields changed column name(s) + expressions;
  we look them up in `Dataset.fields[path]` to attach the declared meaning. Unmatched columns (in
  the diff but not the schema) produce a snapshot with `declared_type=None` and
  `change_kind` still set — so a brand-new/renamed column is visible, not dropped.
- **D2. Column-change parsing, with an explicit pairing rule.** For each changed file: collect
  removed lines (`-`) and added lines (`+`). For each such line, compute its **output column name**
  = the alias after `as`, else the trailing bare identifier before the comma (so `revenue,` and
  `revenue / 100 as revenue,` both map to output col `revenue`). Pair a removed line with an added
  line **sharing the same output column name** → `before_expr` (from `-`, stripped of trailing comma)
  and `after_expr` (from `+`). This pairing rule is the crux and is tested directly. A removed line
  with no matching added line = column dropped; an added with no matching removed = column added
  (both `change_kind` heuristics still apply; `declared_type` may be None). Comment/whitespace lines
  (starting `--` or blank after the marker) are ignored, giving the benign control an empty result.
- **D3. `change_kind` heuristic** (evidence keywords, not truth):
  - `/ <n>` or `* <n>` on a numeric col → `unit_scale`
  - `coalesce(<col>, <literal>)` → `null_sentinel`
  - `case when ... then ... end` remapping values → `categorical_remap`
  - comment/whitespace-only, or no column expr change → `none`
  - else → `other`
- **D4. Pure module** `src/semantic_guardian/extractor.py`; models live in `models.py` (extend it).

## Interface
```
class ColumnSnapshot(BaseModel):
    field_path: str
    declared_type: str | None
    description: str | None
    glossary_terms: list[GlossaryTerm]
    # optional profile signal (absent in sample data)
    null_rate: float | None = None
    cardinality: int | None = None
    samples: list[str] = []

class ChangeSnapshot(BaseModel):
    field_path: str
    before_expr: str | None
    after_expr: str | None
    change_kind: str        # unit_scale | null_sentinel | categorical_remap | other | none

class ColumnDelta(BaseModel):
    column: ColumnSnapshot
    change: ChangeSnapshot

def extract_snapshots(dataset: Dataset, diff: PRDiff) -> list[ColumnDelta]: ...
```

## Testing / acceptance
- **unit_scale fixture:** `extract_snapshots(fct_revenue, unit_scale.diff)` → one `ColumnDelta` for
  `revenue` with `change_kind='unit_scale'`, `after_expr` containing `/ 100`, and the column carrying
  the USD glossary term + dollars description (proves the join to declared semantics).
- **null_sentinel fixture:** `revenue` → `change_kind='null_sentinel'`, `after_expr` has `coalesce`.
- **categorical_remap fixture:** `account_status` → `change_kind='categorical_remap'`.
- **benign fixture:** no `ColumnDelta` with a real change (comment-only → `change_kind='none'` or
  empty result). This is the false-positive guard.
- **unmatched column:** diff changes a column absent from the dataset → snapshot with
  `declared_type=None`, not dropped.
- **determinism:** same inputs → identical output (no ordering flakiness).
- **Acceptance (issue):**
  - [ ] Given a dataset + diff, produces snapshots for the changed columns
  - [ ] Produces a before/after change snapshot (before_expr/after_expr) as raw material for #5
  - [ ] Pure, no I/O, fully unit-tested with fixtures

## Risks
- **SQL parse fragility** — a real diff can be arbitrary SQL. Mitigation: scope to the demo fixtures,
  return `change_kind='other'` + raw exprs when unsure (never crash, never false-classify silently);
  #5 still gets the before/after text to reason over even when the heuristic abstains.
