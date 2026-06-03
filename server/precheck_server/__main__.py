"""CLI entry point."""

import secrets
from pathlib import Path

import click
import uvicorn

from precheck_server.config import load_config
from precheck_server.docker_client import DockerClient


@click.group()
def cli():
    """Precheck server management CLI."""
    pass


@cli.command()
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration file path",
)
def serve(config_path: Path):
    """Start the API server."""
    config = load_config(config_path)

    # Check for orphaned containers
    docker = DockerClient(
        container_prefix=config.docker.container_prefix,
        image=config.docker.image,
    )
    orphans = docker.has_orphans()
    if orphans:
        click.echo(f"Error: Found {len(orphans)} orphaned containers:", err=True)
        for name in orphans:
            click.echo(f"  - {name}", err=True)
        click.echo("\nRun 'precheck-server cleanup' first", err=True)
        raise SystemExit(1)

    # Import here to avoid circular imports
    from precheck_server.app import create_app

    app = create_app(config)
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
    )


@cli.command()
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration file path",
)
@click.option("--dry-run", is_flag=True, help="Show what would be done")
def cleanup(config_path: Path, dry_run: bool):
    """Remove orphaned Docker containers."""
    config = load_config(config_path)
    docker = DockerClient(
        container_prefix=config.docker.container_prefix,
        image=config.docker.image,
    )

    orphans = docker.has_orphans()
    if not orphans:
        click.echo("No orphaned containers found")
        return

    click.echo(f"Found {len(orphans)} orphaned containers:")
    for name in orphans:
        click.echo(f"  - {name}")

    if dry_run:
        click.echo("\nDry run - no containers removed")
        return

    removed = docker.cleanup_orphans()
    click.echo(f"\nRemoved {len(removed)} containers")


@cli.command()
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
    help="Configuration file path",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def status(config_path: Path, as_json: bool):
    """Show current server status."""
    import json as json_module

    config = load_config(config_path)
    docker = DockerClient(
        container_prefix=config.docker.container_prefix,
        image=config.docker.image,
    )

    containers = docker.list_precheck_containers()
    running = [c for c in containers if c.status == "running"]

    status_data = {
        "storage_path": str(config.server.storage_path),
        "max_concurrent": config.server.max_concurrent,
        "containers": {
            "total": len(containers),
            "running": len(running),
        },
    }

    if as_json:
        click.echo(json_module.dumps(status_data, indent=2))
    else:
        click.echo(f"Storage: {status_data['storage_path']}")
        click.echo(f"Max concurrent: {status_data['max_concurrent']}")
        click.echo(f"Containers: {len(running)} running, {len(containers)} total")


@cli.group()
def runs():
    """Manage precheck runs."""
    pass


@runs.command("list")
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
)
@click.option("--status", multiple=True, help="Filter by status")
@click.option("--json", "as_json", is_flag=True)
def runs_list(config_path: Path, status: tuple, as_json: bool):
    """List precheck runs."""
    import asyncio
    import json as json_module
    import aiosqlite

    config = load_config(config_path)
    db_path = config.server.storage_path / "precheck.db"

    if not db_path.exists():
        click.echo("No database found. Is the server running?", err=True)
        return

    async def _list():
        from precheck_server.database import Database

        db = Database(db_path, upload_expiry_minutes=config.server.upload_expiry_minutes)
        # Don't reinitialize - just connect
        db._conn = await aiosqlite.connect(db_path)
        db._conn.row_factory = aiosqlite.Row

        status_filter = list(status) if status else None
        runs = await db.list_runs(status=status_filter)
        await db.close()
        return runs

    runs_data = asyncio.run(_list())

    if as_json:
        click.echo(json_module.dumps(runs_data, indent=2, default=str))
    else:
        click.echo(f"{'ID':<36} {'STATUS':<12} {'CREATED':<24} {'TOP_CELL':<20}")
        click.echo("-" * 92)
        for run in runs_data:
            click.echo(
                f"{run['Id']:<36} {run['State']['Status']:<12} "
                f"{run['Created']:<24} {run['Config']['Labels']['top_cell']:<20}"
            )


