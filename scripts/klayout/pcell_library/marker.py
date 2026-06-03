# Copyright 2026 Leo Moser
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

import pya
import math
from .layers import Layers

class marker(pya.PCellDeclarationHelper):
    """
    Marker generator for GF180MCU
    """

    min_width = 50
    min_thick = 10

    def __init__(self):

        # Initialize parent cell
        super(marker, self).__init__()

        self.param(
            "width",
            self.TypeDouble,
            "Width",
            default=100,
            unit="um",
        )
        self.param(
            "thick",
            self.TypeDouble,
            "Thickness",
            default=10,
            unit="um",
        )

        self.layer = self.param(
            "layer",
            self.TypeLayer,
            "Layer",
            default=Layers.Metal1
        )

        self.param("area", self.TypeDouble, "Area", readonly=True, unit="um²")
        self.param("perim", self.TypeDouble, "Perimeter", readonly=True, unit="um")

    def display_text_impl(self):
        # Description of the cell
        return (
            "marker(W="
            + ("%.3f" % self.width)
            + ",T="
            + ("%.3f" % self.thick)
            + ")"
        )

    def coerce_parameters_impl(self):
        # Limit length and width
        self.width = max(self.min_width, self.width)
        self.thick = max(self.min_thick, self.thick)

        # Calculate area and perimeter
        self.area = self.width * self.width
        self.perim = 4 * self.width

    def can_create_from_shape_impl(self):
        # Any shape with a bounding box
        return self.shape.is_box() or self.shape.is_polygon() or self.shape.is_path()

    def parameters_from_shape_impl(self):
        # Get width and height
        self.width = self.shape.dbbox().width()

    def transformation_from_shape_impl(self):
        # Get the bottom left corner
        return pya.DTrans(self.shape.dbbox().left, self.shape.dbbox().bottom)

    def produce_impl(self):
        # Make sure points are aligned
        # with manufacturing grid
        dbu = 0.005
        
        to_um = pya.CplxTrans(dbu)
        from_um = to_um.inverted()
        
        hypotenuse = math.sqrt(2 * self.thick**2)
        
        # Outer triangle
        points = []
        
        # Top right
        points.append(pya.DPoint(self.width, self.width))
        
        # Bottom right
        points.append(pya.DPoint(self.width - self.thick + self.thick, self.thick + hypotenuse - self.thick/2))
        points.append(pya.DPoint(self.width - (self.thick + hypotenuse - self.thick/2), self.thick + hypotenuse - self.thick/2))
        
        # Top left
        points.append(pya.DPoint(self.thick + hypotenuse - self.thick/2, self.width - (self.thick + hypotenuse - self.thick/2)))
        points.append(pya.DPoint(self.thick + hypotenuse - self.thick/2, self.width - self.thick + self.thick))

        region_outer = pya.Region(from_um * pya.DPolygon(points))

        # Inner triangle
        points = []
        
        # Top right
        points.append(pya.DPoint(self.width - self.thick, self.width - self.thick))
        
        # Bottom right
        points.append(pya.DPoint(self.width - self.thick, self.thick + hypotenuse + self.thick/2))
        points.append(pya.DPoint(self.width - self.thick - self.thick/2, self.thick + hypotenuse + self.thick/2))
        
        # Top left
        points.append(pya.DPoint(self.thick + hypotenuse + self.thick/2, self.width - self.thick - self.thick/2))
        points.append(pya.DPoint(self.thick + hypotenuse + self.thick/2, self.width - self.thick))
        
        region_inner = pya.Region(from_um * pya.DPolygon(points))
        
        for polygon in (region_outer - region_inner).each():
            self.cell.shapes(self.layer).insert(to_um * polygon)
