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

import pya
import qrcode
from .layers import Layers


def draw_qrcode(layout, pixel_width, pixel_height, content, metal_level, pixel_type):

    # Create qrcode cell
    qrcode_cell = layout.cell(layout.add_cell("qrcode"))

    # Draw the QR code image
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=1,
        border=0,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="white", back_color="black")

    # Create the pixel cell
    pixel_cell = layout.cell(layout.add_cell("qrcode_pixel"))
    if pixel_type == "octagon":
        factor = 0.2
        pixel_cell.shapes(Layers.by_name(metal_level)).insert(
            pya.DPolygon(
                [
                    pya.DPoint(0 * pixel_width, factor * pixel_height),
                    pya.DPoint(0 * pixel_width, (1 - factor) * pixel_height),
                    pya.DPoint(factor * pixel_width, 1 * pixel_height),
                    pya.DPoint((1 - factor) * pixel_width, 1 * pixel_height),
                    pya.DPoint(1 * pixel_width, (1 - factor) * pixel_height),
                    pya.DPoint(1 * pixel_width, factor * pixel_height),
                    pya.DPoint((1 - factor) * pixel_width, 0 * pixel_height),
                    pya.DPoint(factor * pixel_width, 0 * pixel_height),
                ]
            )
        )
    elif pixel_type == "square":
        pixel_cell.shapes(Layers.by_name(metal_level)).insert(
            pya.DBox.new(0, 0, pixel_width, pixel_height)
        )

    width, height = img.size

    print(f"Width: {width}, Height: {height}")

    # Draw the QR code
    for y in range(height):
        print("> ", end="")

        for x in range(width):
            pixel = img.getpixel((x, y))

            if pixel == (255, 255, 255):
                print("██", end="")
                inverted_y = height - y - 1
                qrcode_cell.insert(
                    pya.DCellInstArray(
                        pixel_cell.cell_index(),
                        pya.DVector(x * pixel_width, inverted_y * pixel_height),
                    )
                )
            else:
                print("  ", end="")
        print("")

    # No metal fill
    qrcode_cell.shapes(Layers.PMNDMY).insert(
        pya.DBox.new(0, 0, pixel_width * width, pixel_height * height)
    )

    # Add boundary
    qrcode_cell.shapes(Layers.PR_bndry).insert(
        pya.DBox.new(0, 0, pixel_width * width, pixel_height * height)
    )

    return qrcode_cell
