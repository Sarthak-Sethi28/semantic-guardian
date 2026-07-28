"""Scenario change-fixture tests (#3). Unit — no network."""
from __future__ import annotations

from pathlib import Path

from semantic_guardian.clients.git import GitClient

CHANGES = Path(__file__).resolve().parents[1] / "scenario" / "changes"


def test_unit_scale_fixture_carries_the_semantic_change():
    diff = GitClient().get_local_diff(CHANGES / "unit_scale.diff")
    assert diff.files[0].path == "models/fct_revenue.sql"
    assert "revenue / 100" in diff.files[0].patch  # the dollars->cents evidence


def test_benign_fixture_touches_no_column_expression():
    diff = GitClient().get_local_diff(CHANGES / "benign.diff")
    patch = diff.files[0].patch
    # only added lines are comments; no column expression changed
    added = [
        line
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    assert added, "benign diff should add something"
    assert all(line.lstrip("+").strip().startswith("--") for line in added)


def test_all_fixtures_parse():
    gc = GitClient()
    for name in ("unit_scale", "null_sentinel", "categorical_remap", "benign"):
        diff = gc.get_local_diff(CHANGES / f"{name}.diff")
        assert diff.files, f"{name}.diff produced no file changes"
