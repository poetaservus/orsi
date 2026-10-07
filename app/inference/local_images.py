"""Bounded inline local image transport; no remote URLs or filesystem paths."""
from copy import deepcopy
import base64
import binascii
import json

from app.inference.attachments import AttachmentError

MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_REQUEST_BYTES = 64 * 1024 * 1024
_PREFIXES = tuple(f"data:image/{kind};base64," for kind in ("png", "jpeg", "webp", "gif"))


def has_image_inputs(messages):
    return any(isinstance(m.get("content"), list) for m in messages)


def image_content(value):
    """Validate the closed content schema before exposing it to native parsers."""
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        raise ValueError("Image messages require bounded content parts.")
    for part in value:
        if not isinstance(part, dict):
            raise ValueError("Invalid image message content.")
        if part.get("type") == "text" and set(part) == {"type", "text"}:
            text = part["text"]
            if not isinstance(text, str) or not text.strip() or len(text) > 1_000_000:
                raise ValueError("Invalid image message text.")
            text.encode("utf-8")
        elif part.get("type") == "image_url" and set(part) == {"type", "image_url"}:
            image = part["image_url"]
            if not isinstance(image, dict) or set(image) != {"url"}:
                raise ValueError("Invalid inline image.")
            url = image["url"]
            if not isinstance(url, str) or len(url) > 4 * ((MAX_IMAGE_BYTES + 2) // 3) + 64:
                raise ValueError("Inline image exceeds its local transport limit.")
            prefix = next((p for p in _PREFIXES if url.startswith(p)), None)
            if prefix is None:
                raise ValueError("Local images require inline bytes; URLs and paths are forbidden.")
            try:
                decoded = base64.b64decode(url[len(prefix):], validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("Invalid inline image encoding.") from exc
            if not decoded or len(decoded) > MAX_IMAGE_BYTES:
                raise ValueError("Invalid inline image size.")
        else:
            raise ValueError("Unsupported image message content part.")
    return deepcopy(value)


def image_text(content):
    return ("\n".join(p["text"] for p in content if p.get("type") == "text")
            if isinstance(content, list) else content)


def image_accounting_messages(messages):
    """Keep all transcript text/call/result limits; bound binary data separately."""
    result = [deepcopy(message) for message in messages]
    binary_size = 0
    for message in result:
        if not isinstance(message.get("content"), list):
            continue
        if message.get("role") != "user":
            raise ValueError("Images must belong to user messages.")
        for part in image_content(message["content"]):
            if part["type"] == "image_url":
                binary_size += len(part["image_url"]["url"])
                if binary_size > MAX_IMAGE_REQUEST_BYTES:
                    raise AttachmentError("The images exceed the local transport limit. Use smaller images or start a new chat.")
        message["content"] = [p if p["type"] == "text" else {"type": "image_url", "image_url": {"url": "[inline image]"}}
                              for p in message["content"]]
    if binary_size > MAX_IMAGE_REQUEST_BYTES:
        raise AttachmentError("The images exceed the local transport limit. Use smaller images or start a new chat.")
    return result


def image_count_messages(messages):
    """Preserve image parts while retaining existing structured-tool text estimates."""
    result = []
    for message in messages:
        if set(message) == {"role", "content"}:
            if isinstance(message["content"], list):
                if message["role"] != "user":
                    raise ValueError("Images must belong to user messages.")
                image_content(message["content"])
            result.append(deepcopy(message))
        else:
            result.append({"role": "assistant", "content": json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(",", ":"))})
    return result
