# Spec — #18: Anomaly-detection pre-filter (two-stage, Jeevan's idea)

- **Issue:** #18 (P0) · Pure statistics, **no LLM / no API key.** · Credit: Jeevan.
- **Status:** SPEC — rate before planning.

## Problem
Semantic Guardian's reasoning (LLM + blast radius + human validation) is expensive — can't run on
every column of every change continuously. We need a **cheap first stage** that decides *when* the
expensive reasoning is worth invoking. Two-stage: (1) this layer flags suspicious profile shifts
cheaply and continuously; (2) #5 does the expensive meaning-reasoning only on what this escalates.

## Goals
- G1. Given a column's **before** and **after** profile, detect statistical symptoms of the change
  classes: **unit/scale shift, null-rate shift, cardinality/category remap, distribution drift.**
- G2. Emit a typed `AnomalySignal` per fired check: the check, the **data-derived baseline** it was
  measured against, the observed value, the magnitude, and a confidence — **not a verdict** (#5 judges).
- G3. A `should_investigate(signals)` gate → whether to escalate to Semantic Guardian.
- G4. Explicitly own the **blind spot**: a meaning-preserving-distribution change (e.g. an inverted
  boolean `1=active`→`1=deleted`) will NOT fire here — same counts, same distribution. Documented,
  because that blind spot is *exactly* why the LLM stage exists. This honesty is a selling point.

## THE non-negotiable: nothing hardcoded
Every threshold is **derived from the data**, never a literal magic number:
- **Scale shift:** ratio of after-median to before-median (or mean); flagged when the ratio departs
  from 1 by more than a band derived from the before-profile's own variation — not `if >100`.
- **Null-rate shift:** compared against the before-profile's null rate; flagged on a relative jump.
- **Cardinality/remap:** distinct-count and value-set change measured against the before-profile.
- **Distribution drift:** two-tier, because real DataHub `DatasetFieldProfile` usually gives summary
  stats (mean/median/stdev/min/max) but NOT a full histogram. (a) **Always-available proxy:** a
  standardized shift of the summary moments — e.g. change in mean measured in units of the before
  profile's own stdev (a z-like statistic), plus a spread-ratio (after-stdev / before-stdev). Both
  are computed from stats we reliably have. (b) **PSI (best-effort):** only when `sample_values` /
  histograms exist on both sides; skipped cleanly otherwise. This guarantees the distribution check
  actually fires on real DataHub profiles instead of being dead code.
- The **only** tunable is a single sensitivity `z`/`sigma` multiplier, and even that is applied to a
  **data-derived spread**, documented, and asserted in tests to adapt per-column (two columns with
  different variance flag at different absolute deltas). A judge can see it learns, not memorizes.

## Non-goals
- The expensive reasoning (#5) · trigger plumbing (#16) · fetching profiles (caller passes them in).
- Perfect statistics — this is a *cheap gate*, tuned for recall (don't miss), #5 handles precision.

## Key decisions
- **D1. Pure function over profiles.** Input: two `ColumnProfile` (typed). Output:
  `list[AnomalySignal]`. No I/O, no DataHub import — fully unit-testable with fixtures. (The real
  profiles come from DataHub/#4; this layer doesn't care where they're from.)
- **D2. `ColumnProfile`** carries what real DataHub `DatasetFieldProfile` provides: `null_count`,
  `unique_count`, `min`/`max`/`mean`/`median`/`stdev`, `sample_values`, `row_count`. All optional —
  degrade gracefully when a stat is absent (skip that check, don't crash).
- **D3. Baseline from the before-profile.** Each detector measures the after against the before's own
  stats. When no before exists (new column), emit a low-confidence "new column" signal rather than
  false-flag.
- **D4. Confidence = how far past the data-derived band**, normalized 0–1 — feeds the gate, not a verdict.
- **D5. `should_investigate`** escalates if any signal's confidence ≥ a documented sensitivity, OR
  multiple weak signals co-occur. Sensitivity is a single named constant, justified, not per-class magic.

## Interface
```
class ColumnProfile(BaseModel): field_path; row_count; null_count; unique_count;
    min; max; mean; median; stdev; sample_values: list
class AnomalySignal(BaseModel): field_path; kind; baseline; observed; magnitude; confidence; note
def detect(before: ColumnProfile, after: ColumnProfile) -> list[AnomalySignal]
def should_investigate(signals: list[AnomalySignal]) -> bool
```

## Testing / acceptance
- **scale:** before median≈100, after≈1 (÷100) → `unit_scale` signal; baseline recorded; **and** a
  column with naturally high variance does NOT flag on the same absolute delta (proves data-derived).
- **null-rate:** before 2% nulls, after 60% → `null_rate` signal.
- **cardinality/remap:** distinct set changes materially → `cardinality`/`category_remap` signal.
- **distribution drift:** mean shifts by several before-stdevs → `distribution` signal via the
  summary-moment proxy (works with no histogram); PSI path tested separately when sample_values given.
- **blind spot (must pass):** inverted boolean (same counts + same distribution) → **no signal fires**;
  a test asserts this and documents that #5 is what catches it.
- **missing stats:** partial profile → relevant checks skipped, no crash.
- **new column:** no before → single low-confidence signal, not a false positive storm.
- **no hardcoded magic:** a test asserts two columns with different baselines flag at different absolute
  values (the threshold moved with the data).
- **Acceptance (issue #18):** all boxes in the issue; pure/no-LLM; fully unit-tested.

## Risks
- **Over-flagging** (cheap gate) — acceptable by design (tuned for recall; #5 filters). Documented.
- **PSI/divergence needs binning** — use a simple, standard, data-derived binning; test determinism.
