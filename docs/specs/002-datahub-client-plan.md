# Plan — Issue #2: DataHub client (read path + PR diff)

Spec: `002-datahub-client.md`. Branch: `feat/2-datahub-client`. TDD, small commits, pause before merge.

## Verified against live GMS (:8081) before planning
- `get_aspect(SchemaMetadataClass)` → fields w/ `fieldPath`, `nativeDataType`, `description`.
- `get_aspect(OwnershipClass)` → owners (`jdoe`, `datahub`).
- `get_aspect(GlossaryTermsClass)` → dataset-level terms (None in sample; field-level via editableSchemaMetadata).
- `execute_graphql(relationships types:[DerivedFrom] INCOMING)` → mlFeature/mlPrimaryKey edges.
- Contracts: no assertions in sample data → `get_contracts` returns `[]` (D8, non-blocking).

## File map
```
src/semantic_guardian/models.py            # Pydantic v2 typed models (shared)
src/semantic_guardian/clients/__init__.py
src/semantic_guardian/clients/datahub.py   # DataHubClient (reads)
src/semantic_guardian/clients/git.py       # GitClient (PR diff + local diff)
src/semantic_guardian/config.py            # env / ~/.datahubenv resolution
tests/clients/test_models.py
tests/clients/test_config.py
tests/clients/test_datahub_client.py       # unit, SDK mocked
tests/clients/test_git_client.py           # unit, local patch + mocked GitHub
tests/integration/test_datahub_live.py     # -m integration, real GMS
tests/fixtures/sample.diff                 # revenue dollars->cents patch (also feeds #3)
```

## Steps (each = 1 commit, test-first)

**Step 1 — models.py (commit: `feat(models): typed DataHub + diff models (#2)`)**
- Test: construct/validate `SchemaField(field_path, native_type, description, glossary_terms)`,
  `Dataset(urn, name, platform, fields: dict[str,SchemaField])`, `GlossaryTerm`, `Owner`,
  `RelatedEntity(urn, entity_type, relationship)`, `Contract`, `FileChange`, `PRDiff(files, raw)`.
- Then: write the Pydantic v2 models. Pure, no I/O → 100% coverable.

**Step 2 — config.py (commit: `feat(config): env + .datahubenv resolution (#2)`)**
- Test: precedence arg > env(`DATAHUB_GMS_URL`/`_TOKEN`) > `~/.datahubenv` > `http://localhost:8081`;
  token optional; `~/.datahubenv` parsed for `gms.server`/`gms.token`.
- Then: `resolve_datahub_config()` + `resolve_github_token()`. Filesystem read mocked via tmp path.

**Step 3 — DataHubClient (commit: `feat(datahub): read client — schema, glossary, owners, lineage (#2)`)**
- Test (SDK mocked — patch `DataHubGraph`): `get_dataset` maps aspects → `Dataset.fields` keyed by
  path; `get_downstream_ml` filters mixed `get_related` results to `mlFeature/mlPrimaryKey/mlModel`
  URNs; `get_owners`; `get_contracts` returns `[]` on empty; typed errors (`EntityNotFound`,
  `DataHubUnavailable`); `health()`.
- Then: implement over `DataHubGraph` (`get_aspect` + `execute_graphql`). Raw JSON stays internal.

**Step 4 — GitClient (commit: `feat(git): PR diff + local diff → PRDiff (#2)`)**
- Test: `get_local_diff(sample.diff)` parses into `PRDiff` (per-file hunks); `get_pr_diff` mocked
  httpx GitHub response → same model; `GitDiffError` on bad input.
- Then: implement. `get_local_diff` is the demo default (no network).

**Step 5 — live integration (commit: `test(datahub): gated live integration against local GMS (#2)`)**
- `-m integration`: `get_dataset(fct_users_created)` has `user_id`/`user_name`; `get_downstream_ml`
  returns `is_premium_user`/`regions`/`number_of_visits`; `health()` True. Skipped if GMS down.

**Step 6 — wire CLI + verify (commit: `chore: expose client + green suite (#2)`)**
- `pytest -m "not integration"` green; add `-m integration` marker to pyproject; ruff+mypy clean.
- Optional tiny `semantic-guardian inspect <urn>` command to eyeball a dataset (demo-friendly).

## Definition of done (#2 read scope)
- All spec acceptance boxes for read scope checked; unit suite green & mocked; one live integration
  test passes; nothing above `clients/` imports the SDK. Rate impl → fix to 10 → code-review → PR.
- **PR references #2 but does NOT close it** ("Part of #2, read path; write-back in #8/#9"), because
  #2's acceptance includes write-back. #2 is closed by the write pass. This keeps the issue honest.
- **Pause for merge approval** — do not merge without the user's go-ahead.
