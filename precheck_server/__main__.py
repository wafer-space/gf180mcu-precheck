"""CLI entry point."""

import click


@click.group()
def cli():
    """Precheck server management CLI."""
    pass


@cli.command()
def serve():
    """Start the API server."""
    click.echo("Server not implemented yet")


if __name__ == "__main__":
    cli()
