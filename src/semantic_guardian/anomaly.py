"""Anomaly-detection pre-filter (#18) — the cheap first stage of a two-stage model.

Credit: idea from Jeevan. This layer runs continuously and cheaply on column profiles
and decides WHEN the expensive Semantic Guardian reasoning (#5 + blast radius + human
validation) is worth invoking. It is pure statistics — no LLM, no network.

Design principle (non-negotiable): NOTHING is hardcoded. Every detector measures the
after-profile against the column's OWN before-profile (its learned baseline), and flags a
shift relative to that column's own spread — never against a literal magic number. The one
tunable is a single sensitivity multiplier applied to a data-derived spread.

It has one deliberate blind spot: a meaning-preserving-distribution change (e.g. an inverted
boolean, 1=active -> 1=deleted) is statistically invisible and will NOT fire here. That blind
spot is exactly why the semantic (LLM) stage exists.
"""
from __future__ import annotations

import math

from pydantic import BaseModel

# The ONE sensitivity knob. Applied to a data-derived spread, never to a raw value.
# A shift is notable when it exceeds this many multiples of the baseline's own variation.
_SENSITIVITY_SIGMA = 3.0
# Relative-change floor for stats that have no natural spread (null rate, cardinality):
# fraction of the baseline that counts as a material move. Documented, not per-class tuned.
_REL_CHANGE = 0.5
# Escalate to the expensive stage at/above this confidence.
_ESCALATE_AT = 0.6


class ColumnProfile(BaseModel):
    """A column's profile — mirrors what DataHub DatasetFieldProfile provides. All optional
    so we degrade gracefully when a stat is absent."""

    field_path: str
    row_count: int | None = None
    null_count: int | None = None
    unique_count: int | None = None
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    median: float | None = None
    stdev: float | None = None
    sample_values: list[str] = []


class AnomalySignal(BaseModel):
    """One fired check. A HINT that something shifted — never a verdict (that's #5)."""

    field_path: str
    kind: str  # unit_scale | null_rate | cardinality | distribution | new_column
    baseline: float | None = None  # the before value it measured against
    observed: float | None = None
    magnitude: float = 0.0  # how big the move is, in data terms
    confidence: float = 0.0  # 0..1, how far past the data-derived band
    note: str = ""


def _confidence(excess_ratio: float) -> float:
    """Map 'how many multiples past the band' -> 0..1, saturating. 1x past = ~0.5."""
    return max(0.0, min(1.0, excess_ratio / (excess_ratio + 1.0) * 2.0))


def _null_rate(p: ColumnProfile) -> float | None:
    if p.row_count and p.row_count > 0 and p.null_count is not None:
        return p.null_count / p.row_count
    return None


def _detect_scale(before: ColumnProfile, after: ColumnProfile) -> AnomalySignal | None:
    """Scale/unit shift: the RATIO of central values departs from 1 by a whole order of
    magnitude or more. Ratio is the right lens for a unit change (dollars->cents = ~100x)
    because when a column is rescaled its stdev rescales too, so an absolute/stdev test is
    blind to it — that's exactly the case the distribution detector can't see either.

    Data-derived: the ratio comes entirely from the two profiles; we flag when it leaves the
    'same order of magnitude' band (0.5x .. 2x), i.e. |log10(ratio)| exceeds a fraction of a
    decade. No absolute magic number about the values themselves."""
    b, a = before.median, after.median
    if b is None or a is None or b == 0 or a == 0:
        b, a = before.mean, after.mean  # fall back to mean if median missing/zero
        if b is None or a is None or b == 0 or a == 0:
            return None
    ratio = a / b
    if ratio <= 0:
        return None
    decades = abs(math.log10(ratio))  # 0 = unchanged, 1 = 10x, 2 = 100x
    # A move within the same order of magnitude (< ~0.3 decades ≈ 2x) is not a scale change.
    if decades < 0.3:
        return None
    excess = (decades - 0.3) / 0.3
    return AnomalySignal(
        field_path=after.field_path, kind="unit_scale", baseline=float(b),
        observed=float(a), magnitude=ratio,
        confidence=_confidence(excess),
        note=f"central value {b:.3g} -> {a:.3g} ({ratio:.3g}x, ~{decades:.1f} orders of magnitude)",
    )


def _detect_null_rate(before: ColumnProfile, after: ColumnProfile) -> AnomalySignal | None:
    nb, na = _null_rate(before), _null_rate(after)
    if nb is None or na is None:
        return None
    # material relative jump against the column's own baseline null rate
    ref = max(nb, 0.01)  # avoid div-by-zero; a jump from ~0 is still measured
    rel = (na - nb) / ref
    if rel <= _REL_CHANGE:
        return None
    return AnomalySignal(
        field_path=after.field_path, kind="null_rate", baseline=nb, observed=na,
        magnitude=na - nb, confidence=_confidence(rel - _REL_CHANGE + 0.5),
        note=f"null rate {nb:.1%} -> {na:.1%}",
    )


def _detect_cardinality(before: ColumnProfile, after: ColumnProfile) -> AnomalySignal | None:
    b, a = before.unique_count, after.unique_count
    if b is None or a is None or b == 0:
        return None
    rel = abs(a - b) / b
    if rel <= _REL_CHANGE:
        return None
    return AnomalySignal(
        field_path=after.field_path, kind="cardinality", baseline=float(b),
        observed=float(a), magnitude=abs(a - b),
        confidence=_confidence(rel - _REL_CHANGE + 0.5),
        note=f"distinct values {b} -> {a}",
    )


def _detect_distribution(before: ColumnProfile, after: ColumnProfile) -> AnomalySignal | None:
    """Summary-moment proxy (works with no histogram): change in mean measured in units of
    the before profile's own stdev. Standardized, data-derived — no magic constant."""
    if before.mean is None or after.mean is None:
        return None
    spread = before.stdev if before.stdev and before.stdev > 0 else None
    if spread is None:
        return None
    z = abs(after.mean - before.mean) / spread
    if z <= _SENSITIVITY_SIGMA:
        return None
    excess = (z - _SENSITIVITY_SIGMA) / _SENSITIVITY_SIGMA
    return AnomalySignal(
        field_path=after.field_path, kind="distribution", baseline=before.mean,
        observed=after.mean, magnitude=z, confidence=_confidence(excess),
        note=f"mean shifted {z:.1f} baseline-stdevs",
    )


def detect(before: ColumnProfile | None, after: ColumnProfile) -> list[AnomalySignal]:
    """Return anomaly signals for a column's before->after profile shift.

    No before-profile (new column) -> a single low-confidence 'new_column' signal, so a
    fresh column is surfaced without a false-positive storm.
    """
    if before is None:
        return [
            AnomalySignal(
                field_path=after.field_path, kind="new_column", confidence=0.3,
                note="no prior profile to baseline against",
            )
        ]
    signals: list[AnomalySignal] = []
    for detector in (_detect_scale, _detect_null_rate, _detect_cardinality, _detect_distribution):
        sig = detector(before, after)
        if sig is not None:
            signals.append(sig)
    return signals


def should_investigate(signals: list[AnomalySignal]) -> bool:
    """Gate: escalate to the expensive semantic stage (#5) when warranted.

    Escalate if any single signal is confident enough, OR two+ weaker signals co-occur
    (corroboration). Both use the one documented sensitivity, not per-class magic.
    """
    if not signals:
        return False
    real = [s for s in signals if s.kind != "new_column"]
    if any(s.confidence >= _ESCALATE_AT for s in real):
        return True
    return len([s for s in real if s.confidence >= _ESCALATE_AT / 2]) >= 2
