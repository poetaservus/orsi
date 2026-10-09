"""Native image requests and bounded final-image decoding."""
from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass

from app.inference.attachments import AttachmentError
from app.inference.completion import CompletionText, IncompleteResponseError

_CREATE_VERBS = r"(?:generate|genereate|create|make|design|render)"
_CREATE = re.compile(rf"\b{_CREATE_VERBS}\b", re.I)
_DRAW = re.compile(r"\b(?:draw|paint|sketch|illustrate)\b", re.I)
_VISUAL_OUTPUT = re.compile(
    r"\b(?:images?|pictures?|photos?|photographs?|illustrations?|artworks?|logos?|posters?|"
    r"thumbnails?|wallpapers?|portraits?|landscapes?|drawings?|paintings?|sketch(?:es)?|"
    r"icons?|avatars?|sprites?|textures?|diagrams?|infographics?|storyboards?|"
    r"concept[ -]+art|character[ -]+designs?|(?:character|model|sprite|turnaround)[ -]+(?:reference[ -]+)?sheets?)\b",
    re.I,
)
_REFERENCE_SHEET = re.compile(r"\breference[ -]+sheets?\b", re.I)
_VISUAL_REFERENCE = re.compile(r"\b(?:character|model(?:l?ing)?|sprite|turnaround|costume|pose|anatomy|manga|art|design)\b", re.I)
_TEXT_OUTPUT_WORDS = r"(?:lists?|scripts?|code|programs?|functions?|reports?|documents?|tables?|spreadsheets?|files?|instructions|prompts?|descriptions?|explanations?|captions?|summar(?:y|ies))"
_TEXT_OUTPUT = re.compile(rf"\b{_TEXT_OUTPUT_WORDS}\b", re.I)
_EDIT = re.compile(r"\b(?:edit|change|replace|remove|add|make|darken|brighten|crop|resize|turn|adjust|give|put|transform)\b", re.I)
_IMAGE_REFERENCE = re.compile(r"\b(?:it|this|that|them|these|those)\b", re.I)
_VISUAL_SUBJECT = re.compile(r"\b(?:character|subject|image|picture|photo|photograph|portrait|background|view)\b", re.I)
_VIEW_CHANGE = re.compile(r"\b(?:(?:side|back|front|rear|three-quarter)[ -]+views?|sideways?|sideway|sideview|backview|(?:another|different)[ -]+angle)\b", re.I)
_IMAGE_NOUN_WORDS = r"(?:image|picture|photo|photograph|illustration|portrait|drawing|painting|screenshot)"
_IMAGE_NOUN = re.compile(rf"\b{_IMAGE_NOUN_WORDS}\b", re.I)
_VISUAL_EDIT_TARGET = re.compile(r"\b(?:background|foreground|lighting|colou?r|darker|brighter|hat|shirt|style|cropped|red|green|blue|black|white|transparent|larger|smaller|sharper)\b", re.I)
_NAMED_EDIT_TARGET = re.compile(r"\b(?:background|foreground|lighting|hat|shirt)\b", re.I)
_INHERENT_VISUAL_EDITS = {"crop", "resize", "darken", "brighten"}
_CODE_TARGET = re.compile(r"\b(?:code|source|script|program|function|traceback|exception|error|crash\w*|debug\w*|tkinter|sliders?|buttons?|files?)\b|\b[\w-]+\.(?:py|js|ts|tsx|jsx|cpp|cs|java)\b", re.I)
_SOURCE_TARGET = re.compile(r"\b(?:code|source|script|program|function|tkinter)\b|\b[\w-]+\.(?:py|js|ts|tsx|jsx|cpp|cs|java)\b", re.I)
_VISUAL_CODE = re.compile(r"\b(?:image|picture|photo|drawing)[ -]+(?:(?:processing|loading|generation|rendering|editing|display|viewer|preview|handling)[ -]+)*(?:code|script|program|function|class|widget|button|file)\b", re.I)
_DIRECT_IMAGE_TARGET = re.compile(rf"^(?:(?:the|this|that|attached|selected|supplied|my|an?)\s+)*{_IMAGE_NOUN_WORDS}(?:\s+(?:to|by|so|and|into|with|without|it)\b|[.,]|$)", re.I)
_REQUEST_PREFIX = (r"(?:(?:please|now|also|then|and|instead)\s+|(?:can|could|would|will)\s+you\s+|"
                   r"i\s+(?:want|need|would\s+like)\s+(?:you\s+to\s+|to\s+)?)*")
_ANALYSIS = re.compile(rf"^{_REQUEST_PREFIX}(?:how\s+(?:do|can|to)|explain|describe|analy[sz]e|what|inspect|review|compare|show)\b", re.I)
_ACTION = re.compile(
    rf"^{_REQUEST_PREFIX}"
    rf"(?P<verb>{_CREATE_VERBS}|draw|paint|sketch|illustrate|edit|change|replace|remove|add|"
    r"darken|brighten|crop|resize|turn|adjust|give|put|transform|write|draft|compose|fix|debug)\b(?=\s|$)", re.I)
