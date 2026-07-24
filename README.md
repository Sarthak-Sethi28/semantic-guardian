<div align="center">

# 🛡️ Semantic Guardian

**A code reviewer for the *meaning* of your data.**

When an engineer changes a data pipeline, Semantic Guardian reviews that change against your
organization's approved business semantics — *before it merges*. It reads the code diff, reconciles
it with [DataHub](https://datahub.com)'s lineage, ownership, and contracts, flags high-confidence
semantic violations, computes the downstream ML blast radius, routes the decision to the right
owner, and compiles that decision into a **durable, machine-enforceable contract** so the same
breakage is caught deterministically next time.

*Built for the [Build with DataHub: Agent Hackathon](https://datahub.devpost.com) — Production ML Agents.*

</div>

---

## The problem

The ML failures that cost the most money are silent semantic changes — where a column's *meaning*
changes but its name and type stay valid, so nothing errors and the model quietly rots:

- A pipeline PR switches a `revenue` column from **dollars → cents**. Same name, same int type,
  pipeline green — and the downstream pricing model now thinks everything costs 100× more.
- A `CASE` statement inverts `account_status` (`1 = active` → `1 = deleted`). **Same values, same
  distribution** — a statistical monitor sees *nothing* — but every model reading it is now backwards.
- A `COALESCE` silently re-encodes missing values `NULL → 0`, and the model reads 0 as real.

## The key idea: evidence, not guessing

Statistical monitors (Monte Carlo, Soda, Evidently, …) can catch some *symptoms* of these — but
they see numbers move, not *why*, and for a meaning-preserving-distribution change (the inverted
flag above) they are **blind**. Semantic Guardian is different because it triggers on the **code
change** and reasons from **causal evidence**:

> It doesn't guess "the median jumped, maybe the unit changed." It reads the diff — *"this PR added
> `/ 100` to a column the contract declares is in dollars"* — and reconciles that against DataHub's
> approved semantics. That's proof, not a hunch, so false positives stay low.

## What it does

```
PR / change  →  Extract semantic delta from the diff  →  Reconcile with DataHub context
             →  Compute ML blast radius  →  Route decision to owner
             →  Write back + compile a durable contract
```

1. **Trigger on a change** — a dbt/SQL/pipeline PR (or a metadata change) fires the review.
2. **Extract the semantic delta** from the actual code diff + profile deltas.
3. **Reconcile with DataHub context** — schema history, glossary, ownership, column-level lineage,
   and any existing contract. Classify: compatible / breaking / insufficient-context.
4. **Compute ML blast radius** — which features, models, and deployments are affected, and who owns them.
5. **Route to a human** — present competing hypotheses + evidence; the owner decides (never silent).
6. **Write back + compile a contract** — record the decision in DataHub (tag, glossary, incident)
   **and** compile it into a machine-enforceable assertion/contract. The next time that violation
   occurs, it's caught **deterministically — without the LLM.**

Every human validation makes the system rely on the LLM *less*. It turns tacit organizational
knowledge into executable, durable context.

Scoped to three high-confidence, evidence-backed change classes: **unit/scale**, **null↔sentinel
encoding**, and **categorical remap**. It ships with a **seeded evaluation benchmark** (precision /
recall / abstention) and a reusable **DataHub Skill**.

## Why it uses DataHub meaningfully

Remove DataHub and the tool stops working: it depends on DataHub for column identity, historical
context, glossary/contracts, ownership routing, column-level lineage, ML blast radius, incident
creation, and durable write-back. It doesn't just *read* the graph — it **contributes durable,
validated context back to it**, which the judging explicitly rewards.

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
