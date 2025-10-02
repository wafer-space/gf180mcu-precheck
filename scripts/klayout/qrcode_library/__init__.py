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

from .qrcode import *


class gf180mcu_qrcode(pya.Library):
    """
    Qr code library
    """

    def __init__(self):
        # Set the description
        self.description = "GF180MCU QR code"

        # Create the PCell declaration
        self.layout().register_pcell("qrcode", qrcode())

        # Register us with the name "gf180mcu_qrcode".
        self.register("gf180mcu_qrcode")
