#!/usr/bin/env python3

# Copyright (c) 2025 Leo Moser <leo.moser@pm.me>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import shutil
import argparse

from typing import List, Type, Tuple

from librelane.common import Path
from librelane.config import Variable
from librelane.state import DesignFormat, State
from librelane.flows.sequential import SequentialFlow
from librelane.steps import (
    KLayout,
    Checker,
    Magic,
    Misc,
    Step,
    ViewsUpdate,
    MetricsUpdate,
    StepError,
    StepException,
)
from librelane.steps.klayout import KLayoutStep
from librelane.flows.flow import FlowError


@Step.factory.register()
class ReadLayout(KLayoutStep):
    """
    Reads in a layout and converts it to GDS.
    """

    id = "KLayout.ReadLayout"
    name = "Read in a layout"

    inputs = []
    outputs = [DesignFormat.GDS]

    config_vars = [
        Variable(
            "KLAYOUT_READ_LAYOUT",
            Path,
            "Path to the layout that is read in.",
        ),
    ]

    def run(self, state_in: State, **kwargs) -> Tuple[ViewsUpdate, MetricsUpdate]:
        metrics_updates: MetricsUpdate = {}
        views_updates: ViewsUpdate = {}

        input_view = self.config["KLAYOUT_READ_LAYOUT"]
        assert isinstance(input_view, Path)

        output_view = os.path.join(
            self.step_dir,
            f"{self.config['DESIGN_NAME']}.{DesignFormat.GDS.extension}",
        )

        self.run_pya_script(
            [
                sys.executable,
                os.path.join(
                    os.path.dirname(__file__),
                    "scripts",
                    "klayout",
                    "read_layout.py",
                ),
                os.path.abspath(input_view),
                os.path.abspath(output_view),
            ]
        )

        views_updates[DesignFormat.GDS] = Path(output_view)

        return views_updates, metrics_updates


@Step.factory.register()
class CheckTopLevel(KLayoutStep):
    """
    Checks that the top-level cell equals DESIGN_NAME.
    """

    id = "KLayout.CheckTopLevel"
    name = "Check top-level name"

    inputs = [DesignFormat.GDS]
    outputs = []

    def run(self, state_in: State, **kwargs) -> Tuple[ViewsUpdate, MetricsUpdate]:
        metrics_updates: MetricsUpdate = {}
        views_updates: ViewsUpdate = {}

        input_view = state_in[DesignFormat.GDS]
        assert isinstance(input_view, Path)

        self.run_pya_script(
            [
                sys.executable,
                os.path.join(
                    os.path.dirname(__file__),
                    "scripts",
                    "klayout",
                    "check_top.py",
                ),
                os.path.abspath(input_view),
                "--top",
                self.config["DESIGN_NAME"],
            ]
        )

        return views_updates, metrics_updates


@Step.factory.register()
class GenerateID(KLayoutStep):
    """
    Generates and inserts the ID
    """

    id = "KLayout.GenerateID"
    name = "Generate ID"

    inputs = [DesignFormat.GDS]
    outputs = [DesignFormat.GDS]

    config_vars = [
        Variable(
            "KLAYOUT_ID",
            str,
            "The ID to generate.",
        ),
    ]

    def run(self, state_in: State, **kwargs) -> Tuple[ViewsUpdate, MetricsUpdate]:
        metrics_updates: MetricsUpdate = {}
        views_updates: ViewsUpdate = {}

        input_view = state_in[DesignFormat.GDS]
        assert isinstance(input_view, Path)

        output_view = os.path.join(
            self.step_dir,
            f"{self.config['DESIGN_NAME']}.{DesignFormat.GDS.extension}",
        )

        self.run_pya_script(
            [
                sys.executable,
                os.path.join(
                    os.path.dirname(__file__),
                    "scripts",
                    "klayout",
                    "generate_id.py",
                ),
                os.path.abspath(input_view),
                os.path.abspath(output_view),
                "--id",
                self.config["KLAYOUT_ID"],
            ]
        )

        views_updates[DesignFormat.GDS] = Path(output_view)

        return views_updates, metrics_updates


class PrecheckFlow(SequentialFlow):

    Steps: List[Type[Step]] = [
        # Read the layout (gds, gds.gz and oas)
        ReadLayout,
        # Check that exactly one top-level cell exists
        # and that it matches "DESIGN_NAME"
        CheckTopLevel,
        # Check that cell for id exists
        # Replace cell with content
        GenerateID,
        # Check the density
        KLayout.RunDensity,
        Checker.Density,
        # Run magic DRC
        Magic.DRC,
        Checker.MagicDRC,
        # Run KLayout DRC (filler cells)
        KLayout.DRC,
        Checker.KLayoutDRC,
    ]


def main(input_layout, top_cell, design_dir, die_id):

    PDK_ROOT = os.getenv("PDK_ROOT", os.path.expanduser("~/.ciel"))
    PDK = os.getenv("PDK", "gf180mcuD")

    if PDK != "gf180mcuD":
        print(f"Error: Precheck is only supported for gf180mcuD. PDK = {PDK}")
        sys.exit(1)

    print(f"PDK_ROOT = {PDK_ROOT}")
    print(f"PDK = {PDK}")

    flow_cfg = {
        "DESIGN_NAME": top_cell,
        "KLAYOUT_READ_LAYOUT": input_layout,
        "KLAYOUT_ID": die_id,
        # Prevent false positive DRC errors in I/O cells
        "MAGIC_GDS_FLATGLOB": [
            # For contacts
            "*_CDNS_*",
            # COMP and Poly2 filler cells need to be
            # flattened to form a "filltrans" layer
            "COMP_fill_cell",
            "Poly2_fill_cell",
        ],
    }

    # Run flow
    flow = PrecheckFlow(
        flow_cfg,
        design_dir=design_dir,
        pdk_root=PDK_ROOT,
        pdk=PDK,
    )

    try:
        # Start the flow
        flow.start()
    except FlowError as e:
        print(f"Error: The precheck failed with the following exception: \n{e}")
        sys.exit(1)

    print(f"Precheck successfully completed.")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="The layout file to check and process.")
    parser.add_argument("--top", help="The top-level cell in the layout.")
    parser.add_argument("--id", default="FFFFFFFF", help="The ID to use for this chip.")
    parser.add_argument("--dir", default=".", help="Directory where to run the flow.")

    args = parser.parse_args()

    main(args.input, args.top, args.dir, args.id)
