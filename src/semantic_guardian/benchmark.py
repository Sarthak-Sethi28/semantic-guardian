"""Seeded evaluation benchmark (#17) — turns 'impressive demo' into 'measured result'.

A small, LABELED suite of controlled changes (the 3 breaking classes + benign negative
controls + ambiguous cases) run through the semantic-delta engine, scored on precision,
recall, and abstention. Honest framing: this is a SEEDED suite of N hand-labeled cases —
NOT production-scale numbers. The point is a reproducible, defensible signal that the
agent flags real breaks, stays quiet on benign changes, and abstains when unsure.

The engine's reasoner is injected, so this runs with a scripted reasoner offline and with
a real model (Bedrock/Anthropic) once available — same harness either way.
"""

from __future__ import annotations

from pydantic import BaseModel

from semantic_guardian.engine import reason_about_change
from semantic_guardian.models import ChangeSnapshot, ColumnDelta, ColumnSnapshot


class BenchmarkCase(BaseModel):
    name: str
    before_expr: str
    after_expr: str
    declared: str  # the column's declared meaning (catalog description)
    expected: str  # breaking | compatible | insufficient-context
    expected_class: str  # unit_scale | null_sentinel | categorical_remap | other | unknown


class Metrics(BaseModel):
    total: int = 0
    correct: int = 0
    precision: float = 0.0  # of predicted-breaking, how many were truly breaking
    recall: float = 0.0  # of truly-breaking, how many we caught
    abstained: int = 0
    false_positives: int = 0  # benign/compatible predicted breaking
    missed: int = 0  # breaking predicted not-breaking

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


# ── the seeded, labeled suite (honest: N hand-built cases) ──────────────────────
CASES: list[BenchmarkCase] = [
    # breaking: unit / scale
    BenchmarkCase(
        name="revenue_div_100",
        before_expr="revenue",
        after_expr="revenue / 100 as revenue",
        declared="Revenue in USD dollars (not cents)",
        expected="breaking",
        expected_class="unit_scale",
    ),
    BenchmarkCase(
        name="latency_x1000",
        before_expr="latency_ms",
        after_expr="latency_ms * 1000 as latency_ms",
        declared="Latency in milliseconds",
        expected="breaking",
        expected_class="unit_scale",
    ),
    # breaking: null / sentinel
    BenchmarkCase(
        name="coalesce_zero",
        before_expr="revenue",
        after_expr="coalesce(revenue, 0) as revenue",
        declared="Revenue; NULL means not yet billed",
        expected="breaking",
        expected_class="null_sentinel",
    ),
    # breaking: categorical remap (the statistically-invisible one)
    BenchmarkCase(
        name="invert_status",
        before_expr="account_status",
        after_expr="case when account_status = 1 then 0 else 1 end as account_status",
        declared="1 = active, 0 = deleted",
        expected="breaking",
        expected_class="categorical_remap",
    ),
    # compatible: benign negative controls
    BenchmarkCase(
        name="add_comment",
        before_expr="revenue",
        after_expr="revenue -- keep in dollars",
        declared="Revenue in USD dollars",
        expected="compatible",
        expected_class="other",
    ),
    BenchmarkCase(
        name="rename_alias_same_meaning",
        before_expr="revenue as revenue",
        after_expr="revenue as revenue_amount",
        declared="Revenue in USD dollars",
        expected="compatible",
        expected_class="other",
    ),
    BenchmarkCase(
        name="whitespace_only",
        before_expr="revenue",
        after_expr="  revenue  ",
        declared="Revenue in USD dollars",
        expected="compatible",
        expected_class="other",
    ),
    # ambiguous: should abstain
    BenchmarkCase(
        name="opaque_udf",
        before_expr="revenue",
        after_expr="adjust(revenue) as revenue",
        declared="Revenue in USD dollars",
        expected="insufficient-context",
        expected_class="unknown",
    ),
    BenchmarkCase(
        name="unknown_transform",
        before_expr="score",
        after_expr="recalibrate(score) as score",
        declared="",
        expected="insufficient-context",
        expected_class="unknown",
    ),
]


def _delta(case: BenchmarkCase) -> ColumnDelta:
    field = case.name
    return ColumnDelta(
        column=ColumnSnapshot(field_path=field, declared_type="unknown", description=case.declared),
        change=ChangeSnapshot(
            field_path=field, before_expr=case.before_expr, after_expr=case.after_expr
        ),
    )


def score(cases: list[BenchmarkCase], predictions: dict[str, str]) -> Metrics:
    """Score predictions {case_name -> classification} against the labeled cases."""
    m = Metrics(total=len(cases))
    tp = fp = fn = 0
    for c in cases:
        pred = predictions.get(c.name, "insufficient-context")
        if pred == c.expected:
            m.correct += 1
        if pred == "insufficient-context":
            m.abstained += 1
        # precision/recall computed on the "breaking" positive class
        truly_breaking = c.expected == "breaking"
        pred_breaking = pred == "breaking"
        if pred_breaking and truly_breaking:
            tp += 1
        elif pred_breaking and not truly_breaking:
            fp += 1
            m.false_positives += 1
        elif truly_breaking and not pred_breaking:
            fn += 1
            m.missed += 1
    m.precision = tp / (tp + fp) if (tp + fp) else 1.0
    m.recall = tp / (tp + fn) if (tp + fn) else 1.0
    return m


def run_benchmark(reasoner) -> Metrics:
    """Run the engine (with the given reasoner) over the seeded suite and score it."""
    predictions: dict[str, str] = {}
    for case in CASES:
        finding = reason_about_change(reasoner, _delta(case))
        predictions[case.name] = finding.classification
    return score(CASES, predictions)
