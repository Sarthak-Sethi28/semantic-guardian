"""DataHub read client (#2).

The single boundary through which every layer reads DataHub. Wraps the SDK
`DataHubGraph` (aspects) + GraphQL (relationships/assertions) and returns typed
models — nothing above this module touches the SDK or raw JSON.

Write-back (tags, glossary, incidents) is intentionally not here; see #8/#9.
"""
from __future__ import annotations

from semantic_guardian.config import resolve_datahub_config
from semantic_guardian.models import (
    Contract,
    Dataset,
    Owner,
    RelatedEntity,
    SchemaField,
)

try:  # SDK import isolated so tests can patch it and non-DataHub layers never import it
    from datahub.ingestion.graph.client import DataHubGraph, DatahubClientConfig
except Exception:  # pragma: no cover - only hit if SDK missing
    DataHubGraph = None
    DatahubClientConfig = None

# Relationship + entity-type constants (verified against live GMS).
_ML_ENTITY_MARKERS = ("mlFeature", "mlPrimaryKey", "mlModel")
_DOWNSTREAM_TYPES = ["DerivedFrom", "DownstreamOf", "Produces", "Consumes"]


class DataHubError(Exception):
    """Base for client errors so upstream layers can degrade gracefully."""


class DataHubUnavailable(DataHubError):
    """GMS unreachable / auth failed (e.g. expired ~/.datahubenv token → `datahub init`)."""


class EntityNotFound(DataHubError):
    """Requested URN has no data (e.g. no schema aspect)."""


class DataHubClient:
    def __init__(self, gms_url: str | None = None, token: str | None = None) -> None:
        cfg = resolve_datahub_config(url=gms_url, token=token)
        self._url = cfg.url
        try:
            self._graph = DataHubGraph(
                DatahubClientConfig(server=cfg.url, token=cfg.token or None)
            )
        except Exception as exc:  # connect/auth failure
            raise DataHubUnavailable(
                f"Could not connect to DataHub at {cfg.url}: {exc}. "
                "If the token expired, run `datahub init`."
            ) from exc

    # ── reads ────────────────────────────────────────────────────────────────

    def get_dataset(self, urn: str) -> Dataset:
        from datahub.metadata.schema_classes import SchemaMetadataClass

        schema = self._graph.get_aspect(urn, SchemaMetadataClass)
        if schema is None:
            raise EntityNotFound(f"No schema for {urn}")
        fields = {
            f.fieldPath: SchemaField(
                field_path=f.fieldPath,
                native_type=getattr(f, "nativeDataType", None),
                description=getattr(f, "description", None),
            )
            for f in schema.fields
        }
        return Dataset(urn=urn, name=_name_from_urn(urn), platform=_platform_from_urn(urn), fields=fields)

    def get_schema_fields(self, urn: str) -> list[SchemaField]:
        return list(self.get_dataset(urn).fields.values())

    def get_owners(self, urn: str) -> list[Owner]:
        from datahub.metadata.schema_classes import OwnershipClass

        own = self._graph.get_aspect(urn, OwnershipClass)
        if own is None:
            return []
        return [
            Owner(urn=o.owner, username=o.owner.split(":")[-1], type=getattr(o, "type", None))
            for o in own.owners
        ]

    def get_related(self, urn: str, types: list[str], direction: str = "INCOMING") -> list[RelatedEntity]:
        # `types` must be non-null [String!]! and `direction` is an enum literal in the live
        # GMS schema, so we inline them into the input object rather than pass loose variables.
        types_literal = "[" + ",".join(f'"{t}"' for t in types) + "]"
        query = f"""
        query($urn:String!){{
          entity(urn:$urn){{ relationships(input:{{types:{types_literal},direction:{direction},count:100}}){{
            relationships{{ type entity{{ urn type }} }} }} }}
        }}"""
        try:
            res = self._graph.execute_graphql(query, variables={"urn": urn})
        except Exception as exc:
            raise DataHubUnavailable(f"GraphQL relationships failed for {urn}: {exc}") from exc
        rels = (((res or {}).get("entity") or {}).get("relationships") or {}).get("relationships") or []
        return [
            RelatedEntity(
                urn=r["entity"]["urn"],
                entity_type=r["entity"].get("type", "") or "",
                relationship=r["type"],
            )
            for r in rels
        ]

    def get_downstream_ml(self, urn: str) -> list[RelatedEntity]:
        related = self.get_related(urn, _DOWNSTREAM_TYPES, "INCOMING")
        return [r for r in related if any(m in r.urn for m in _ML_ENTITY_MARKERS)]

    def get_contracts(self, urn: str) -> list[Contract]:
        """Best-effort (D8): return existing assertions/contracts, [] if none/unsupported."""
        query = """
        query($urn:String!){ entity(urn:$urn){ ... on Dataset {
          assertions(start:0,count:50){ assertions{ urn info{ description type } } } } } }"""
        try:
            res = self._graph.execute_graphql(query, variables={"urn": urn})
        except Exception:
            return []
        items = ((((res or {}).get("entity") or {}).get("assertions") or {}).get("assertions")) or []
        out: list[Contract] = []
        for a in items:
            info = a.get("info") or {}
            out.append(Contract(urn=a.get("urn", ""), description=info.get("description"), kind=info.get("type")))
        return out

    def get_profile(self, urn: str):  # noqa: ARG002 - deferred non-goal, stubbed
        """Column stats/profiles: deferred (evidence comes from the diff, not stats)."""
        return None

    def health(self) -> bool:
        try:
            self._graph.get_config()
            return True
        except Exception:
            return False


def _name_from_urn(urn: str) -> str:
    # urn:li:dataset:(urn:li:dataPlatform:hive,fct_users_created,PROD)
    try:
        inner = urn.split("(", 1)[1].rstrip(")")
        return inner.split(",")[1]
    except Exception:
        return urn


def _platform_from_urn(urn: str) -> str | None:
    try:
        return urn.split("dataPlatform:", 1)[1].split(",", 1)[0]
    except Exception:
        return None
