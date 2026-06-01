# Copyright (c) 2025 Leo Moser <leo.moser@pm.me>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import pya
import click
import traceback

# Try to load the qrcode library
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))

try:
    # Import the qrcode library
    from pcell_library import gf180mcu_ws_pcells, Layers

    # Instantiate and register the library
    gf180mcu_ws_pcells()
except Exception as e:
    print(f"Error: Couldn't load the qrcode library: {e}")
    traceback.print_exc()
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
@click.option("--cob", type=bool, required=True)
def check_top(
    input: str,
    output: str,
    id: str,
    cob: bool,
):
    ly = pya.Layout()
    ly.read(input)

    if not len(id) == 8:
        print(f"Error: Length of ID must be exactly 8 characters, is {len(id)}.")
        sys.exit(1)

    if cob:
        if not ly.has_cell("gf180mcu_ws_ip__qrcode_id"):
            print("Error: Couldn't find ID cell: 'gf180mcu_ws_ip__qrcode_id'.")
            sys.exit(1)

        if not ly.has_cell("gf180mcu_ws_ip__shuttle_id"):
            print("Error: Couldn't find ID cell: 'gf180mcu_ws_ip__shuttle_id'.")
            sys.exit(1)

        if not ly.has_cell("gf180mcu_ws_ip__project_id"):
            print("Error: Couldn't find ID cell: 'gf180mcu_ws_ip__project_id'.")
            sys.exit(1)

        if not ly.has_cell("gf180mcu_ws_ip__marker"):
            print("Error: Couldn't find ID cell: 'gf180mcu_ws_ip__marker'.")
            sys.exit(1)

    topcell = ly.top_cell()

    qrcode_id_cell = ly.cell("gf180mcu_ws_ip__qrcode_id")
    shuttle_id_cell = ly.cell("gf180mcu_ws_ip__shuttle_id")
    project_id_cell = ly.cell("gf180mcu_ws_ip__project_id")
    marker_cell = ly.cell("gf180mcu_ws_ip__marker")
    
    # If CoB, ensure the cell instances exist
    # and their location and size is correct
    if cob:
        for cell, coords in [
            # Bottom left corner
            (qrcode_id_cell, (26,26,168.8,168.8)),
            (shuttle_id_cell, (26,175.6,85.5,371.1)),
            (project_id_cell, (175.6,26,371.1,85.5)),
            # Top right corner
            (marker_cell, (
                topcell.dbbox().width() - 36 - 245,
                topcell.dbbox().height() - 36 - 245,
                topcell.dbbox().width() - 36,
                topcell.dbbox().height() - 36
            ))
        ]:
            cell_insts = [item.child_inst() for item in cell.each_parent_inst()]
            assert (len(cell_insts) == 1), f"Error: '{cell.name}' must be instantiated exactly once."
            assert (cell_insts[0].dbbox() == pya.DBox(coords[0], coords[1], coords[2], coords[3])), f"Error: '{cell.name}' must have coordinates {coords}, is {cell_insts[0].dbbox()}."
    
    # Generate QRCode ID
    
    qrcode_width = 142.8
    qrcdoe_height =  142.8
    qrcode_pixel = 21
    qrcode_pixel_size = 142.8 / 21

    # Create the QRCode PCell instance
    ly_tmp = pya.Layout()
    param = {
        "pixel_width": qrcode_pixel_size,
        "pixel_height": qrcode_pixel_size,
        "content": id,
        "pixel_type": "octagon",
        "metal_level": "Metal1 to Metal5",
    }
    qrcode_id_cell_tmp = ly_tmp.create_cell("qrcode", "gf180mcu_ws_pcells", param)

    if not qrcode_id_cell_tmp:
        print("Error: Couldn't create qrcode PCell instance.")
        sys.exit(1)

    # Flatten all levels
    qrcode_id_cell_tmp.flatten(-1)

    if qrcode_id_cell:
        # Make sure both cells are of the same size
        assert qrcode_id_cell.bbox() == qrcode_id_cell_tmp.bbox()

        # Clear the ID cell
        qrcode_id_cell.clear()

        # Copy the contents into the id cell
        qrcode_id_cell.copy_tree(qrcode_id_cell_tmp)

    print(f"Inserted ID: {id}")

    def draw_text_id(ly, text):
        "Create text on all metal layers and flatten the cell."
        
        text_id_cell = ly.cell(ly.add_cell(f"text_id_{text}"))
        
        for layer in [Layers.Metal1, Layers.Metal2, Layers.Metal3, Layers.Metal4, Layers.Metal5]:
            param = {
                "text": text,
                "layer": layer,
                "mag": 85,
            }
            text_id_cell_layer = ly.create_cell("TEXT", "Basic", param)
            text_id_cell.insert(
                pya.DCellInstArray(
                    text_id_cell_layer,
                    pya.DPoint(
                        0, 0
                    ),
                )
            )

        if not text_id_cell:
            print("Error: Couldn't create the text id cell.")
            sys.exit(1)
        
        # Flatten all levels
        text_id_cell.flatten(-1)
        
        # Add layers
        for layer in [Layers.PR_bndry, Layers.PMNDMY, Layers.NDMY]:
            text_id_cell.shapes(layer).insert(
                pya.DBox.new(0, 0, text_id_cell.dbbox().width(), text_id_cell.dbbox().height())
            )
        
        return text_id_cell
    
    # Generate readble ID
    
    tmp_ly = pya.Layout()
    
    shuttle_id = id[0:4]
    project_id = id[4:8]
    
    shuttle_id_cell_tmp = draw_text_id(tmp_ly, shuttle_id)
    project_id_cell_tmp = draw_text_id(tmp_ly, project_id)

    if project_id_cell:
        # Make sure both cells are of the same size
        assert project_id_cell.bbox() == project_id_cell_tmp.bbox(), "project_id_cell is not of the right size"

        # Clear the ID cells
        project_id_cell.clear()

        # Copy the contents into the id cell
        project_id_cell.copy_tree(project_id_cell_tmp)

    if shuttle_id_cell:
        # Make sure both cells are of the same size
        assert shuttle_id_cell.bbox() == shuttle_id_cell_tmp.bbox(), "shuttle_id_cell is not of the right size"
    
        # Clear the ID cells
        shuttle_id_cell.clear()
    
        # Copy the contents into the id cell
        shuttle_id_cell.copy_tree(shuttle_id_cell_tmp)
    
    # Generate Marker
    
    tmp_ly = pya.Layout()
    marker_cell_tmp = tmp_ly.cell(tmp_ly.add_cell("gf180mcu_ws_ip__marker"))

    for layer in [Layers.Metal1, Layers.Metal2, Layers.Metal3, Layers.Metal4, Layers.Metal5]:
        # Create the QRCode PCell instance
        param = {
            "width": 245,
            "thick": 15,
            "layer": layer,
        }
        marker_cell_layer = tmp_ly.create_cell("marker", "gf180mcu_ws_pcells", param)

        if not marker_cell_layer:
            print("Error: Couldn't create marker PCell instance.")
            sys.exit(1)
        
        marker_cell_tmp.insert(
            pya.DCellInstArray(
                marker_cell_layer,
                pya.DPoint(
                    0, 0
                ),
            )
        )

    # Flatten all levels
    marker_cell_tmp.flatten(-1)
    
    # Add layers
    for layer in [Layers.PR_bndry]:
        marker_cell_tmp.shapes(layer).insert(
            pya.DBox.new(0, 0, marker_cell_tmp.dbbox().p2.x, marker_cell_tmp.dbbox().p2.y)
        )
    
    if marker_cell:
        # Make sure both cells are of the same size
        assert marker_cell_tmp.bbox() == marker_cell.bbox(), "marker_cell is not of the right size"
        
        # Clear the marker cells
        marker_cell.clear()
        
        # Copy the contents into the marker cell
        marker_cell.copy_tree(marker_cell_tmp)

    # Don't save PCell information in the "$$$CONTEXT_INFO$$$" cell
    # as this could cause issues further downstream
    options = pya.SaveLayoutOptions()
    options.write_context_info = False

    # Save output layout
    ly.write(output, options)

if __name__ == "__main__":
    check_top()
