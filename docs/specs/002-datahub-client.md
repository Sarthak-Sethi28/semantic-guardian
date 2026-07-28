# Spec — Issue #2: DataHub client library (read path + PR diff)

- **Issue:** #2 (P0) · **Scope this pass:** reads + Git/PR diff. Write-back deferred to #8/#9.
- **Status:** SPEC — rate before planning.

## Problem
Every layer of Semantic Guardian (signal extractor, delta engine, blast radius) needs
data *from* DataHub and *from* the changed pipeline repo. If each layer talks to GraphQL/SDK/GitHub
directly, external I/O leaks everywhere, nothing is mockable, and downstream code parses raw JSON.
We need **one module** that isolates all external reads behind a typed, mockable interface.

## Goals (this pass)
- G1. One `DataHubClient` that wraps the DataHub GMS (SDK `DataHubGraph` + GraphQL) for the reads the
  spine needs: **dataset schema, field descriptions, glossary terms, ownership, downstream lineage
  (including ML features/primary keys via `DerivedFrom`), and any existing assertions/contracts.**
- G2. A `GitClient` that fetches a **PR/branch diff + changed files** from a pipeline repo (GitHub API),
  so the delta engine has the actual code change. Also supports a **local diff** (a `.diff`/patch file
  or two file versions) so the demo runs with no GitHub dependency.
- G3. **Typed Pydantic models** for every return value — downstream layers never touch raw JSON.
- G4. **Config from env** (`DATAHUB_GMS_URL`, `DATAHUB_GMS_TOKEN`, `GITHUB_TOKEN`), defaulting to the
  local GMS on `http://localhost:8081`; token falls back to `~/.datahubenv`.
- G5. **Mockable for unit tests** (no network), plus **one gated live integration test** against the
  running local DataHub.

## Non-goals (this pass)
- **Write-back** (tags, glossary, descriptions, assertions, incidents) — that is #8/#9. The interface
  will leave clean seams for it but implement no writes now.
- MCP transport — SDK + GraphQL cover every read we need; MCP is not required.
- Caching / rate-limit handling — sample-data scale; add only if a real need appears.
- **Column stats / value-distribution profiles** — issue #2 lists these, but the sample `demo-data`
  carries no `DatasetProfile` aspect (to be confirmed in planning). Semantic Guardian's thesis is
  *evidence from the code diff*, not statistical drift, so profiles are corroborating-only. Deferred:
  `get_profile(urn)` gets a typed stub returning `None` now, wired for real only if #5 needs it.
- **Assertions/contracts read** is **best-effort this pass** — see D7.

## Key decisions
- **D1. SDK `DataHubGraph` as the primary transport; GraphQL for relationship/lineage queries.**
  Confirmed live: `get_aspect(SchemaMetadataClass)` returns fields; `execute_graphql` with a
  `relationships(types:[...], direction:INCOMING)` query returns the ML-feature edges. Both verified
  against the running instance today.
