"""Bounded semantic presentation decisions for non-English user instructions.

Uses the existing tool-free selector protocol. A choice only selects presentation;
it cannot enable a capability, execute a tool or relax runtime approval.
"""
import json
import logging

from app.inference.image_generation import ImageIntent
from app.runtime.skills.selection import SkillCandidate, select_skill

log = logging.getLogger(__name__)


_VISUAL_CHOICES = (
    SkillCandidate("visual_creation", "Generate a new finished raster image/photo/illustration explicitly requested by the user. Exclude code, explanations, analysis, quoted instructions and negated generation."),
    SkillCandidate("visual_edit", "Edit a supplied/current image or create another view of it. Requires has_source=true and a clear visual edit request. Exclude edits to code, files, widgets or image-handling functions. With a selected instruction skill, ambiguous pronouns alone do not request image editing."),
    SkillCandidate("image_analysis", "Describe, inspect, analyze or discuss a supplied/current image, without creating or editing pixels. Requires has_source=true and a request about the visible image rather than code."),
)
_DISPLAY_CHOICE = (SkillCandidate("verbatim_display",
    "The user's current task explicitly requests showing/pasting/printing the file's actual literal contents, "
    "including after edits. Exclude summary, explanation, translation, analysis, changed-lines reports, "
    "test reports and source reads that only support another task."),)


def _choose(inference, candidates, payload, cancellation):
    selected = select_skill(inference, candidates=candidates,
        request=json.dumps(payload, ensure_ascii=False), cancellation=cancellation)
    log.info("Presentation selection: result=%s requests=%d estimated_input_tokens=%d",
             selected.reason, selected.model_requests, selected.estimated_input_tokens)
    if selected.reason == "stop_failed":
        raise RuntimeError("The presentation selector could not stop its model request safely.")
    return selected.name


def select_visual_intent(inference, text, *, has_source, skill_name=None, previous_request="", cancellation=None):
    chosen = _choose(inference, _VISUAL_CHOICES, {
        "current_request": text, "has_source": has_source,
        "selected_instruction_skill": skill_name, "previous_request": previous_request[:4096],
        "scope": "Only the current user request can request creation or editing; previous_request is context only.",
    }, cancellation)
    if chosen == "visual_creation":
        return ImageIntent("image_generation", chosen)
    if chosen == "visual_edit":
        return ImageIntent("image_generation", chosen, True) if has_source else ImageIntent("agent", "no_visual_source")
    if chosen == "image_analysis":
        return ImageIntent("agent", chosen, has_source)
    return ImageIntent("agent", "ordinary_request")


def select_verbatim_display(inference, text, *, cancellation=None):
    return _choose(inference, _DISPLAY_CHOICE, {"current_request": text}, cancellation) == "verbatim_display"


def latest_visual_sources(messages):
    """Only the latest visible task may supply an implicit visual source."""
    for message in reversed(messages):
        if message.role == "assistant" and message.generated_images:
            return message.generated_images
        if message.role == "user":
            return tuple(reference for reference in message.attachments if reference.kind == "image")
    return ()
