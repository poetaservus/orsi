"""Offline presentation hints; never translate input or grant tool authority."""
import re
from threading import Lock


_lock = Lock()
_identifier = None


def authored_text(text):
    # Bounded and content-free outside this call. Attachments are never inspected.
    text = str(text)[:16384]
    text = re.sub(r"```[\s\S]*?(?:```|$)|~~~[\s\S]*?(?:~~~|$)", "", text)
    text = re.sub(r'`[^`\n]*`|"[^"\n]*"|(?<!\w)\'[^\'\n]*\'(?!\w)', "", text)
    text = "\n".join(line for line in text.splitlines() if not re.match(r"\s*>|\s{4,}\S", line))
    return re.sub(r"(?:https?://|[A-Za-z]:[\\/])\S+|\b\S+\.(?:py|json|txt|md|js|css|html|cmd)\b", "", text)


def detect_language(text):
    """Return a confident statistical hint, or None for short/ambiguous input."""
    global _identifier
    text = authored_text(text)
    if sum(c.isalpha() for c in text) < 12 or len(re.findall(r"[^\W\d_]+", text)) < 2:
        return None
    with _lock:
        if _identifier is None:
            from langid.langid import LanguageIdentifier, model
            _identifier = LanguageIdentifier.from_modelstring(model, norm_probs=True)
        code, probability = _identifier.classify(text)
    return code if probability >= .85 else None


def reply_locale(code, user_text, history=()):
    if code != "auto":
        return code
    detected = detect_language(user_text)
    if detected:
        return detected
    for message in reversed(history):
        if message.get("role") == "user":
            detected = detect_language(message.get("content", ""))
            if detected:
                return detected
    return "en"
