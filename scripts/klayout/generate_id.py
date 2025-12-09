# Copyright (c) 2025 Leo Moser <leo.moser@pm.me>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import pya
import click

# Try to load the qrcode library
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))

try:
    # Import the qrcode library
    from qrcode_library import gf180mcu_qrcode

    # Instantiate and register the library
    gf180mcu_qrcode()
except:
    print("Error: Couldn't load the qrcode library.")
    sys.exit(1)


@click.command()
@click.argument(
    "input",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
@click.argument(
    "output",
    type=click.Path(exists=False, file_okay=True, dir_okay=False),
)
@click.option("--id", type=str, required=True)
def check_top(
    input: str,
    output: str,
    id: str,
):
    ly = pya.Layout()
    ly.read(input)

    if not ly.has_cell("gf180mcu_ws_ip__id"):
        print("Error: Couldn't find ID cell: 'gf180mcu_ws_ip__id'.")
        sys.exit(1)

    id_cell = ly.cell("gf180mcu_ws_ip__id")

    topcell = ly.top_cell()

    ly2 = pya.Layout()
    param = {
        "pixel_width": 142.8 / 21,
        "pixel_height": 142.8 / 21,
        "content": id,
        "pixel_type": "octagon",
        "metal_level": "Metal1 to Metal5",
    }
    qrcode_cell = ly2.create_cell("qrcode", "gf180mcu_qrcode", param)

    if not qrcode_cell:
        print("Error: Couldn't create the qrcode PCell.")
        sys.exit(1)

    # Flatten all levels
    qrcode_cell.flatten(-1)

    # Make sure both cells are of the same size
    assert id_cell.bbox() == qrcode_cell.bbox()

    # Clear the ID cell
    id_cell.clear()

    # Copy the contents into the id cell
    id_cell.copy_tree(qrcode_cell)

    print(f"Inserted ID: {id}")

    # Don't save PCell information in the "$$$CONTEXT_INFO$$$" cell
    # as this could cause issues further downstream
    options = pya.SaveLayoutOptions()
    options.write_context_info = False

    # Save output layout
    ly.write(output, options)


if __name__ == "__main__":
    check_top()
