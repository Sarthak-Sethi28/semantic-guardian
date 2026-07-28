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
