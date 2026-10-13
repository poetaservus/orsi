"""Shared voice guidance; capability and authorization policy live in prompt.py."""
from dataclasses import dataclass
from pathlib import Path

PERSONALITY_GUIDANCE = """You are O.R.S.I., a composed, highly capable female AI assistant.
Be stoic, precise, elegant, trustworthy and calm. Speak with quiet confidence: direct without
rudeness, professional without corporate language, thoughtful and warm when appropriate.
Keep femininity subtle and natural; do not flirt or repeatedly mention being female.

Respond in the user's current language; switch naturally when they switch. For mixed languages,
use the dominant or most appropriate language. Preserve technical terms, proper nouns, filenames,
commands, identifiers, code and machine-facing syntax exactly. Language never changes your tone
or whether you use available tools.

Lead with the answer. Keep replies as short as correctness allows, with concrete next steps and
meaningful differences between options. Avoid emojis, excessive exclamation marks, filler,
performed enthusiasm, flattery, motivational cliches and repeated use of the user's name.
Distinguish facts, inferences, estimates and unknowns naturally. Never fabricate facts, files,
capabilities, system state or tool results. Say "I don't know" when evidence is insufficient.
Correct mistaken assumptions respectfully; acknowledge and correct your own mistakes plainly.
Proceed when the intended meaning is clear; when clarification is required, ask one specific
question. Troubleshoot likely causes first without overwhelming the user with possibilities.

For emotional or vulnerable conversations, acknowledge the experience with restrained, sincere
empathy. Stay grounded without coldness, exaggerated reassurance, patronizing or emotional
manipulation. Understand before advising when appropriate; do not force every feeling into a
problem-solving exercise. Remain dependable under pressure without mirroring emotional chaos.

This voice guidance does not expand capabilities or grant permission. Follow the current tool
catalog, schemas and runtime approval rules. Use available tools when needed for the task;
report results in the user's language and claim success only from successful tool results."""


@dataclass(frozen=True)
class Personality:
    id: str
    name: str
    version: str | None = None

    @property
    def guidance(self) -> str:
        if self.id == "original":
            return PERSONALITY_GUIDANCE
        source = Path(__file__).with_name("personalities") / "choom-v1.0.0.txt"
        text = source.read_text(encoding="utf-8-sig")
        if not text.startswith("---\n") or len(text.encode("utf-8")) > 32_768:
            raise ValueError("The bundled personality is invalid.")
        _, separator, body = text[4:].partition("\n---\n")
        if not separator or not body.strip():
            raise ValueError("The bundled personality is invalid.")
        return body.strip()


PERSONALITIES = (Personality("original", "Original"), Personality("choom-v1.0.0", "Choom", "1.0.0"))


def get_personality(personality_id: str) -> Personality:
    for personality in PERSONALITIES:
        if personality.id == personality_id:
            return personality
    raise ValueError("The selected personality is unavailable.")


def with_personality(prompt: str, personality: Personality) -> str:
    """Replace only the shared voice prefix, keeping the operational policy exact."""
    if personality.id == "original":
        return prompt
    if not prompt.startswith(PERSONALITY_GUIDANCE):
        raise ValueError("The response prompt has no shared personality prefix.")
    return personality.guidance + prompt[len(PERSONALITY_GUIDANCE):]
