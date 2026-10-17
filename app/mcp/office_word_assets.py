"""Bounded immutable local picture assets; no remote URLs or model byte payloads."""
import base64
from hashlib import sha256
from io import BytesIO

from app.mcp.office_word_native import reject, PKG, W

MAX_IMAGE_BYTES = 256 * 1024
MAX_MEDIA_BYTES = 1024 * 1024
MAX_IMAGES = 8
MAX_DIMENSION = 2048
MAX_PIXELS = 4_000_000
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
PIC = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"
A14 = "{http://schemas.microsoft.com/office/drawing/2010/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def inspect_image(data):
    from PIL import Image, UnidentifiedImageError
    if not data or len(data) > MAX_IMAGE_BYTES:
        reject("Picture file exceeds the 256-KiB limit.")
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            format = image.format
            if format not in {"PNG", "JPEG"}:
                reject("Pictures must be PNG or JPEG.")
            if (not 1 <= width <= MAX_DIMENSION or not 1 <= height <= MAX_DIMENSION
                    or width * height > MAX_PIXELS or getattr(image, "n_frames", 1) != 1):
                reject("Picture dimensions exceed 2048 per side or four million pixels; animations are unsupported.")
            image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        reject("Picture decoding failed.")
    return {"format": format, "width_px": width, "height_px": height, "bytes": len(data)}


class WordAssets:
    def __init__(self):
        self.assets, self.pending = {}, {}

    def clear(self):
        self.assets.clear()
        self.pending.clear()

    def chunk(self, session, asset, offset, data, final):
        if asset in self.assets or not isinstance(offset, int) or offset < 0:
            reject("Picture registration is immutable; register a fresh asset.")
        if len(self.assets) + len(self.pending) >= MAX_IMAGES and asset not in self.pending:
            reject("Picture registration exceeds eight assets per connection.")
        prior_session, prior = self.pending.get(asset, (session, b""))
        if prior_session != session or offset != len(prior):
            reject("Picture registration sequence is invalid.")
        try:
            chunk = base64.b64decode(data, validate=True)
        except (ValueError, TypeError):
            reject("Picture registration bytes are invalid.")
        value = prior + chunk
        total = sum(len(v[1]) for v in self.assets.values()) + sum(len(v[1]) for k, v in self.pending.items() if k != asset)
        if len(chunk) > 24000 or len(value) > MAX_IMAGE_BYTES or total + len(value) > MAX_MEDIA_BYTES:
            self.pending.pop(asset, None)
            reject("Picture registration exceeds its file or one-MiB total media limit.")
        if final:
            self.pending.pop(asset, None)
            metadata = inspect_image(value)
            self.assets[asset] = (session, bytes(value), metadata)
            return {"session": session, "asset": asset, **metadata}
        self.pending[asset] = (session, value)
        return {"accepted": len(value)}

    def resolve(self, plan):
        from app.mcp.office_contracts import WordImage
        result, total = {}, 0
        for block in plan.blocks:
            if not isinstance(block, WordImage):
                continue
            record = self.assets.get(block.asset)
            if record is None or record[0] != plan.session:
                reject("Register the picture in this Word session before composition.")
            data, metadata = record[1:]
            # Compilation embeds each placement. Bound all placed bytes, even
            # when several pictures refer to the same immutable source asset.
            total += len(data)
            height = block.width_mm * metadata["height_px"] / metadata["width_px"]
            if height > plan.layout.height_mm - plan.layout.margins_mm[0] - plan.layout.margins_mm[2]:
                reject("Picture height exceeds the usable page body.")
            result[block.asset] = (data, metadata)
        if total > MAX_MEDIA_BYTES:
            reject("Pictures exceed the one-MiB total media limit.")
        return result


