"""CLI entry point."""

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


if __name__ == "__main__":
    cli()
