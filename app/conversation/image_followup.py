"""Resolve visual follow-ups to the latest retained result."""
import re

_VISUAL = re.compile(r"\b(?:image|picture|photo|background|foreground|lighting|colou?r|darker|brighter|hat|shirt|style|cropped|portrait|landscape|version)\b", re.I)
_REFERENCE = re.compile(r"\b(?:it|this|that|them|these|those)\b", re.I)
_FOLLOWUP_ACTION = re.compile(r"\b(?:edit|change|replace|remove|add|make|darken|brighten|crop|resize|turn|adjust|give|put|transform|describe|analy[sz]e|show|what)\b", re.I)


def visual_followup(text):
    return bool(_FOLLOWUP_ACTION.search(text) and (_VISUAL.search(text) or _REFERENCE.search(text)))


def latest_generated_sources(messages):
    for message in reversed(messages):
        if message.role == "assistant" and message.generated_images:
            return message.generated_images
    return ()
