"""Semantic-delta engine (#5) — THE SPINE.

Given a column change (diff evidence + DataHub-declared meaning), reason about what
SEMANTICALLY changed and classify it: compatible | breaking | insufficient-context.

The reasoning is done by an LLM behind a thin interface (`LLMReasoner` = anything with
`reason(prompt) -> str`). This file is provider-agnostic: a Bedrock or Anthropic impl is a
drop-in that satisfies the protocol. Tests use a scripted stub, so the whole engine —
prompt assembly, parsing, abstention — is verifiable with no API key.

Two principles that keep this an *agent*, not a lookup table:
1. Nothing hardcoded: the deterministic `change_kind` hint from the extractor is NEVER put
   in the prompt as the answer — the model reasons from the raw diff + contract and must
   generalize to changes we didn't anticipate.
2. Abstention is a feature: weak/ambiguous evidence -> insufficient-context, don't alert.
"""
from __future__ import annotations

import json
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from semantic_guardian.models import ColumnDelta


@runtime_checkable
class LLMReasoner(Protocol):
    """Structural interface. A real Bedrock/Anthropic client implements this; so does a stub."""

    def reason(self, prompt: str) -> str:  # returns the model's raw text (expected JSON)
        ...


class Finding(BaseModel):
    field_path: str
    classification: str  # compatible | breaking | insufficient-context
    # unit_scale | null_sentinel | categorical_remap | other | unknown
    change_class: str = "unknown"
    explanation: str = ""
    hypotheses: list[str] = []
    confidence: dict[str, float] = {}  # broken out by dimension: code / stats / catalog / precedent

    @property
    def abstained(self) -> bool:
        return self.classification == "insufficient-context"


_SYSTEM = """You are a data-semantics reviewer. You are given a CODE CHANGE to a column and
the column's DECLARED MEANING from the data catalog. Decide whether the change preserves or
breaks the declared meaning. Reason ONLY from the evidence shown — do not assume a verdict.

A change is "breaking" if it alters what the column MEANS even when its name and type are
unchanged (e.g. dividing a money column changes its unit; inverting a CASE flips an encoding
while leaving the distribution identical). It is "compatible" if meaning is preserved. If the
evidence is too weak to tell, answer "insufficient-context" — abstaining is correct, not failure.

Return ONLY a JSON object:
{"classification": "compatible|breaking|insufficient-context",
 "change_class": "unit_scale|null_sentinel|categorical_remap|other|unknown",
 "explanation": "<one or two sentences citing the evidence>",
 "hypotheses": ["<competing explanation 1>", "<competing explanation 2>"],
 "confidence": {"code": 0-1, "stats": 0-1, "catalog": 0-1, "precedent": 0-1}}"""


def build_prompt(delta: ColumnDelta) -> str:
    """Assemble the evidence prompt. Carries the diff + declared meaning ONLY — never the
    extractor's heuristic change_kind (that would anchor the model into rubber-stamping)."""
    col = delta.column
    ch = delta.change
    terms = ", ".join(t.name for t in col.glossary_terms) or "none"
    return f"""{_SYSTEM}

COLUMN: {ch.field_path}
DECLARED TYPE: {col.declared_type or "unknown"}
DECLARED MEANING (catalog description): {col.description or "none"}
GLOSSARY TERMS: {terms}

CODE CHANGE (unified-diff evidence):
- before: {ch.before_expr or "(absent)"}
+ after:  {ch.after_expr or "(absent)"}

Classify the change and respond with the JSON object only."""


def _extract_json(raw: str) -> str:
    """Pull the JSON object out of a model response. Models commonly wrap JSON in
    ```json fences or add prose; we strip fences and take the outermost {...}."""
    if not raw:
        return "{}"
    text = raw.strip()
    # strip a leading ```json / ``` fence and trailing ```
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    # take the outermost object if there's surrounding prose
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def reason_about_change(reasoner: LLMReasoner, delta: ColumnDelta) -> Finding:
    """Ask the reasoner to classify one column change. Malformed output -> abstain (never
    fabricate a verdict, never crash)."""
    prompt = build_prompt(delta)
    try:
        raw = reasoner.reason(prompt)
        data = json.loads(_extract_json(raw))
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except Exception:
        return Finding(
            field_path=delta.change.field_path,
            classification="insufficient-context",
            change_class="unknown",
            explanation="The reasoner did not return a parseable verdict; abstaining.",
        )

    classification = data.get("classification", "insufficient-context")
    if classification not in ("compatible", "breaking", "insufficient-context"):
        classification = "insufficient-context"

    return Finding(
        field_path=delta.change.field_path,
        classification=classification,
        change_class=data.get("change_class", "unknown") or "unknown",
        explanation=data.get("explanation", "") or "",
        hypotheses=list(data.get("hypotheses", []) or []),
        confidence={k: float(v) for k, v in (data.get("confidence") or {}).items()
                    if isinstance(v, (int, float))},
    )