- **D2. Lineage-to-ML uses the `DerivedFrom` relationship, not `DownstreamOf`.** Verified: from
  `fct_users_created`, `DownstreamOf` returns only the dataset; the mlFeature / mlPrimaryKey edges
  come through `DerivedFrom` (9 incoming edges). Blast radius (#6) depends on this, so the client
  exposes a generic `get_related(urn, types, direction)` and a convenience
  `get_downstream_ml(urn)` that filters to ML entity URNs.
- **D3. Typed models** (`Dataset`, `SchemaField`, `GlossaryTerm`, `Owner`, `LineageEdge`,
  `RelatedEntity`, `Contract`/`Assertion`, `PRDiff`, `FileChange`). Pydantic v2. A raw-JSON escape
  hatch is kept internal only.
- **D4. Config precedence:** explicit constructor arg → env var → `~/.datahubenv` (server+token) →
  `http://localhost:8081`. Token is optional (local quickstart may accept none).
- **D5. Two clients, one module boundary:** `DataHubClient` and `GitClient` live under
  `src/semantic_guardian/clients/`. Both depend only on stdlib/SDK/httpx; nothing above them imports
  the SDK directly.
- **D6. Errors are typed** (`DataHubUnavailable`, `EntityNotFound`, `GitDiffError`) so upstream layers
  can degrade to "insufficient-context" rather than crash.
- **D7. Semantics are keyed by field path.** The whole spine reconciles a *changed column* against its
  *declared meaning*, so `Dataset` and the semantic reads expose a `fields: dict[field_path ->
  SchemaField]` map where each `SchemaField` carries `native_type`, `description`, and any attached
  `glossary_terms`. This lets the signal extractor (#4) join a diff's changed column directly to its
  DataHub-declared semantics with no re-parsing.
- **D8. Contracts read is best-effort and non-blocking.** `get_contracts(urn)` tries the assertions
  GraphQL; if the instance has none (sample data likely has zero), it returns `[]`, never raises. The
  planning step verifies the exact query against the live instance before implementing; if the shape
  is uncertain, it ships returning `[]` with a `# TODO(#9)` seam rather than guessing an API.

## Interface (read path)
```
class DataHubClient:
    def __init__(self, gms_url=None, token=None): ...
    def get_dataset(urn) -> Dataset                     # .fields: dict[field_path -> SchemaField]
    def get_schema_fields(urn) -> list[SchemaField]     # native_type, description, glossary_terms
    def get_glossary_terms(urn) -> list[GlossaryTerm]   # dataset- and field-level
    def get_owners(urn) -> list[Owner]
    def get_related(urn, types, direction) -> list[RelatedEntity]
    def get_downstream_ml(urn) -> list[RelatedEntity]   # filters DerivedFrom → mlFeature/mlPrimaryKey/mlModel
    def get_contracts(urn) -> list[Contract]            # best-effort; [] if none (D8)
    def get_profile(urn) -> DatasetProfile | None       # stub this pass (deferred non-goal)
    def health() -> bool                                # GMS reachable

class GitClient:
    def get_pr_diff(repo, pr_number) -> PRDiff          # GitHub API
    def get_local_diff(path_or_two_files) -> PRDiff     # demo path, no network
```

## Architecture / flow
```
env / ~/.datahubenv ─┐
                     ├─► DataHubClient ──(SDK get_aspect / execute_graphql)──► GMS :8081 ──► typed models
GITHUB_TOKEN ────────┴─► GitClient ─────(GitHub API | local patch)──────────► PRDiff
```
Everything above the clients (extractor, delta engine, blast radius) imports **only** these typed
models and the two client classes.

## Testing / acceptance
**Unit (mocked, no network — the default suite):**
- SDK/GraphQL responses are faked; each method maps a canned response to the right typed model.
- `get_downstream_ml` filters mixed relationship results to ML URNs only.
- Config precedence (arg > env > .datahubenv > default) resolves correctly.
- Typed errors raised on missing entity / unreachable GMS / bad diff.
- `get_local_diff` parses a sample patch into `PRDiff` with per-file hunks.

**Live integration (gated, `-m integration`, requires local DataHub):**
- `get_dataset('...fct_users_created...')` returns fields incl. `user_id`, `user_name`.
- `get_downstream_ml(...)` returns the known mlFeatures (`is_premium_user`, `regions`,
  `number_of_visits`) via `DerivedFrom`.
- `health()` is True against :8081.

**Acceptance (subset of the issue, read scope):**
- [ ] Fetch a dataset's schema + downstream (ML) lineage + any contract from local DataHub
- [ ] Fetch a PR diff (GitHub) and a local diff (file) into the same `PRDiff` model
- [ ] Unit tests fully mocked; one gated live integration test passes against local DataHub
- [ ] No layer above `clients/` imports the DataHub SDK or GraphQL directly

## Risks
- **Token expiry** (`~/.datahubenv` token expires ~monthly) → `health()` + a clear `DataHubUnavailable`
  message pointing at `datahub init`.
- **SDK version drift** (pinned `acryl-datahub==1.5.0.6`) → keep the pin; integration test catches breaks.
- **GitHub rate limits / no token** → `get_local_diff` is the demo default, so the spine never blocks on GitHub.
