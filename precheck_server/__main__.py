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
def reset(config_path: Path):
    """Reset server state."""
    import shutil

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

    # Remove storage directory
    storage_path = config.server.storage_path
    if storage_path.exists():
        click.echo(f"Removing storage directory: {storage_path}")
        shutil.rmtree(storage_path)
        click.echo("Storage directory removed")
    else:
        click.echo("Storage directory does not exist")

    click.echo("Server state reset complete")


if __name__ == "__main__":
    cli()
