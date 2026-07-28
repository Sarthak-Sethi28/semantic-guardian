"""Git client (#2): fetch a code change as a typed PRDiff.

Two entry points:
- get_local_diff  — parse a unified diff from a file path or raw string (demo default; no network)
- get_pr_diff     — fetch a PR's unified diff from the GitHub API

The delta engine (#5) reads PRDiff.files[*].patch as the evidence of what the change does.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from semantic_guardian.config import resolve_github_token
from semantic_guardian.models import FileChange, PRDiff

_GITHUB_DIFF_ACCEPT = "application/vnd.github.v3.diff"


class GitDiffError(Exception):
    """Bad diff input, missing file, or GitHub fetch failure."""


class GitClient:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or resolve_github_token()

    def get_local_diff(self, source: str | Path) -> PRDiff:
        """Parse a unified diff from a file path or a raw diff string."""
        raw = self._read_source(source)
        if not raw.strip():
            raise GitDiffError("Empty diff")
        return _parse_unified_diff(raw)

    def get_pr_diff(self, repo: str, pr_number: int) -> PRDiff:
        """Fetch a PR's unified diff from GitHub (repo = 'owner/name')."""
        url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
        headers = {"Accept": _GITHUB_DIFF_ACCEPT}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        resp = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
        if resp.status_code != 200:
            raise GitDiffError(
                f"GitHub returned {resp.status_code} for {repo}#{pr_number}: {resp.text[:200]}"
            )
        return _parse_unified_diff(resp.text)

    @staticmethod
    def _read_source(source: str | Path) -> str:
        if isinstance(source, Path):
            if not source.exists():
                raise GitDiffError(f"Diff file not found: {source}")
            return source.read_text()
        # str: a path that exists, else treat as raw diff text
        p = Path(source)
        try:
            if p.exists():
                return p.read_text()
        except OSError:
            pass
        return source


def _parse_unified_diff(raw: str) -> PRDiff:
    """Split a unified diff into per-file FileChange hunks.

    Deliberately minimal: enough to give the delta engine each changed file's path
    and its patch text. Not a full git parser.
    """
    files: list[FileChange] = []
    current_path: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_path, current_lines
        if current_path is not None and current_lines:
            files.append(FileChange(path=current_path, patch="\n".join(current_lines).strip()))
        current_lines = []

    for line in raw.splitlines():
        if line.startswith("diff --git "):
            flush()
            # "diff --git a/path b/path" -> take the b/ path
            parts = line.split()
            current_path = parts[-1][2:] if parts[-1].startswith("b/") else parts[-1]
        elif line.startswith("+++ b/"):
            # authoritative new path
            current_path = line[len("+++ b/"):].strip()
            current_lines.append(line)
        elif current_path is not None:
            current_lines.append(line)
    flush()

    if not files:
        raise GitDiffError("No file changes found in diff")
    return PRDiff(files=files, raw=raw)
