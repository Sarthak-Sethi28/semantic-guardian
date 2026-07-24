# Semantic Guardian — hackathon idea, for Ian's gut-check

**TL;DR:** I got into DataHub's "Agent Hackathon" (online, build an AI agent, grand prize $6k, deadline Aug 10). I've scoped an idea and validated it against DataHub's own docs + the competitor landscape before committing 5 weeks. Want you to try to break it.

---

## 1. Context (30 sec)

- **Host:** DataHub (formerly Acryl Data) — the open-source metadata catalog. Run on Devpost.
- **Ask:** build an AI agent on top of DataHub; ship a public Apache-2.0 repo, a <3-min demo, a writeup.
- **Category I picked:** "Production ML Agents" — agents that protect deployed models.
- **Prize pool:** $20.5k total; $6k grand. Real target though is **getting noticed by DataHub's eng team** (they're the judges + run a Champions program + have open Ingestion/Catalog roles).

## 2. The problem I'm attacking

The ML failures that cost the most money are **silent semantic changes** — where everything technically passes but the meaning of the data shifts:

- Upstream team switches a `revenue` column from **dollars → cents** (to kill float rounding). Same name, same type (int), no null, pipeline green. Downstream pricing model now 100x's everything. **No error, ever.**
- `is_active` gets redefined ("logged in last 30d" → "account not deleted"). Same bool. Churn model silently invalidated.
- A missing value gets re-encoded `NULL → 0`. Model reads 0 as a real value.

None of these violate a schema check or a null check. They're invisible to structural diffs and to threshold-based data-quality rules.

## 3. Why this is a real gap (sourced, not hand-waving)

**DataHub's own docs/blog:**
- None of DataHub's 7 assertion types (freshness, volume, column-metric, column-value, custom-SQL, schema, anomaly) detect a column whose *meaning/unit* changes while name+type stay valid. Column assertions are explicitly statistical/constraint-based; schema assertions catch only structural change. (docs.datahub.com/docs/managed-datahub/observe/column-assertions)
- Their ML-model metamodel confirms **no upstream-impact monitoring, no model-drift monitoring** — lineage is stored, not reasoned over. (docs.datahub.com/docs/generated/metamodel/entities/mlmodel)
- **The key admission**, from their hackathon-week blog (2026-07-06): *"auto-generation captures how data has been used, not how it should be used… Without a human validation layer, agents retrieve the most popular context, not the most correct context."* → They're publicly stating that validating what data *means* is currently **manual human work** their platform can't automate. (datahub.com/blog/ai-agents-human-validated-context/)

**Competitor scan (do any existing tools already do this?):** Checked Monte Carlo, Great Expectations, Soda, Anomalo, Elementary, Evidently, WhyLabs. **None** detects semantic/unit/meaning changes — all are statistics + schema shaped. The "dollars→cents, agent silently misreads" failure is a documented, named pain point that **no vendor owns.**

## 4. What I'm building — "Semantic Guardian"

An agent that becomes the **"human validation layer" DataHub says is missing.**

**Pipeline:**
1. **Detect** — watches DataHub metadata + dataset profiles/stats for signals of a semantic shift (scale jump with same type, null-rate collapse with value-spike, categorical cardinality remap, currency/unit cues in descriptions + transformation code).
2. **Reason over lineage** — traverses the graph to determine which features → models → deployments are affected (blast radius), using the MCP Server's `get_lineage`, `list_schema_fields`, `get_dataset_queries`.
3. **Validate w/ human** — presents a **one-click judgment**: evidence + reasoning + proposed fix. Human confirms/rejects (this is the point — 10-second approval vs. hours of manual investigation).
4. **Write back** — on confirm, writes validated semantic context to the catalog (tags, descriptions, glossary terms via MCP; incident via GraphQL `raiseIncident`) so the next person/agent inherits it.
5. **Heal** — opens a fix PR against the pipeline repo (human merges; never auto-merge).

**Ships partly as a reusable DataHub Skill** → hits the open-source-contribution judging bonus AND is the contribution type DataHub's Champions program recognizes.

## 5. Honest scoping / risks (so I don't overclaim)

- **Scope semantic detection to detectable CLASSES** (unit/scale, encoding null↔sentinel, categorical remap, currency) — NOT "detects any meaning change." Distinguishing a true unit change from normal drift without a type signal is the hard part; needs heuristics (scale-shift on same type, downstream-consumer assumptions, description/lineage/code context) + LLM reasoning.
- **Don't lead with pure statistical drift** — DataHub Cloud anomaly detection + Monte Carlo/Evidently already do that. Our novelty is semantic *interpretation* + lineage reasoning + validated write-back.
- **Local-DataHub write constraints (confirmed):** tags/descriptions/glossary write freely via MCP; assertions are Cloud-only; incidents need direct GraphQL. Designing around this.
- **Model/LLM:** personal Anthropic API key, my own account (a few $ total). Nothing on company infra.

## 6. Questions I most want you to pressure-test

1. Is the semantic-detection heuristic set actually tractable, or am I underestimating the false-positive rate?
2. Is "be the human validation layer" the right framing, or is autonomous-fixer stronger?
3. Anything about DataHub / catalogs / ML lineage I'm getting wrong that a judge would catch?

---

*Sources: datahub.devpost.com · docs.datahub.com (assertions, mlmodel metamodel, agent-context/skills, features/mcp) · datahub.com/blog/ai-agents-human-validated-context · github.com/acryldata/mcp-server-datahub · competitor docs (montecarlo.ai, greatexpectations.io, soda.io, anomalo.com, evidentlyai.com, whylabs.ai)*
