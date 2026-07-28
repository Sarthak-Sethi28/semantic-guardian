"""Anomaly-detection layer tests (#18). Pure statistics — no LLM, no network.

These tests double as the proof that NOTHING is hardcoded: thresholds adapt to each
column's own baseline, and the meaning-preserving blind spot is asserted (that's #5's job).
"""
from semantic_guardian.anomaly import (
    AnomalySignal,
    ColumnProfile,
    detect,
    should_investigate,
)


def _p(field="revenue", **kw):
    return ColumnProfile(field_path=field, **kw)


def _kinds(signals):
    return {s.kind for s in signals}


# ── unit / scale ──────────────────────────────────────────────────────────────


def test_scale_shift_dollars_to_cents_fires():
    before = _p(median=100.0, mean=100.0, stdev=10.0, row_count=1000, null_count=0)
    after = _p(median=1.0, mean=1.0, stdev=0.1, row_count=1000, null_count=0)  # ÷100
    signals = detect(before, after)
    assert "unit_scale" in _kinds(signals)
    sig = next(s for s in signals if s.kind == "unit_scale")
    # baseline is the before value it measured against — not a constant
    assert sig.baseline == 100.0
    assert sig.observed == 1.0


def test_realistic_revenue_dollars_to_cents_escalates():
    """Realistic profile (rescaled stdev and all) still escalates — the scale detector uses
    the RATIO, so it isn't blinded by stdev rescaling the way an absolute/z test would be."""
    before = _p(row_count=50000, null_count=120, unique_count=41000,
                mean=842.5, median=610.0, stdev=930.0, min=0.0, max=48000.0)
    after = _p(row_count=50000, null_count=118, unique_count=41000,
               mean=8.425, median=6.10, stdev=9.30, min=0.0, max=480.0)
    signals = detect(before, after)
    assert "unit_scale" in _kinds(signals)
    assert should_investigate(signals) is True


def test_scale_threshold_is_data_derived_not_hardcoded():
    """Two columns, same absolute delta, different baseline variance -> different verdicts.
    Proves the threshold moves with the data (no magic constant)."""
    # low-variance column: a shift from 100 -> 90 is large relative to its tiny spread
    low_var_before = _p(median=100.0, mean=100.0, stdev=1.0, row_count=1000, null_count=0)
    low_var_after = _p(median=90.0, mean=90.0, stdev=1.0, row_count=1000, null_count=0)
    # high-variance column: the SAME 100 -> 90 shift is within its natural noise
    high_var_before = _p(median=100.0, mean=100.0, stdev=40.0, row_count=1000, null_count=0)
    high_var_after = _p(median=90.0, mean=90.0, stdev=40.0, row_count=1000, null_count=0)

    low = should_investigate(detect(low_var_before, low_var_after))
    high = should_investigate(detect(high_var_before, high_var_after))
    assert low is True and high is False, "same delta must flag differently by baseline spread"


# ── null rate ──────────────────────────────────────────────────────────────────


def test_null_rate_jump_fires():
    before = _p(row_count=1000, null_count=20)  # 2%
    after = _p(row_count=1000, null_count=600)  # 60%
    signals = detect(before, after)
    assert "null_rate" in _kinds(signals)


def test_stable_null_rate_does_not_fire():
    before = _p(row_count=1000, null_count=20)
    after = _p(row_count=1000, null_count=25)
    assert "null_rate" not in _kinds(detect(before, after))


# ── cardinality / category remap ────────────────────────────────────────────────


def test_cardinality_change_fires():
    before = _p(unique_count=5, row_count=1000)
    after = _p(unique_count=42, row_count=1000)
    assert "cardinality" in _kinds(detect(before, after))


# ── distribution drift (summary-moment proxy, no histogram needed) ───────────────


def test_distribution_mean_shift_fires_from_summary_stats():
    before = _p(mean=50.0, stdev=5.0, median=50.0, row_count=1000, null_count=0)
    after = _p(mean=95.0, stdev=5.0, median=95.0, row_count=1000, null_count=0)  # +9 sigma
    assert "distribution" in _kinds(detect(before, after))


# ── THE BLIND SPOT — must NOT fire (that's why #5 exists) ────────────────────────


def test_inverted_boolean_does_not_fire():
    """1=active -> 1=deleted: same counts, same distribution, same cardinality.
    Statistically invisible. The anomaly layer MUST stay silent here — this is the
    documented blind spot that the semantic (LLM) stage is built to catch."""
    before = _p(field="account_status", unique_count=2, row_count=1000, null_count=0,
                mean=0.5, median=0.0, stdev=0.5, min=0.0, max=1.0)
    after = _p(field="account_status", unique_count=2, row_count=1000, null_count=0,
               mean=0.5, median=0.0, stdev=0.5, min=0.0, max=1.0)  # identical stats
    signals = detect(before, after)
    assert signals == [], "meaning-preserving change must not fire statistically"
    assert should_investigate(signals) is False


# ── graceful degradation ─────────────────────────────────────────────────────────


def test_missing_stats_skips_checks_no_crash():
    before = _p(field="notes")  # nothing but field_path
    after = _p(field="notes")
    assert detect(before, after) == []  # no data -> no signals, no exception


def test_new_column_low_confidence_signal_not_a_storm():
    signals = detect(None, _p(median=10.0, row_count=100))
    assert len(signals) <= 1
    if signals:
        assert signals[0].confidence < 0.5  # low-confidence "new column", not a hard flag


# ── gate ─────────────────────────────────────────────────────────────────────────


def test_should_investigate_true_on_strong_signal():
    strong = [AnomalySignal(field_path="x", kind="unit_scale", baseline=100, observed=1,
                            magnitude=99.0, confidence=0.95)]
    assert should_investigate(strong) is True


def test_should_investigate_false_on_empty():
    assert should_investigate([]) is False
