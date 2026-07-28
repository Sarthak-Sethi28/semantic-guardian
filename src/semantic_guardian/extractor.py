"""Signal extractor (#4): fuse a code diff with DataHub-declared semantics.

Pure transformation over #2's typed models — no I/O, no client imports. Produces
one ColumnDelta per changed output column: the declared meaning (ColumnSnapshot)
joined by field path to what the diff did (ChangeSnapshot).

change_kind is a cheap heuristic HINT (keywords in the diff), never the verdict —
the semantic-delta engine (#5) makes the real call and also sees before/after text.
"""
from __future__ import annotations

import re

from semantic_guardian.models import (
    ChangeSnapshot,
    ColumnDelta,
    ColumnSnapshot,
    Dataset,
    PRDiff,
)

# Heuristics (D3) — evidence keywords, matched against the after-expression.
_UNIT_SCALE = re.compile(r"[/*]\s*\d+(\.\d+)?\b")
_NULL_SENTINEL = re.compile(r"\bcoalesce\s*\(", re.IGNORECASE)
_CATEGORICAL = re.compile(r"\bcase\s+when\b", re.IGNORECASE)


def _output_column(expr: str) -> str | None:
    """Output column name for a select-list line: the `as <alias>`, else trailing identifier."""
    e = expr.strip().rstrip(",").strip()
    if not e:
        return None
    m = re.search(r"\bas\s+([A-Za-z_][\w]*)\s*$", e, re.IGNORECASE)
    if m:
        return m.group(1)
    # bare column: last identifier token
    m = re.search(r"([A-Za-z_][\w]*)\s*$", e)
    return m.group(1) if m else None


def _is_ignorable(body: str) -> bool:
    b = body.strip()
    return b == "" or b.startswith("--")


def _classify(after_expr: str | None) -> str:
    if after_expr is None:
        return "none"
    if _NULL_SENTINEL.search(after_expr):
        return "null_sentinel"
    if _CATEGORICAL.search(after_expr):
        return "categorical_remap"
    if _UNIT_SCALE.search(after_expr):
        return "unit_scale"
    return "other"


def _parse_changes(patch: str) -> list[ChangeSnapshot]:
    """Pair removed/added select-list lines by output column name (D2)."""
    removed: dict[str, str] = {}
    added: dict[str, str] = {}
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("-"):
            body = line[1:]
            if _is_ignorable(body):
                continue
            col = _output_column(body)
            if col:
                removed[col] = body.strip().rstrip(",").strip()
        elif line.startswith("+"):
            body = line[1:]
            if _is_ignorable(body):
                continue
            col = _output_column(body)
            if col:
                added[col] = body.strip().rstrip(",").strip()

    changes: list[ChangeSnapshot] = []
    for col in sorted(set(removed) | set(added)):
        before = removed.get(col)
        after = added.get(col)
        # A pure add or pure remove of the SAME identifier with no expression change is noise;
        # only surface when something actually differs.
        if before == after:
            continue
        changes.append(
            ChangeSnapshot(
                field_path=col,
                before_expr=before,
                after_expr=after,
                change_kind=_classify(after),
            )
        )
    return changes


def extract_snapshots(dataset: Dataset, diff: PRDiff) -> list[ColumnDelta]:
    """Fuse each changed column with its declared semantics, joined by field path."""
    deltas: list[ColumnDelta] = []
    for file in diff.files:
        for change in _parse_changes(file.patch):
            field = dataset.fields.get(change.field_path)
            if field is not None:
                col = ColumnSnapshot(
                    field_path=field.field_path,
                    declared_type=field.native_type,
                    description=field.description,
                    glossary_terms=field.glossary_terms,
                )
            else:
                # In the diff but not the schema (new/renamed) — surface, don't drop.
                col = ColumnSnapshot(field_path=change.field_path, declared_type=None)
            deltas.append(ColumnDelta(column=col, change=change))
    return deltas
