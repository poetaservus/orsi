"""Native image requests and bounded final-image decoding."""
from __future__ import annotations

import base64
import binascii
import re

from app.inference.attachments import AttachmentError
from app.inference.completion import CompletionText, IncompleteResponseError

_CREATE_VERBS = r"(?:generate|genereate|create|make|design|render)"
_CREATE = re.compile(rf"\b{_CREATE_VERBS}\b", re.I)
_DRAW = re.compile(r"\b(?:draw|paint|sketch|illustrate)\b", re.I)
_VISUAL_OUTPUT = re.compile(
    r"\b(?:images?|pictures?|photos?|photographs?|illustrations?|artworks?|logos?|posters?|"
    r"thumbnails?|wallpapers?|portraits?|landscapes?|drawings?|paintings?|sketches?|"
    r"icons?|avatars?|sprites?|textures?|diagrams?|infographics?|storyboards?|"
    r"concept[ -]+art|character[ -]+designs?|(?:character|model|sprite|turnaround)[ -]+(?:reference[ -]+)?sheets?)\b",
    re.I,
)
_REFERENCE_SHEET = re.compile(r"\breference[ -]+sheets?\b", re.I)
_VISUAL_REFERENCE = re.compile(r"\b(?:character|model(?:l?ing)?|sprite|turnaround|costume|pose|anatomy|manga|art|design)\b", re.I)
_TEXT_OUTPUT_WORDS = r"(?:lists?|scripts?|code|programs?|functions?|reports?|documents?|tables?|spreadsheets?|files?|instructions|prompts?|descriptions?|explanations?|captions?|summar(?:y|ies))"
_TEXT_OUTPUT = re.compile(rf"\b{_TEXT_OUTPUT_WORDS}\b", re.I)
_WRITE_TASK = re.compile(rf"\b(?:write|draft|compose)\b[^.!?\n]*\b{_TEXT_OUTPUT_WORDS}\b", re.I)
_EDIT = re.compile(r"\b(?:edit|change|replace|remove|add|make|darken|brighten|crop|resize|turn|adjust|give|put|transform)\b", re.I)
_EXPLAIN = re.compile(r"\b(?:how\s+(?:do|can|to)|explain|describe|analy[sz]e|what\s+(?:is|are|does))\b", re.I)
_TEXT_REQUEST = re.compile(rf"\b{_CREATE_VERBS}\s+(?:(?:me|a|an|the|some|python|javascript)\s+)*(?:list|script|code|program|function|report|document|table|instructions|prompt)\b", re.I)
_IMAGE_REFERENCE = re.compile(r"\b(?:it|this|that|them|these|those)\b", re.I)
_VISUAL_SUBJECT = re.compile(r"\b(?:character|subject|image|picture|photo|photograph|portrait|background|version|view|again)\b", re.I)
_VIEW_CHANGE = re.compile(r"\b(?:(?:side|back|front|rear|three-quarter)[ -]+views?|sideways?|sideway|sideview|backview|(?:another|different)[ -]+angle)\b", re.I)


def creation_followup(text):
    """A new view/version of a retained image, rather than an unrelated creation."""
    creation = _CREATE.search(text)
    if creation is None:
        return False
    clause = re.split(r"[.!?\n]", text[creation.end():], maxsplit=1)[0]
    if _TEXT_OUTPUT.search(clause) or _EXPLAIN.search(text):
        return False
    return bool(_VIEW_CHANGE.search(clause) or
                _IMAGE_REFERENCE.search(clause) and _VISUAL_SUBJECT.search(clause))


def image_request(text, *, has_image=False):
    if text.lstrip().startswith("/image "):
        return True
    if _EXPLAIN.search(text) or _TEXT_REQUEST.search(text):
        return False
    creation = _CREATE.search(text)
    writing = _WRITE_TASK.search(text)
    if writing is not None and (creation is None or writing.start() < creation.start()):
        return False
    if creation is not None:
        # Read the requested output in its clause, without an adjective-count cutoff.
        clause = re.split(r"[.!?\n]", text[creation.end():], maxsplit=1)[0]
        visual = _VISUAL_OUTPUT.search(clause)
        reference = _REFERENCE_SHEET.search(clause)
        if reference is not None and _VISUAL_REFERENCE.search(clause):
            if visual is None or reference.start() < visual.start():
                visual = reference
        written = _TEXT_OUTPUT.search(clause)
        # A report containing pictures stays a report; an image depicting text stays an image.
        if written is not None and (visual is None or written.start() < visual.start()):
            return False
        if visual is not None:
            return True
    return bool(_DRAW.search(text) or has_image and (_EDIT.search(text) or creation_followup(text)))


def image_result(payload, *, store, settings, completion, cancellation=None):
    if completion.incomplete:
        raise IncompleteResponseError("Image generation did not finish. You can retry the request.", completion)
    output = payload.get("output")
    if not isinstance(output, list) or any(not isinstance(item, dict) or
            item.get("type") not in {"image_generation_call", "message", "reasoning"} for item in output):
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
    try:
        for index, (data, extension) in enumerate(decoded, 1):
            ref = store.import_bytes(data, name=f"Generated image {index}.{extension}", cancellation=cancellation, draft=True)
            references.append(ref)
            AttachmentProcessor(store).prepare(ref, cancellation=cancellation)
    except Exception:
        for reference in references:
            store.discard_draft(reference)
        raise
    return CompletionText("Image generated." if len(references) == 1 else "Images generated.", completion,
                          generated_images=tuple(references))
