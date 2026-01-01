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
    options = pya.LoadLayoutOptions()
    lm = pya.LayerMap()

    # Dummy comp to active comp
    lm.map(pya.LayerInfo(22, 4), 0, pya.LayerInfo(22, 0))

    # Dummy poly2 to active poly2
    lm.map(pya.LayerInfo(30, 4), 1, pya.LayerInfo(30, 0))

    # Dummy metal to active metal
    lm.map(pya.LayerInfo(34, 4), 2, pya.LayerInfo(34, 0))
    lm.map(pya.LayerInfo(36, 4), 3, pya.LayerInfo(36, 0))
    lm.map(pya.LayerInfo(42, 4), 4, pya.LayerInfo(42, 0))
    lm.map(pya.LayerInfo(46, 4), 5, pya.LayerInfo(46, 0))
    lm.map(pya.LayerInfo(81, 4), 6, pya.LayerInfo(81, 0))

    options.set_layer_map(lm, True)

    ly = pya.Layout()
    ly.read(input, options)
    ly.write(output)


if __name__ == "__main__":
    check_top()
