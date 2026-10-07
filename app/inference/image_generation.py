"""Native image requests and bounded final-image decoding."""
from __future__ import annotations

import base64
import binascii
import re

from app.inference.attachments import AttachmentError
from app.inference.completion import CompletionText, IncompleteResponseError

_CREATE = re.compile(r"\b(?:generate|create|make|design|render)\b.{0,100}\b(?:image|picture|photo|illustration|artwork|logo|poster|thumbnail|wallpaper)\b|\b(?:draw|paint|sketch|illustrate)\b", re.I | re.S)
_EDIT = re.compile(r"\b(?:edit|change|replace|remove|add|make|darken|brighten|crop|resize|turn)\b", re.I)
_EXPLAIN = re.compile(r"\b(?:how\s+(?:do|can|to)|explain|describe|analy[sz]e|what\s+(?:is|are|does))\b", re.I)


def image_request(text, *, has_image=False):
    if text.lstrip().startswith("/image "):
        return True
    if _EXPLAIN.search(text):
        return False
    return bool(_CREATE.search(text) or has_image and _EDIT.search(text))


def image_result(payload, *, store, settings, completion, cancellation=None):
    if completion.incomplete:
        raise IncompleteResponseError("Image generation did not finish. You can retry the request.", completion)
    output = payload.get("output")
    if not isinstance(output, list):
        raise AttachmentError("The image service returned an invalid result.")
    calls = [item for item in output if item.get("type") == "image_generation_call"]
    if not calls:
        raise AttachmentError("No image was returned. Check image model access and retry the request.")
    if len(calls) > 8:
        raise AttachmentError("The image service returned too many results.")
    decoded, identities = [], set()
    for item in calls:
        identity, encoded = item.get("id"), item.get("result")
        if not isinstance(identity, str) or identity in identities or item.get("status") != "completed":
            raise AttachmentError("The image service returned incomplete or duplicate results.")
        identities.add(identity)
        if not isinstance(encoded, str) or not encoded or len(encoded) > 32 * 1024 * 1024:
            raise AttachmentError("The generated image exceeds the safe storage limit.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise AttachmentError("The image service returned invalid image data.") from None
        fmt = item.get("output_format") or settings.output_format
        valid = (fmt == "png" and data.startswith(b"\x89PNG\r\n\x1a\n")
                 or fmt == "jpeg" and data.startswith(b"\xff\xd8\xff")
                 or fmt == "webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP")
        if not valid:
            raise AttachmentError("The image service returned an unsupported image format.")
        decoded.append((data, "jpg" if fmt == "jpeg" else fmt))
    if sum(len(data) for data, _ in decoded) > 32 * 1024 * 1024:
        raise AttachmentError("The generated images exceed the safe storage limit.")
    references = []
    from app.conversation.attachment_processing import AttachmentProcessor
    for index, (data, extension) in enumerate(decoded, 1):
        ref = store.import_bytes(data, name=f"Generated image {index}.{extension}", cancellation=cancellation)
        AttachmentProcessor(store).prepare(ref, cancellation=cancellation)
        references.append(ref)
    return CompletionText("Image generated." if len(references) == 1 else "Images generated.", completion,
                          generated_images=tuple(references))
