# Copyright (c) 2025 Leo Moser <leo.moser@pm.me>
# SPDX-License-Identifier: Apache-2.0

import sys
import pya
import click

USER_PROJECT_WIDTH = 3880
USER_PROJECT_HEIGHT = 5070

SEAL_RING_SIZE = 26

USER_DIE_WIDTH = USER_PROJECT_WIDTH + 2 * SEAL_RING_SIZE
USER_DIE_HEIGHT = USER_PROJECT_HEIGHT + 2 * SEAL_RING_SIZE

SAW_STREET_MINIMUM = 60


@click.command()
@click.argument(
    "input",
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
@click.option(
    "--slot",
    type=str,
)
def check_top(
    input: str,
    slot: str,
):
    ly = pya.Layout()
    ly.read(input)

    # Check origin
    if ly.top_cell().dbbox().p1 != pya.DPoint(0, 0):
        print("[Error]: Layout origin is not at (0, 0)")
        sys.exit(-1)

    # Check dbu
    if ly.dbu != 0.001:
        print("[Error]: Database unit (dbu) is not 0.001um.")
        sys.exit(-1)

    # Check max metal layer
    Via5 = pya.LayerInfo(82, 0)
    MetalTop = pya.LayerInfo(53, 0)

    Via5_region = pya.Region(ly.top_cell().begin_shapes_rec(ly.layer(Via5)))
    MetalTop_region = pya.Region(ly.top_cell().begin_shapes_rec(ly.layer(MetalTop)))

    if Via5_region.count() > 0:
        print(
            f"[Error]: Layer 'Via5' is used. wafers.space uses the 5LM metal stackup."
        )
        sys.exit(-1)

    if MetalTop_region.count() > 0:
        print(
            f"[Error]: Layer 'MetalTop' is used. wafers.space uses the 5LM metal stackup."
        )
        sys.exit(-1)

    # Check sealring exists
    GUARD_RING_MK = pya.LayerInfo(167, 5)
    GUARD_RING_MK_region = pya.Region(
        ly.top_cell().begin_shapes_rec(ly.layer(GUARD_RING_MK))
    )

    if GUARD_RING_MK_region.count() == 0:
        print(
            f"[Error]: Layer 'GUARD_RING_MK' is not used. wafers.space requires a seal ring (guard ring) around the die."
        )
        sys.exit(-1)

    # Check layout size
    layout_width = ly.top_cell().dbbox().width()
    layout_height = ly.top_cell().dbbox().height()

    print("Layout size:")
    print(f"layout width:  {layout_width}")
    print(f"layout height: {layout_height}")

    if slot == "1x1":
        div_x = 1
        div_y = 1
    elif slot == "0p5x1":
        div_x = 2
        div_y = 1
    elif slot == "1x0p5":
        div_x = 1
        div_y = 2
    elif slot == "0p5x0p5":
        div_x = 2
        div_y = 2
    else:
        print(f"[Error]: Unsupported slot size: {slot}")
        sys.exit(-1)

    slot_width = (USER_DIE_WIDTH - ((div_x - 1) * SAW_STREET_MINIMUM)) / div_x
    slot_height = (USER_DIE_HEIGHT - ((div_y - 1) * SAW_STREET_MINIMUM)) / div_y

    print("Expected slot size:")
    print(f"slot width:  {slot_width}")
    print(f"slot height: {slot_height}")

    if layout_width != slot_width or layout_height != slot_height:
        print(f"[Error]: Layout size does not match slot size {slot}.")
        sys.exit(-1)

    print(f"Layout dimension matches the selected slot size {slot}.")
    sys.exit(0)


if __name__ == "__main__":
    check_top()
