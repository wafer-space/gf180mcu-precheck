# Copyright 2025 Leo Moser
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from .draw_qrcode import *

default_width = 10
default_height = 10

minimum_width = 1
minimum_height = 1


class qrcode(pya.PCellDeclarationHelper):
    """
    QR code generator for GF180MCU
    """

    def __init__(self):

        # Initialize parent cell
        super(qrcode, self).__init__()

        self.param(
            "pixel_width",
            self.TypeDouble,
            "Pixel Width",
            default=default_width,
            unit="um",
        )
        self.param(
            "pixel_height",
            self.TypeDouble,
            "Pixel Height",
            default=default_height,
            unit="um",
        )

        self.content = self.param(
            "content", self.TypeString, "Content", default="Placeholder"
        )

        self.metal_handle = self.param(
            "metal_level", self.TypeList, "Metal level", default="Metal5"
        )
        self.metal_handle.add_choice("Metal1", "Metal1")
        self.metal_handle.add_choice("Metal2", "Metal2")
        self.metal_handle.add_choice("Metal3", "Metal3")
        self.metal_handle.add_choice("Metal4", "Metal4")
        self.metal_handle.add_choice("Metal5", "Metal5")
        self.metal_handle.add_choice("MetalTop", "MetalTop")
        self.metal_handle.add_choice("Metal1 to Metal5", "Metal1 to Metal5")

        self.type_handle = self.param(
            "pixel_type",
            self.TypeList,
            "Pixel type",
            default="octagon",
            tooltip="Choose a different pixel type.",
        )
        self.type_handle.add_choice("octagon", "octagon")
        self.type_handle.add_choice("square", "square")

        self.param("area", self.TypeDouble, "Area", readonly=True, unit="um²")
        self.param("perim", self.TypeDouble, "Perimeter", readonly=True, unit="um")

    def display_text_impl(self):
        # Description of the cell
        return (
            "qrcode(W="
            + ("%.3f" % self.pixel_width)
            + ",H="
            + ("%.3f" % self.pixel_height)
            + ")"
        )

    def coerce_parameters_impl(self):
        # Limit length and width
        self.pixel_width = max(minimum_width, self.pixel_width)
        self.pixel_height = max(minimum_height, self.pixel_height)

        # Calculate area and perimeter
        self.area = self.pixel_width * self.pixel_height
        self.perim = 2 * (self.pixel_width + self.pixel_height)

    def can_create_from_shape_impl(self):
        # Any shape with a bounding box
        return self.shape.is_box() or self.shape.is_polygon() or self.shape.is_path()

    def parameters_from_shape_impl(self):
        # Get width and height
        self.pixel_width = self.shape.dbbox().width()
        self.pixel_height = self.shape.dbbox().height()

    def transformation_from_shape_impl(self):
        # Get the bottom left corner
        return pya.DTrans(self.shape.dbbox().left, self.shape.dbbox().bottom)

    def produce_impl(self):
        if self.metal_level == "Metal1 to Metal5":
            # Draw the qrcode
            qrcode_instance = draw_qrcode(
                self.layout,
                self.pixel_width,
                self.pixel_height,
                self.content,
                ["Metal1", "Metal2", "Metal3", "Metal4", "Metal5"],
                self.pixel_type,
            )
        else:
            # Draw the qrcode
            qrcode_instance = draw_qrcode(
                self.layout,
                self.pixel_width,
                self.pixel_height,
                self.content,
                [self.metal_level],
                self.pixel_type,
            )

        self.cell.insert(
            pya.CellInstArray(
                qrcode_instance.cell_index(),
                pya.Trans(pya.Point(0, 0)),
            )
        )
