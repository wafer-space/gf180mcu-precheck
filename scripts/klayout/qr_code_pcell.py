# Copyright (c) 2025 Leo Moser <leo.moser@pm.me>
# SPDX-License-Identifier: Apache-2.0

import qrcode

img = qrcode.make("Placeholder")

print(img)
type(img)  # qrcode.image.pil.PilImage

