"""Review surface (#13) — GitHub-native first.

A code-review agent's natural surface is a PR comment, so the review UI is a Markdown
renderer: turn a SkillResult into the comment posted on the change. Pure formatting — no
network — so it's testable and reusable (post it via the GitHub API, or print it in the CLI).
"""
from __future__ import annotations

from semantic_guardian.skill import SkillResult

_HEADER = "## 🛡️ Semantic Guardian"


def _confidence_line(conf: dict[str, float]) -> str:
    if not conf:
        return ""
    parts = " · ".join(f"{k}: {v:.2f}" for k, v in conf.items())
    return f"\n\n*Confidence — {parts}*"


def render_review(result: SkillResult) -> str:
    """Render a SkillResult as a GitHub PR review comment (Markdown)."""
    if not result.findings:
        return (
            f"{_HEADER}\n\n"
            f"No column changes detected in `{result.event}`. Nothing to review."
        )

    breaking = [f for f in result.findings if f.classification == "breaking"]
    lines = [_HEADER, ""]

    if not breaking:
        classes = ", ".join(sorted({f.classification for f in result.findings}))
        lines.append(
            f"Reviewed the change to **{', '.join(result.changed_fields)}** — "
            f"no breaking semantic change ({classes}). ✅"
        )
        # surface any abstention honestly rather than implying all-clear
        if any(f.classification == "insufficient-context" for f in result.findings):
            lines.append(
                "\n> Some fields were **insufficient-context** — the evidence was too weak to "
                "judge, so the agent abstained rather than guess."
            )
        return "\n".join(lines)

    # one section per breaking finding
    for f in breaking:
        lines.append(f"**BREAKING semantic change** on `{f.field_path}` "
                     f"(`{f.change_class}`).\n")
        lines.append(f"**Why it matters** — {f.explanation}")
        if f.hypotheses:
            lines.append("\n**Competing hypotheses**")
            for i, h in enumerate(f.hypotheses, 1):
                lines.append(f"{i}. {h}")
        stats = f.confidence.get("stats")
        if stats is not None and stats == 0.0:
            lines.append(
                "\n> Note: **statistical monitors are blind to this** — the value set and "
                "distribution are unchanged. It is only visible from the code change."
            )
        lines.append(_confidence_line(f.confidence))

    # blast radius + routing
    br = result.blast_radius
    if br is not None:
        impacted = sum(br.counts.values())
        owners = ", ".join(f"`{o.username}`" for o in br.owners_to_notify) or "—"
        lines.append(
            f"\n**Blast radius** — severity `{br.severity}`, {impacted} downstream ML "
            f"entit{'y' if impacted == 1 else 'ies'} affected. Routed to: {owners}."
        )

    lines.append(
        "\n**Next** — confirm intent. On confirmation, Semantic Guardian compiles a durable "
        "DataHub assertion so this exact break is caught deterministically next time."
    )
    return "\n".join(lines)