@runs.command("inspect")
@click.argument("run_id")
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
)
def runs_inspect(run_id: str, config_path: Path):
    """Inspect a precheck run."""
    import asyncio
    import json as json_module
    import aiosqlite

    config = load_config(config_path)
    db_path = config.server.storage_path / "precheck.db"

    if not db_path.exists():
        click.echo("No database found.", err=True)
        return

    async def _get():
        from precheck_server.database import Database

        db = Database(db_path)
        db._conn = await aiosqlite.connect(db_path)
        db._conn.row_factory = aiosqlite.Row
        run = await db.get_run(run_id)
        await db.close()
        return run

    run = asyncio.run(_get())

    if not run:
        click.echo(f"No such run: {run_id}", err=True)
        return

    click.echo(json_module.dumps(run, indent=2, default=str))


@runs.command("delete")
@click.argument("run_id")
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
)
@click.option("--force", is_flag=True, help="Skip confirmation")
def runs_delete(run_id: str, config_path: Path, force: bool):
    """Delete a precheck run."""
    import asyncio
    import shutil
    import aiosqlite

    config = load_config(config_path)
    db_path = config.server.storage_path / "precheck.db"

    if not db_path.exists():
        click.echo("No database found.", err=True)
        return

    async def _delete():
        from precheck_server.database import Database

        db = Database(db_path)
        db._conn = await aiosqlite.connect(db_path)
        db._conn.row_factory = aiosqlite.Row

        run = await db.get_run(run_id)
        if not run:
            return None

        if not force:
            click.confirm(f"Delete run {run_id}?", abort=True)

        # Delete files
        run_dir = Path(run["_run_dir"])
        if run_dir.exists():
            shutil.rmtree(run_dir)

        await db.delete_run(run_id)
        await db.close()
        return run_id

    deleted = asyncio.run(_delete())

    if deleted:
        click.echo(f"Deleted run: {deleted}")
    else:
        click.echo(f"No such run: {run_id}", err=True)


@runs.command("prune")
@click.option(
    "--config",
    "config_path",
    default="config.toml",
    type=click.Path(exists=True, path_type=Path),
)
@click.option("--status", multiple=True, help="Only prune runs with these statuses")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
def runs_prune(config_path: Path, status: tuple, dry_run: bool):
    """Delete old precheck runs."""
    import asyncio
    import shutil
    import aiosqlite

    config = load_config(config_path)
    db_path = config.server.storage_path / "precheck.db"

    if not db_path.exists():
        click.echo("No database found.", err=True)
        return

    async def _prune():
        from precheck_server.database import Database

        db = Database(db_path)
        db._conn = await aiosqlite.connect(db_path)
        db._conn.row_factory = aiosqlite.Row

        status_filter = list(status) if status else ["completed", "failed", "cancelled"]
        runs = await db.list_runs(status=status_filter)

        if not runs:
            click.echo("No runs to prune")
            return []

        click.echo(f"Found {len(runs)} runs to prune:")
        total_size = 0
        for run in runs:
            run_dir = Path(run["_run_dir"])
            size = sum(f.stat().st_size for f in run_dir.rglob("*") if f.is_file()) if run_dir.exists() else 0
            total_size += size
            click.echo(f"  {run['Id']}  {run['State']['Status']:<12}  {size / 1024 / 1024:.1f} MB")

        click.echo(f"\nTotal: {total_size / 1024 / 1024:.1f} MB")

        if dry_run:
            click.echo("\nDry run - no runs deleted")
            return []

        if not click.confirm("\nDelete these runs?"):
            return []

        deleted = []
        for run in runs:
            run_dir = Path(run["_run_dir"])
            if run_dir.exists():
                shutil.rmtree(run_dir)
            await db.delete_run(run["Id"])
            deleted.append(run["Id"])

        await db.close()
        return deleted

    deleted = asyncio.run(_prune())
    if deleted:
        click.echo(f"\nDeleted {len(deleted)} runs")


@cli.group()
def apikey():
    """Manage API keys."""
    pass


@apikey.command("generate")
@click.option("--name", default="", help="Optional name for the key")
def apikey_generate(name: str):
    """Generate a new API key."""
    key = f"ws_key_{secrets.token_hex(24)}"

    click.echo(f"\nGenerated API key:")
    click.echo(f"  Name: {name or '(unnamed)'}")
    click.echo(f"  Key:  {key}")
    click.echo(f"\nAdd to config.toml:")
    click.echo(f'  [[auth.api_keys]]')
    click.echo(f'  name = "{name}"')
    click.echo(f'  key = "{key}"')
    click.echo(f"\n⚠️  Save this key now - it cannot be retrieved later")


if __name__ == "__main__":
    cli()
