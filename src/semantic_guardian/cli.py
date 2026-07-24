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


if __name__ == "__main__":
    app()
