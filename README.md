<div align="center">

# 🛡️ Semantic Guardian

**The meaning-layer for your data catalog.**

An AI agent that catches the silent data failures every monitoring tool misses — the ones where
nothing errors, every check passes, and your ML models quietly rot. It reasons over
[DataHub](https://datahub.com) lineage to find what breaks, validates with a human, writes the
finding back to the catalog, and opens a fix PR.

*Built for the [Build with DataHub: Agent Hackathon](https://datahub.devpost.com) — Production ML Agents.*

</div>

---

## The problem

The ML failures that cost the most money are the ones where **everything technically passes**:

- An upstream team switches a `revenue` column from **dollars → cents**. Same name, same type,
  no nulls, pipeline green — and the downstream pricing model now thinks everything costs 100× more.
- `is_active` gets **redefined** ("logged in this month" → "account not deleted"). Same boolean —
  and the churn model trained on the old meaning is silently invalidated.
- A missing value gets silently **re-encoded** `NULL → 0`, and the model reads 0 as a real value.

A schema check sees no change. A null check sees no nulls. The model just gets worse, for weeks,
with **zero alerts**. This class of failure is [documented as unsolved](docs/datahub-environment-findings.md)
by every major data-quality tool (Monte Carlo, Great Expectations, Soda, Anomalo, Evidently, WhyLabs) —
all of them are statistics-and-schema shaped and none reasons about a column's *meaning*.

## What Semantic Guardian does

One reasoning engine — *"understand what every column actually means"* — pointed at the places
DataHub currently needs a human's judgment.

```
Detect  →  Reason over lineage  →  Validate with human  →  Write back to catalog  →  Heal (fix PR)
```

1. **Detect** a semantic shift that passed every existing check (unit/scale, null↔sentinel
   encoding, categorical remap, currency, meaning drift).
2. **Reason over lineage** — walk the DataHub graph to find exactly which features, models, and
   deployments are in the blast radius.
3. **Validate with a human** — present evidence + reasoning + a proposed fix as a one-click judgment.
4. **Write back to the catalog** — record the validated finding (tags, glossary, description, and a
   DataHub incident) so the next person or agent inherits it.
5. **Heal** — open a scoped, ready-to-merge fix PR against the pipeline repo. A human merges;
   it never auto-merges to production.

The same engine also flags **PII/governance** gaps and auto-writes **missing documentation**, and
ships partly as a reusable **DataHub Skill**.

## Why it uses DataHub meaningfully

Semantic Guardian doesn't just *read* metadata — it **contributes back to the graph**, which is
what the hackathon judging explicitly rewards. It reads lineage/schema/stats via the DataHub
**MCP Server** and SDK, and writes tags, glossary terms, descriptions, and incidents back.

## Status

🚧 Under active development. See [issues](../../issues) for the prioritized build plan and
[docs/](docs/) for the architecture and design specs. Sample generated artifacts live in
[`examples/`](examples/).

## Quick start

```bash
# 1. Run DataHub locally (see docs/setup.md for details)
datahub docker quickstart

# 2. Install
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 3. Configure (personal Anthropic API key — never committed)
cp .env.example .env   # then edit .env

# 4. Run
semantic-guardian --help
```

## Architecture

See [docs/architecture.md](docs/architecture.md). In short: a layered pipeline —
DataHub client → signal extractor → detection engine → blast-radius traversal →
human validation → write-back + healing — where each layer has one job and is tested in isolation.

## License

[Apache-2.0](LICENSE).
