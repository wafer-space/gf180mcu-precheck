#!/usr/bin/env python3

# Copyright (c) 2025 Leo Moser <leo.moser@pm.me>
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import shutil
import argparse

from typing import List, Type, Tuple, Optional

from librelane.common import Path, get_script_dir, mkdirp
from librelane.logging import info
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
from librelane.steps.checker import MetricChecker
from librelane.flows.flow import FlowError


@Step.factory.register()
class ReadLayout(KLayoutStep):
    """
    Reads in a layout and converts it to GDS.
    """

    id = "KLayout.ReadLayout"
    name = "Read in the layout"

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
class WriteLayout(KLayoutStep):
    """
    Write the layout to an external path.
    """

    id = "KLayout.WriteLayout"
    name = "Write the layout"

    inputs = [DesignFormat.GDS]
    outputs = []

    config_vars = [
        Variable(
            "KLAYOUT_WRITE_LAYOUT",
            Optional[str],
            "Path to the layout that is read in.",
        ),
    ]

    def run(self, state_in: State, **kwargs) -> Tuple[ViewsUpdate, MetricsUpdate]:
        metrics_updates: MetricsUpdate = {}
        views_updates: ViewsUpdate = {}

        input_view = state_in[DesignFormat.GDS]
        output_view = self.config["KLAYOUT_WRITE_LAYOUT"]

        if output_view:
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

        return views_updates, metrics_updates


@Step.factory.register()
class CheckTopLevel(KLayoutStep):
    """
    Checks that the top-level cell equals DESIGN_NAME.
    """

    id = "KLayout.CheckTopLevel"
    name = "Check the top-level name"

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
class CheckSize(KLayoutStep):
    """
    Checks that the origin is at 0, 0 and the dimensions match the selected slot size.
    """

    id = "KLayout.CheckSize"
    name = "Check Size"

    inputs = [DesignFormat.GDS]
    outputs = []

    config_vars = [
        Variable(
            "KLAYOUT_SLOT",
            str,
            "The slot size of the design in order to check the dimensions.",
        ),
    ]

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
                    "check_size.py",
                ),
                os.path.abspath(input_view),
                "--slot",
                self.config["KLAYOUT_SLOT"],
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


@Step.factory.register()
class ZeroAreaPolygons(KLayoutStep):
    """
    Find zero area polygons
    """

    id = "KLayout.ZeroAreaPolygons"
    name = "Find Zero Area Polygons"

    inputs = [DesignFormat.GDS]
    outputs = []

    def run(self, state_in: State, **kwargs) -> Tuple[ViewsUpdate, MetricsUpdate]:
        metrics_updates: MetricsUpdate = {}
        views_updates: ViewsUpdate = {}

        kwargs, env = self.extract_env(kwargs)

        input_gds = state_in[DesignFormat.GDS]
        assert isinstance(input_gds, Path)

        script = os.path.join(
            os.path.dirname(__file__),
            "scripts",
            "klayout",
            "zero_area.drc",
        )

        reports_dir = os.path.join(self.step_dir, "reports")
        mkdirp(reports_dir)
        lyrdb_report = os.path.join(reports_dir, "density.klayout.lyrdb")
        json_report = os.path.join(reports_dir, "density.klayout.json")

        info(f"Running KLayout zero area polygons check…")

        # Not a pya script
        subprocess_result = self.run_subprocess(
            [
                "klayout",
                "-b",
                "-zz",
                "-r",
                script,
                "-rd",
                f"input={os.path.abspath(input_gds)}",
                "-rd",
                f"topcell={self.config['DESIGN_NAME']}",
                "-rd",
                f"report={os.path.abspath(lyrdb_report)}",
            ],
            env=env,
        )

        subprocess_result = self.run_pya_script(
            [
                "python3",
                os.path.join(
                    get_script_dir(),
                    "klayout",
                    "xml_drc_report_to_json.py",
                ),
                f"--xml-file={os.path.abspath(lyrdb_report)}",
                f"--json-file={os.path.abspath(json_report)}",
                "--metric=klayout__zero_area_polygons__count",
            ],
            env=env,
            log_to=os.path.join(self.step_dir, "xml_drc_report_to_json.log"),
        )

        return views_updates, subprocess_result["generated_metrics"]


@Step.factory.register()
class CheckerKLayoutZeroAreaPolygons(MetricChecker):
    id = "Checker.KLayoutZeroAreaPolygons"
    name = "KLayout Zero Area Polygons Checker"
    long_name = "KLayout Zero Area Polygons Checker"
    deferred = False

    metric_name = "klayout__zero_area_polygons__count"
    metric_description = "KLayout zero area polygons count"

    error_on_var = Variable(
        "ERROR_ON_KLAYOUT_ZERO_AREA_POLYGONS",
        bool,
        "Checks for zero area polygon violations after KLayout.ZeroAreaPolygons is executed and exits the flow if any was found.",
        default=True,
    )
    config_vars = [error_on_var]


