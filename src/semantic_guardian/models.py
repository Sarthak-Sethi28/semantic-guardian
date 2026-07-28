"""Typed models shared across Semantic Guardian layers (#2).

Downstream layers (signal extractor, delta engine, blast radius) consume ONLY these
models — never raw DataHub JSON or GitHub payloads.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class GlossaryTerm(BaseModel):
    urn: str
    name: str


class SchemaField(BaseModel):
    """One column and its DataHub-declared semantics (D7: keyed by field_path)."""

    field_path: str
    native_type: str | None = None
    description: str | None = None
    glossary_terms: list[GlossaryTerm] = Field(default_factory=list)


class Owner(BaseModel):
    urn: str
    username: str
    type: str | None = None  # e.g. DATAOWNER, TECHNICAL_OWNER


class Dataset(BaseModel):
    urn: str
    name: str
    platform: str | None = None
    # D7: field_path -> SchemaField so a diff's changed column joins directly to its meaning.
    fields: dict[str, SchemaField] = Field(default_factory=dict)


class RelatedEntity(BaseModel):
    """An entity reached by traversing a relationship (e.g. DerivedFrom -> mlFeature)."""

    urn: str
    entity_type: str  # dataset | mlFeature | mlPrimaryKey | mlModel | dataJob | ...
    relationship: str  # DerivedFrom | DownstreamOf | Produces | ...


class Contract(BaseModel):
    """An existing assertion/contract on an entity. Best-effort read (D8)."""

    urn: str
    description: str | None = None
    kind: str | None = None


class FileChange(BaseModel):
    path: str
    patch: str  # unified-diff hunk(s) for this file


class PRDiff(BaseModel):
    files: list[FileChange] = Field(default_factory=list)
    raw: str | None = None
