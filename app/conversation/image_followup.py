"""Resolve source identity within the current visual task, keeping history intact."""
from dataclasses import dataclass
from app.inference.attachments import AttachmentReference, attachment_references
from app.inference.image_generation import image_intent


@dataclass(frozen=True)
class ImageRouteDecision:
    route: str
    reason: str
    references: tuple[AttachmentReference, ...]
    source: str
    skill_name: str | None


def image_route(text, *, attachments=(), messages=(), supported=True, skill_name=None):
    references = attachment_references(attachments)
    if not supported:
        return ImageRouteDecision("agent", "unsupported_backend", references, "submitted", skill_name)
    # Resolve history only after the request itself establishes a visual follow-up.
    intent = image_intent(text, has_image=True, skill_name=skill_name)
    source = "submitted" if references else "none"
    if not references and intent.followup:
        references = latest_generated_sources(messages)
        if references:
            source = "current_visual_task"
    if intent.reason == "visual_edit" and not any(ref.kind == "image" for ref in references):
        return ImageRouteDecision("agent", "no_visual_source", references, source, skill_name)
    return ImageRouteDecision(intent.route, intent.reason, references, source, skill_name)


def visual_followup(text):
    return image_intent(text, has_image=True).followup


def latest_generated_sources(messages):
    for message in reversed(messages):
        if message.role == "assistant" and message.generated_images:
            return message.generated_images
        if message.role == "user":
            intent = image_intent(message.content, has_image=True)
            images = tuple(ref for ref in message.attachments if ref.kind == "image")
            if images and intent.followup:
                return images
            if not intent.followup:
                return ()
    return ()