def validate_package(root):
    """Allow only ordinary embedded inline PNG/JPEG pictures, before any write."""
    parts = {p.attrib.get(PKG + "name"): p for p in root.findall(PKG + "part")}
    media, total = {}, 0
    for name, part in parts.items():
        binary = part.find(PKG + "binaryData")
        if binary is None:
            continue
        if not name.startswith("/word/media/"):
            reject("Unsupported binary Word dependency.")
        encoded = "".join((binary.text or "").split())
        if len(encoded) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
            reject("Picture dependency exceeds the 256-KiB limit.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError:
            reject("Picture dependency is invalid.")
        metadata = inspect_image(data)
        expected_type = "image/png" if metadata["format"] == "PNG" else "image/jpeg"
        if part.attrib.get(PKG + "contentType") != expected_type:
            reject("Picture dependency content type does not match its decoded format.")
        total += len(data)
        media[name] = (data, metadata)
    if len(media) > MAX_IMAGES or total > MAX_MEDIA_BYTES:
        reject("Word media exceeds eight pictures or one MiB.")
    drawings = root.findall(".//" + W + "drawing")
    if len(drawings) > MAX_IMAGES:
        reject("Word supports at most eight inline pictures.")
    import posixpath
    for name, part in parts.items():
        if not name.endswith(".rels"):
            continue
        for relation in part.iter(REL + "Relationship"):
            if relation.attrib.get("TargetMode") == "External":
                reject("Word documents with external relationships are unsupported.")
    document = parts.get("/word/document.xml")
    rels = parts.get("/word/_rels/document.xml.rels")
    mapping = {} if rels is None else {r.attrib.get("Id"): r for r in rels.iter(REL + "Relationship")}
    supported = []
    for drawing in drawings:
        if document is None or drawing not in list(document.iter()):
            reject("Pictures in running matter are unsupported.")
        inline = drawing.find(WP + "inline")
        pictures = drawing.findall(".//" + PIC + "pic")
        blips = drawing.findall(".//" + A + "blip")
        if inline is None or len(pictures) != 1 or len(blips) != 1 or len(drawing) != 1:
            reject("Only native inline pictures are supported; floating drawings are unsupported.")
        relation = mapping.get(blips[0].attrib.get(R + "embed"))
        if relation is None or not relation.attrib.get("Type", "").endswith("/image") or R + "link" in blips[0].attrib:
            reject("Picture relationship is unsupported.")
        target = posixpath.normpath(posixpath.join("/word", relation.attrib.get("Target", "")))
        if target not in media:
            reject("Picture media is unavailable.")
        # Crop, rotation, effects, linked SVG and extension payloads are outside
        # this initial subset. Refuse instead of flattening or discarding them.
        allowed = {W + "drawing", WP + "inline", WP + "extent", WP + "effectExtent", WP + "docPr",
            WP + "cNvGraphicFramePr", A + "graphicFrameLocks", A + "graphic", A + "graphicData",
            PIC + "pic", PIC + "nvPicPr", PIC + "cNvPr", PIC + "cNvPicPr", A + "picLocks",
            PIC + "blipFill", A + "blip", A + "stretch", A + "fillRect", PIC + "spPr",
            A + "xfrm", A + "off", A + "ext", A + "prstGeom", A + "avLst", A + "noFill",
            A + "ln", A + "extLst", A14 + "useLocalDpi"}
        for extension in drawing.iter(A + "ext"):
            if "uri" in extension.attrib and (extension.attrib["uri"] != "{28A0092B-C50C-407E-A947-70E740481C1C}"
                    or len(extension) != 1 or extension[0].tag != A14 + "useLocalDpi"
                    or extension[0].attrib.get("val") not in {"0", "1"}):
                reject("Picture extensions are unsupported.")
        if any(n.tag not in allowed or n.attrib.get("rot", "0") != "0"
               or n.attrib.get("flipH", "0") not in {"0", "false"}
               or n.attrib.get("flipV", "0") not in {"0", "false"} for n in drawing.iter()):
            reject("Picture effects, crop, rotation or extensions are unsupported.")
        extent = inline.find(WP + "extent")
        if extent is None or any(not 0 < int(extent.attrib.get(k, 0)) <= 420 * 36000 for k in ("cx", "cy")):
            reject("Picture geometry exceeds its bound.")
        supported.append({**media[target][1], "width_mm": int(extent.attrib["cx"]) / 36000,
            "height_mm": int(extent.attrib["cy"]) / 36000, "digest": sha256(media[target][0]).hexdigest()})
    if root.find(".//" + W + "pict") is not None or root.find(".//" + W + "object") is not None:
        reject("Legacy drawings and embedded objects are unsupported.")
    return supported
