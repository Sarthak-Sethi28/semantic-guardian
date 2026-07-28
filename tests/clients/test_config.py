"""Config resolution tests (#2). No real filesystem/network — tmp paths + monkeypatch."""
from __future__ import annotations

import textwrap

from semantic_guardian.config import resolve_datahub_config, resolve_github_token


def test_explicit_arg_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("DATAHUB_GMS_URL", "http://env:8081")
    cfg = resolve_datahub_config(url="http://explicit:9999", token="t", home=tmp_path)
    assert cfg.url == "http://explicit:9999"
    assert cfg.token == "t"


def test_env_over_datahubenv_and_default(monkeypatch, tmp_path):
    (tmp_path / ".datahubenv").write_text(
        textwrap.dedent("""
        gms:
          server: http://file:8081
          token: filetok
        """)
    )
    monkeypatch.setenv("DATAHUB_GMS_URL", "http://env:8081")
    monkeypatch.setenv("DATAHUB_GMS_TOKEN", "envtok")
    cfg = resolve_datahub_config(home=tmp_path)
    assert cfg.url == "http://env:8081"
    assert cfg.token == "envtok"


def test_datahubenv_over_default(monkeypatch, tmp_path):
    monkeypatch.delenv("DATAHUB_GMS_URL", raising=False)
    monkeypatch.delenv("DATAHUB_GMS_TOKEN", raising=False)
    (tmp_path / ".datahubenv").write_text(
        "gms:\n  server: http://file:8081\n  token: filetok\n"
    )
    cfg = resolve_datahub_config(home=tmp_path)
    assert cfg.url == "http://file:8081"
    assert cfg.token == "filetok"


def test_default_when_nothing_set(monkeypatch, tmp_path):
    monkeypatch.delenv("DATAHUB_GMS_URL", raising=False)
    monkeypatch.delenv("DATAHUB_GMS_TOKEN", raising=False)
    cfg = resolve_datahub_config(home=tmp_path)  # no .datahubenv in tmp
    assert cfg.url == "http://localhost:8081"
    assert cfg.token is None  # token optional for local quickstart


def test_github_token(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghtok")
    assert resolve_github_token() == "ghtok"
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert resolve_github_token() is None
