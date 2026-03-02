from __future__ import annotations

from pathlib import Path

import typer
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from zotero_to_md.config import load_config
from zotero_to_md.errors import ConfigError, SyncError, ZoteroClientError
from zotero_to_md.sync import run_sync

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)


@app.callback()
def _root() -> None:
    """zotero-to-md CLI."""


@app.command("sync")
def sync(
    target_destination_path: Path = typer.Option(
        ...,
        "--target-destination-path",
        file_okay=False,
        dir_okay=True,
        exists=False,
        resolve_path=False,
        help="Absolute path to the destination directory for Markdown output.",
    ),
    root_collection: str = typer.Option(
        ...,
        "--root-collection",
        help="Name of the root Zotero collection to sync.",
    ),
    recursive: bool = typer.Option(
        True,
        "--recursive/--no-recursive",
        help="Include subcollections recursively.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be processed without writing files or state.",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose output."),
) -> None:
    try:
        config = load_config(
            target_destination_path=target_destination_path,
            root_collection=root_collection,
            recursive=recursive,
            dry_run=dry_run,
            verbose=verbose,
        )
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            transient=False,
        ) as progress:
            task_id = progress.add_task("syncing zotero items", total=1)

            def on_progress(current: int, total: int, label: str | None) -> None:
                safe_total = max(total, 1)
                progress.update(task_id, total=safe_total, completed=min(current, safe_total))
                if label:
                    progress.update(task_id, description=f"syncing zotero items [{label}]")

            stats = run_sync(
                config,
                log=lambda message: typer.echo(message, err=True),
                progress=on_progress,
            )
    except (ConfigError, ZoteroClientError, SyncError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:  # pragma: no cover - defensive fallback
        typer.echo(f"unexpected error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo("sync complete")
    typer.echo(f"discovered: {stats.discovered}")
    typer.echo(f"skipped_existing: {stats.skipped_existing}")
    if dry_run:
        typer.echo(f"would_process: {stats.would_process}")
    else:
        typer.echo(f"processed: {stats.processed}")
        typer.echo(f"errors: {stats.errors}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
