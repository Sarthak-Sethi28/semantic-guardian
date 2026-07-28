"""GitClient tests (#2). Local diff parses from a fixture; GitHub path mocked."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from semantic_guardian.clients.git import GitClient, GitDiffError

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sample.diff"


def test_local_diff_parses_into_prdiff():
    diff = GitClient().get_local_diff(FIXTURE)
    assert len(diff.files) == 1
    fc = diff.files[0]
    assert fc.path == "models/fct_revenue.sql"
    # the semantic change must survive into the patch text the delta engine reads
    assert "revenue / 100" in fc.patch
    assert diff.raw and "fct_revenue.sql" in diff.raw


def test_local_diff_missing_file_raises():
    with pytest.raises(GitDiffError):
        GitClient().get_local_diff(Path("/no/such.diff"))


def test_local_diff_from_raw_string():
    raw = (
        "diff --git a/m.sql b/m.sql\n"
        "--- a/m.sql\n+++ b/m.sql\n"
        "@@ -1 +1 @@\n- status\n+ case when status=1 then 0 else 1 end as status\n"
    )
    diff = GitClient().get_local_diff(raw)
    assert diff.files[0].path == "m.sql"
    assert "case when status" in diff.files[0].patch


def test_pr_diff_from_github_mocked():
    resp = MagicMock()
    resp.status_code = 200
    resp.text = FIXTURE.read_text()
    with patch("semantic_guardian.clients.git.httpx.get", return_value=resp) as g:
        diff = GitClient(token="ghtok").get_pr_diff("owner/repo", 42)
    # hit the GitHub diff media type
    _, kwargs = g.call_args
    assert "vnd.github" in kwargs["headers"]["Accept"]
    assert diff.files[0].path == "models/fct_revenue.sql"


def test_pr_diff_http_error_raises():
    resp = MagicMock()
    resp.status_code = 404
    resp.text = "not found"
    with patch("semantic_guardian.clients.git.httpx.get", return_value=resp):
        with pytest.raises(GitDiffError):
            GitClient().get_pr_diff("owner/repo", 999)
