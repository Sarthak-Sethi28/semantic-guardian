# DataHub local environment — ground-truth findings (2026-07-24)

## Environment
- DataHub v1.5.0.6 running locally. Frontend: http://localhost:9002 (datahub/datahub).
- GMS API: http://localhost:8081 (remapped from 8080 to avoid lda_keycloak conflict).
- GraphQL: http://localhost:8081/api/graphql
- CLI pinned to 1.5.0.6 in venv to match server (1.6 CLI produced empty demo-data).
- Auth token in ~/.datahubenv (expires ~1 month; regen via `datahub init`).

## Entity census (sample data loaded via `demo-data` source)
| Type | Count |
|---|---|
| dataset | 7 |
| mlFeature | 20 |
| mlFeatureTable | 5 |
| mlPrimaryKey | 7 |
| mlModel | 1 (scienceModel) |
| dataFlow | 1 (airflow dag_abc) |
| dataJob | 2 (task_123, task_456) |
| dashboard | 1 |, chart 2, corpuser 2, tag 2, glossaryTerm 3, container 2 |

## Datasets (raw tables)
- hive: fct_users_created, fct_users_deleted, logging_events, SampleHiveDataset
- s3: project/root/events/logging_events_bckp
- hdfs: SampleHdfsDataset
- kafka: SampleKafkaDataset

## Lineage — CONFIRMED walkable
- `fct_users_created`: upstream=2, downstream=8. Downstream INCLUDES ML features:
  - mlFeature (user_features): is_premium_user, regions, number_of_visits
  - mlPrimaryKey: user_features.user_id, user_features.user_name, user_analytics.user_name
  - mlFeature/PK (user_analytics): date_joined
  - also -> fct_users_deleted (dataset)
- `logging_events`: downstream=5 -> airflow task_123/task_456, s3 backup, fct_users_created, fct_users_deleted
- So chain **dataset -> mlFeature -> mlFeatureTable** EXISTS and is queryable.

## Gaps to be aware of (shape the build)
- `scienceModel` (the only mlModel) has NO relationships to features/datasets — dataset->model edge is missing in sample data. We may need to ADD a model-to-feature lineage edge ourselves to demo the full dataset->feature->model->deployment chain. (We can emit this via the SDK — good, it also demonstrates write capability.)
- Schema is deliberately messy: `fct_users_created` fields typed `BOOLEAN` but nativeDataType `varchar(100)` / `boolean` — inconsistent. Useful: realistic mess for the agent to reason over.
- Datasets have field-level `description`s (e.g. "Id of the user created") — good raw material for semantic reasoning + auto-doc.

## Implication for Semantic Guardian
- We have a real lineage graph to compute blast radius over (dataset -> features).
- To demo the full ML chain we'll likely emit a small amount of our own metadata:
  1. a dataset->model (or feature->model) lineage edge for scienceModel,
  2. richer dataset profiles/stats (value distributions) so semantic-shift detection has signal,
  3. a realistic "before/after" semantic change (e.g. a $->cents or unit shift) to stage the demo.
- Write paths available locally: tags, descriptions, glossary via MCP/SDK; incidents via GraphQL raiseIncident.
