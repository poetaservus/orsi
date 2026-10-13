"""Encode the unchanged transparent logo as a Windows multi-resolution icon."""
from pathlib import Path
import struct

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter


SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def frame(source, side):
    image = QImage(side, side, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    content = source.scaled(round(side * .90), round(side * .90),
        Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(image)
    painter.drawImage((side - content.width()) // 2, (side - content.height()) // 2, content)
    painter.end()
    return image


def encode(image):
    side = image.width()
    if side >= 128:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise ValueError("Cannot encode the icon image.")
        return bytes(buffer.data())
    # Little-endian ARGB32 is BGRA, matching Windows' bottom-up 32-bit DIBs.
    pixels = bytes(image.constBits())
    rows = [pixels[y * image.bytesPerLine():y * image.bytesPerLine() + side * 4] for y in range(side)]
    masks = []
    for row in rows:
        mask = bytearray(((side + 31) // 32) * 4)
        for x in range(side):
            if row[x * 4 + 3] == 0:
                mask[x // 8] |= 1 << (7 - x % 8)
        masks.append(bytes(mask))
    data = b"".join(reversed(rows)) + b"".join(reversed(masks))
    return struct.pack("<IiiHHIIiiII", 40, side, side * 2, 1, 32, 0, len(data), 0, 0, 0, 0) + data


def build(source, destination):
    source = QImage(str(source))
    if source.isNull() or not source.hasAlphaChannel():
        raise ValueError("A readable transparent logo is required.")
    images = [encode(frame(source, side)) for side in SIZES]
    offset, entries = 6 + 16 * len(images), []
    for side, data in zip(SIZES, images):
        entries.append(struct.pack("<BBBBHHII", side % 256, side % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    Path(destination).write_bytes(struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(images))


if __name__ == "__main__":
    assets = Path(__file__).resolve().parents[1] / "app/ui/assets"
    build(assets / "bsw_o.png", assets / "orsi-app.ico")
    # Preserve the resource used by existing external launchers/shortcuts.
    (assets / "orsi.ico").write_bytes((assets / "orsi-app.ico").read_bytes())