_NEGATED_VISUAL = re.compile(
    r"\b(?:(?:do\s+not|don't|dont|never|stop)\s+(?:\w+\s+){0,3}"
    r"(?:generate|create|make|draw|paint|sketch|illustrate|render)|"
    r"(?:did\s+not|didn't|never)\s+ask\s+(?:you\s+)?(?:to\s+)?(?:generate|draw|create|paint|sketch|illustrate)|"
    r"(?:no|without)\s+image\s+generation)\b", re.I)


@dataclass(frozen=True)
class ImageIntent:
    route: str
    reason: str
    followup: bool = False


def request_text(text):
    """Exclude quoted source/diagnostics from intent, without altering model input."""
    text = re.sub(r"```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)", "", text)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = re.sub(r'"[^"\n]*"|(?<!\w)\'[^\'\n]*\'(?!\w)', "", text)
    return "\n".join(line for line in text.splitlines()
        if not re.match(r"\s*>|\s{4,}\S|\s*(?:Traceback|File\s+\"|\w*(?:Error|Exception):)", line))


def _clauses(text):
    return [clause.strip() for clause in re.split(r"[!?;\n]|\.\s+", text) if clause.strip()]


def _negated_visual(text):
    for clause in _clauses(text):
        for match in _NEGATED_VISUAL.finditer(clause):
            verb = match[0].split()[-1].lower()
            if verb in {"draw", "paint", "sketch", "illustrate", "generation"}:
                return True
            output = clause[match.end():]
            visual, written = _VISUAL_OUTPUT.search(output), _TEXT_OUTPUT.search(output)
            if visual is not None and (written is None or visual.start() < written.start()):
                return True
    return False


def creation_followup(text):
    """A new view/version of a retained image, rather than an unrelated creation."""
    text = request_text(text)
    if _negated_visual(text):
        return False
    for clause in _clauses(text):
        action = _ACTION.match(clause)
        if action is None or not _CREATE.fullmatch(action["verb"]):
            continue
        output = clause[action.end():]
        if _TEXT_OUTPUT.search(output):
            continue
        if (_VIEW_CHANGE.search(output) or _IMAGE_REFERENCE.search(output) and
                (_VISUAL_SUBJECT.search(output) or re.search(r"\bagain\b", output, re.I))):
            return True
    return False


def image_intent(text, *, has_image=False, skill_name=None):
    if text.lstrip().startswith("/image "):
        return ImageIntent("image_generation", "explicit_image")
    text = request_text(text)
    if _negated_visual(text):
        return ImageIntent("agent", "negated_visual")
    for clause in _clauses(text):
        analysis = _ANALYSIS.match(clause)
        if analysis is not None:
            output = clause[analysis.end():]
            visual_analysis = bool(_IMAGE_NOUN.search(output) and not _VISUAL_CODE.search(output))
            return ImageIntent("agent", "image_analysis" if visual_analysis else "analysis", visual_analysis)
        action = _ACTION.match(clause)
        if action is None:
            continue
        verb, output = action["verb"].lower(), clause[action.end():]
        visual = _VISUAL_OUTPUT.search(output)
        reference = _REFERENCE_SHEET.search(output)
        if reference is not None and _VISUAL_REFERENCE.search(output):
            if visual is None or reference.start() < visual.start():
                visual = reference
        written = _TEXT_OUTPUT.search(output)
        if verb in {"write", "draft", "compose", "fix", "debug"} or _VISUAL_CODE.search(output) or (
                written is not None and (visual is None or written.start() < visual.start())):
            return ImageIntent("agent", "coding_request" if verb in {"fix", "debug"} or _CODE_TARGET.search(clause) else "written_request")
        if _CREATE.fullmatch(verb) or _DRAW.fullmatch(verb):
            if visual is not None or _DRAW.fullmatch(verb) and not _CODE_TARGET.search(output):
                return ImageIntent("image_generation", "visual_creation", creation_followup(clause))
        if (_SOURCE_TARGET.search(output) and not _DIRECT_IMAGE_TARGET.match(output.strip()) or
                _CODE_TARGET.search(output) and not _IMAGE_NOUN.search(output)):
            return ImageIntent("agent", "coding_request")
        followup = creation_followup(clause)
        visual_edit = bool(verb in _INHERENT_VISUAL_EDITS or _EDIT.fullmatch(verb) and
                           (_IMAGE_NOUN.search(output) or _VISUAL_EDIT_TARGET.search(output)))
        if has_image and (followup or visual_edit):
            # A skill can disambiguate pronouns; it cannot veto a named visual output.
            if skill_name is not None and not (verb in _INHERENT_VISUAL_EDITS or
                    _VISUAL_SUBJECT.search(output) or _IMAGE_NOUN.search(output) or _NAMED_EDIT_TARGET.search(output)):
                return ImageIntent("agent", "selected_skill")
            return ImageIntent("image_generation", "visual_edit", True)
    return ImageIntent("agent", "ordinary_request")


def image_request(text, *, has_image=False):
    return image_intent(text, has_image=has_image).route == "image_generation"


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
