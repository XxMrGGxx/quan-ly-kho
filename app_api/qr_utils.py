"""QR utilities.

Backend generates QR as data URI so frontend just renders it into <img>.
"""

from __future__ import annotations

import base64
import io

import qrcode


def make_qr_data_uri(text: str, *, box_size: int = 6, border: int = 2) -> str:
    """Create QR code PNG as data URI."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"

