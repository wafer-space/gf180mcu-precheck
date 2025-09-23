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
@click.option("--id", type=str, required=True)
def check_top(
    input: str,
    output: str,
    id: str,
):
    ly = pya.Layout()
    ly.read(input)
    
    if id.isdigit() and len(id) == 8:
        print("OK")

    # the layer where to put the text to
    txt_layer = pya.LayerInfo(1, 0)

    # create layer 1/0
    ly.layer(txt_layer)

    topcell = ly.top_cell()
    param  = { "layer": txt_layer, "text": "ID:" + id, "mag": 10 }

    # create the PCell variant
    txtcell = ly.create_cell("TEXT", "Basic", param)

    # insert the PCell variant into the top cell 
    trans = pya.Trans(0, False, 0, 0)
    topcell.insert(pya.CellInstArray.new(txtcell.cell_index(), trans))

    print(f"Inserted ID {id}.")
    
    ly.write(output)

if __name__ == "__main__":
    check_top()
