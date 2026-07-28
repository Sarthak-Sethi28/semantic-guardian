"""Semantic Guardian command-line entrypoint.

Thin CLI shell for now; commands are wired up per-issue as modules land.
"""
from __future__ import annotations

import typer
from rich.console import Console

from . import __version__

app = typer.Typer(
    name="semantic-guardian",
    help="Catch silent semantic data failures using DataHub lineage.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.callback()
def main() -> None:
    """Semantic Guardian: catch silent semantic data failures using DataHub lineage."""


@app.command()
def version() -> None:
    """Print the Semantic Guardian version."""
    console.print(f"Semantic Guardian [bold cyan]v{__version__}[/]")


@app.command()
def review(
    urn: str = typer.Argument(..., help="Dataset URN the change targets"),
    diff: str = typer.Option(None, "--diff", help="Path to a local unified diff file"),
    pr: int = typer.Option(None, "--pr", help="GitHub PR number (repo via --repo)"),
    repo: str = typer.Option(None, "--repo", help="owner/name for --pr"),
) -> None:
    """Ingest a change (local diff or PR) as a review event and show the request (#16).

    This is the causal event the semantic-delta engine reasons over. Without an LLM key
    it stops after assembling + anomaly-screening the request; the engine call is #5.
    """
    from .anomaly import ColumnProfile  # noqa: F401  (kept for future profile screening)
    from .clients.datahub import DataHubClient, DataHubError
    from .clients.git import GitClient, GitDiffError
    from .trigger import build_review_request

    if not diff and pr is None:
        console.print("[red]Provide --diff <file> or --pr <n> (with --repo).[/]")
        raise typer.Exit(2)

    try:
        gc = GitClient()
        prdiff = gc.get_local_diff(diff) if diff else gc.get_pr_diff(repo, pr)
    except GitDiffError as exc:
        console.print(f"[red]Could not read the change:[/] {exc}")
        raise typer.Exit(1) from exc

    try:
        client = DataHubClient()
        req = build_review_request(client, urn, prdiff, event=("local" if diff else f"pr:{pr}"))
    except DataHubError as exc:
        console.print(f"[red]DataHub error:[/] {exc}")
        raise typer.Exit(1) from exc

    ds_label = urn.split(",")[-2] if "," in urn else urn
    console.print(f"[bold]Review event:[/] {req.event}  ·  dataset [cyan]{ds_label}[/]")
    if not req.deltas:
        console.print("  No column changes detected in this diff.")
        return
    console.print(f"  Changed columns: {', '.join(req.changed_fields)}")
    for d in req.deltas:
        console.print(f"    [bold]{d.change.field_path}[/] ([yellow]{d.change.change_kind}[/])")
        console.print(f"      before: {d.change.before_expr}")
        console.print(f"      after:  {d.change.after_expr}")
        if d.column.description:
            console.print(f"      declared: [dim]{d.column.description}[/]")
    console.print("\n[dim]Next: the semantic-delta engine (#5) reasons over this event.[/]")


@app.command()
def inspect(urn: str) -> None:
    """Inspect a dataset in DataHub: schema, owners, and downstream ML lineage."""
    from .clients.datahub import DataHubClient, DataHubError

    try:
        client = DataHubClient()
        ds = client.get_dataset(urn)
        owners = client.get_owners(urn)
        ml = client.get_downstream_ml(urn)
    except DataHubError as exc:
        console.print(f"[red]DataHub error:[/] {exc}")
        raise typer.Exit(1) from exc

    owner_names = ", ".join(o.username for o in owners) or "—"
    console.print(f"[bold cyan]{ds.name}[/] [dim]({ds.platform})[/]")
    console.print(f"  fields: {len(ds.fields)} | owners: {owner_names}")
    for path, f in ds.fields.items():
        desc = f"· {f.description}" if f.description else ""
        console.print(f"    - {path} [dim]{f.native_type or ''}[/] {desc}")
    console.print(f"  downstream ML entities: [bold]{len(ml)}[/]")
    for r in ml:
        console.print(f"    → {r.relationship}: {r.urn}")


if __name__ == "__main__":
    app()
