"""CLI entry point for tokendroid."""

from __future__ import annotations

import click
from rich.console import Console


@click.group()
@click.version_option(version="0.1.0", prog_name="tokendroid")
def cli() -> None:
    """TokenDroid - Factory Droid analytics dashboard."""


@cli.group()
def stat() -> None:
    """Explore consumption stats."""


@stat.command()
@click.option("--project", "-p", default=None, help="Filter by project")
@click.option("--model", "-m", default=None, help="Filter by model")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def overview(
    project: str | None,
    model: str | None,
    output_json: bool,
) -> None:
    """Global overview: models, projects, KPIs."""
    from .display.rich_cmd import display_overview

    display_overview(project=project, model=model, json_output=output_json)


@stat.command()
@click.option("--project", "-p", default=None, help="Filter by project")
@click.option("--model", "-m", default=None, help="Filter by model")
@click.option("--from", "date_from", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--to", "date_to", default=None, help="End date (YYYY-MM-DD)")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def daily(
    project: str | None,
    model: str | None,
    date_from: str | None,
    date_to: str | None,
    output_json: bool,
) -> None:
    """Daily breakdown with sparkline bars."""
    from .display.rich_cmd import display_daily

    display_daily(
        project=project,
        model=model,
        date_from=date_from,
        date_to=date_to,
        json_output=output_json,
    )


@stat.command()
@click.option("--project", "-p", default=None, help="Filter by project")
@click.option("--model", "-m", default=None, help="Filter by model")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def weekly(
    project: str | None,
    model: str | None,
    output_json: bool,
) -> None:
    """Weekly breakdown with sparkline bars."""
    from .display.rich_cmd import display_weekly

    display_weekly(project=project, model=model, json_output=output_json)


@stat.command()
@click.option("--project", "-p", default=None, help="Filter by project")
@click.option("--model", "-m", default=None, help="Filter by model")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def monthly(
    project: str | None,
    model: str | None,
    output_json: bool,
) -> None:
    """Monthly breakdown with sparkline bars."""
    from .display.rich_cmd import display_monthly

    display_monthly(project=project, model=model, json_output=output_json)


@stat.command()
@click.option("--limit", "-n", default=15, help="Number of sessions to show")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def top(limit: int, output_json: bool) -> None:
    """Top sessions by total tokens."""
    from .display.rich_cmd import display_top_sessions

    display_top_sessions(limit=limit, json_output=output_json)


@cli.command()
def tui() -> None:
    """Launch interactive TUI dashboard."""
    from .display.tui import run_tui

    run_tui()


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind host")
@click.option("--port", default=8080, type=int, help="Bind port")
@click.option("--no-open", is_flag=True, help="Don't open browser")
def web(host: str, port: int, no_open: bool) -> None:
    """Launch web dashboard."""
    from .web.app import run_web

    run_web(host=host, port=port, open_browser=not no_open)


@cli.command()
@click.option("--full", is_flag=True, help="Force full re-sync")
def sync(full: bool) -> None:
    """Force sync cache from ~/.factory."""
    from .db import sync as do_sync

    console = Console()
    count = do_sync(full=full)
    console.print(f"[green]Synced {count} sessions[/green]")


if __name__ == "__main__":
    cli()