class PrecheckFlow(SequentialFlow):

    Steps: List[Type[Step]] = [
        # Read the layout (gds, gds.gz and oas)
        ReadLayout,
        # Check that exactly one top-level cell exists
        # and that it matches "DESIGN_NAME"
        CheckTopLevel,
        # Checks that the origin is at 0, 0 and the
        # dimensions match the selected slot size.
        CheckSize,
        # Check that cell for id exists
        # Replace cell with content
        GenerateID,
        # Check the density
        KLayout.Density,
        Checker.KLayoutDensity,
        # Detect zero area polygons
        ZeroAreaPolygons,
        CheckerKLayoutZeroAreaPolygons,
        # Run KLayout antenna check
        KLayout.Antenna,
        Checker.KLayoutAntenna,
        # Run magic DRC
        Magic.DRC,
        Checker.MagicDRC,
        # Run KLayout DRC (filler cells)
        KLayout.DRC,
        Checker.KLayoutDRC,
        # Write the layout
        WriteLayout,
    ]


def main(
    input_layout,
    output_layout,
    top_cell,
    design_dir,
    die_id,
    slot,
    tag,
    last_run,
    frm,
    to,
    skip,
    with_initial_state,
):

    PDK_ROOT = os.getenv("PDK_ROOT", os.path.expanduser("gf180mcu"))
    PDK = os.getenv("PDK", "gf180mcuD")

    os.environ["PDK_ROOT"] = PDK_ROOT
    os.environ["PDK"] = PDK

    if PDK != "gf180mcuD":
        print(f"Error: Precheck is only supported for gf180mcuD. PDK = {PDK}")
        sys.exit(1)

    print(f"PDK_ROOT = {PDK_ROOT}")
    print(f"PDK = {PDK}")

    if not top_cell:
        top_cell = os.path.basename(input_layout).split(os.path.extsep)[0]

    print(f"Top cell: {top_cell}")
    print(f"Die ID: {die_id}")
    print(f"Slot: {slot}")

    flow_cfg = {
        "DESIGN_NAME": top_cell,
        "KLAYOUT_READ_LAYOUT": input_layout,
        "KLAYOUT_WRITE_LAYOUT": output_layout,
        "KLAYOUT_ID": die_id,
        "KLAYOUT_SLOT": slot,
        # Prevent false positive DRC errors in I/O cells
        "MAGIC_GDS_FLATGLOB": [
            # For contacts
            "*_CDNS_*",
            # Foundry provided SRAMs
            "*$$*",
            "M1_N*",
            "M1_P*",
            "M2_M1*",
            "M3_M2*",
            "nmos_5p0*",
            "nmos_1p2*",
            "pmos_5p0*",
            "pmos_1p2*",
            "via1_*",
            "ypass_gate*",
            "G_ring_*",
            # These additional cells must be flattened to get rid of 3.3V devices
            # (DUALGATE drawn into high-level cells)
            "dcap_103*",
            "din_*",
            "mux821_*",
            "rdummy_*",
            "pmoscap_*",
            "xdec_*",
            "ypredec*",
            "xpredec*",
            "prexdec_*",
            "xdec8_*",
            "xdec16_*",
            "xdec32_*",
            "sa_*",
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
        flow.start(
            tag=tag,
            last_run=last_run,
            frm=frm,
            to=to,
            skip=skip,
            with_initial_state=with_initial_state,
        )
    except FlowError as e:
        print(f"Error: The precheck failed with the following exception: \n{e}")
        sys.exit(1)

    print(f"Precheck successfully completed.")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", help="The layout file to check and process.", required=True
    )
    parser.add_argument("--output", help="The layout file to write.", default=None)
    parser.add_argument("--top", help="The top-level cell in the layout.")
    parser.add_argument("--id", default="FFFFFFFF", help="The ID to use for this chip.")
    parser.add_argument("--dir", default=".", help="Directory where to run the flow.")
    parser.add_argument(
        "--slot",
        default="1x1",
        choices=["1x1", "0p5x1", "1x0p5", "0p5x0p5"],
        help="Slot size of the design.",
    )
    parser.add_argument(
        "--run-tag",
        help="Use a tag for the run directory instead of the timestamp.",
    )
    parser.add_argument(
        "--last-run",
        help="Use the last run as the run tag.",
    )
    parser.add_argument(
        "--from",
        help="Start from a step with this id.",
    )
    parser.add_argument(
        "--to",
        help="Stop at a step with this id.",
    )
    parser.add_argument(
        "--skip",
        nargs="+",
        help="Skip these steps.",
    )
    parser.add_argument(
        "--with-initial-state",
        help="Use this JSON file as an initial state. If this is not specified, the latest `state_out.json` of the run directory will be used. If none exist, an empty initial state is created.",
    )

    args = parser.parse_args()

    print(args.skip)

    main(
        args.input,
        args.output,
        args.top,
        args.dir,
        args.id,
        args.slot,
        args.run_tag,
        args.last_run,
        getattr(args, "from", None),
        args.to,
        args.skip,
        args.with_initial_state,
    )
