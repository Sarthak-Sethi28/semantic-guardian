# Examples — evaluable without running

Real artifacts produced by Semantic Guardian against a local DataHub (GMS 1.5.0.6),
so the output can be judged without setting anything up.

| file | what it is |
|---|---|
| `finding_inverted_status.json` | The engine's Finding for the inverted-boolean change (Claude Sonnet 4.5) — classification, change class, explanation, competing hypotheses, per-dimension confidence. |
| `review_comment.md` | The human-facing review comment posted on the change. |
| `compiled_contract.json` | The durable DataHub assertion compiled after owner confirmation — what makes the same break catchable without the LLM next time. |
| `remediation_revenue.json` | A scoped remediation for the $→cents case (`revenue / 100` → `revenue * 100`). |

## Run the killer demo yourself

```bash
python scenario/seed.py            # seed the world
python scripts/demo_killer.py      # inverted boolean: stats blind → engine catches → contract → caught w/o LLM
python scripts/demo_pipeline.py    # the $→cents case, full pipeline
semantic-guardian benchmark        # seeded 9-case suite (9/9 with Claude Sonnet 4.5)
```
