# Copyright (c) 2025 Leo Moser <leo.moser@pm.me>
# SPDX-License-Identifier: Apache-2.0

import sys
import pya
import click


@click.command()
@click.argument(
    "input",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
@click.option("--top", required=True)
def check_top(
    input: str,
    top: str,
):
    ly = pya.Layout()
    ly.read(input)

    if len(ly.top_cells()) > 1:
        print(f"[Error] More than one top-level cell in {input}!")
        sys.exit(1)

    if not ly.top_cell():
        print(f"[Error] No top-level cell in {input}!")
        sys.exit(1)

    if ly.top_cell().name != top:
        print(f"[Error] No top-level cell in {input}!")
        sys.exit(1)

    print(f"Design name '{top}' matches top-level cell in {input}.")
    sys.exit(0)


if __name__ == "__main__":
    check_top()
