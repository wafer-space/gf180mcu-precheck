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
@click.argument(
    "output",
    type=click.Path(exists=False, file_okay=True, dir_okay=False),
)
def check_top(
    input: str,
    output: str,
):
    ly = pya.Layout()
    ly.read(input)
    ly.write(output)

if __name__ == "__main__":
    check_top()
