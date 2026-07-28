"""Config resolution (#2).

Precedence: explicit arg > env var > ~/.datahubenv > local default.
Token is optional (local quickstart may accept none).
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel

DEFAULT_GMS_URL = "http://localhost:8081"


class DataHubConfig(BaseModel):
    url: str
    token: str | None = None


def _read_datahubenv(home: Path) -> tuple[str | None, str | None]:
    """Return (server, token) from ~/.datahubenv, or (None, None) if absent/malformed."""
    path = home / ".datahubenv"
    if not path.exists():
        return None, None
    try:
        data = yaml.safe_load(path.read_text()) or {}
        gms = data.get("gms", {}) or {}
        return gms.get("server"), gms.get("token")
    except Exception:
        return None, None


def resolve_datahub_config(
    url: str | None = None,
    token: str | None = None,
    home: Path | None = None,
) -> DataHubConfig:
    home = home or Path.home()
    file_server, file_token = _read_datahubenv(home)

    resolved_url = url or os.getenv("DATAHUB_GMS_URL") or file_server or DEFAULT_GMS_URL
    resolved_token = token or os.getenv("DATAHUB_GMS_TOKEN") or file_token
    return DataHubConfig(url=resolved_url, token=resolved_token)


def resolve_github_token() -> str | None:
    return os.getenv("GITHUB_TOKEN")
