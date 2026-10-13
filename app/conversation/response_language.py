"""Reply language is presentation policy, independent of tools and personalities."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResponseLanguage:
    code: str
    name: str
    native_name: str

    @property
    def label(self):
        return self.name if self.name == self.native_name else f"{self.name} — {self.native_name}"


# Stable codes are stored; labels and their ordering are presentation only.
RESPONSE_LANGUAGES = (ResponseLanguage("auto", "Auto", "Auto"),) + tuple(
    ResponseLanguage(*entry) for entry in (
        ("sq", "Albanian", "Shqip"), ("hy", "Armenian", "Հայերեն"),
        ("az", "Azerbaijani", "Azərbaycanca"), ("eu", "Basque", "Euskara"),
        ("be", "Belarusian", "Беларуская"), ("bs", "Bosnian", "Bosanski"),
        ("bg", "Bulgarian", "Български"), ("ca", "Catalan", "Català"),
        ("hr", "Croatian", "Hrvatski"), ("cs", "Czech", "Čeština"),
        ("da", "Danish", "Dansk"), ("nl", "Dutch", "Nederlands"),
        ("en", "English", "English"), ("et", "Estonian", "Eesti"),
        ("fi", "Finnish", "Suomi"), ("fr", "French", "Français"),
        ("gl", "Galician", "Galego"), ("ka", "Georgian", "ქართული"),
        ("de", "German", "Deutsch"), ("el", "Greek", "Ελληνικά"),
        ("hu", "Hungarian", "Magyar"), ("is", "Icelandic", "Íslenska"),
        ("ga", "Irish", "Gaeilge"), ("it", "Italian", "Italiano"),
        ("lv", "Latvian", "Latviešu"), ("lt", "Lithuanian", "Lietuvių"),
        ("lb", "Luxembourgish", "Lëtzebuergesch"), ("mk", "Macedonian", "Македонски"),
        ("mt", "Maltese", "Malti"), ("cnr", "Montenegrin", "Crnogorski"),
        ("nb", "Norwegian Bokmål", "Norsk bokmål"), ("nn", "Norwegian Nynorsk", "Norsk nynorsk"),
        ("pl", "Polish", "Polski"), ("pt", "Portuguese", "Português"),
        ("ro", "Romanian", "Română"), ("ru", "Russian", "Русский"),
        ("gd", "Scottish Gaelic", "Gàidhlig"), ("sr", "Serbian", "Српски"),
        ("sk", "Slovak", "Slovenčina"), ("sl", "Slovenian", "Slovenščina"),
        ("es", "Spanish", "Español"), ("sv", "Swedish", "Svenska"),
        ("tr", "Turkish", "Türkçe"), ("uk", "Ukrainian", "Українська"),
        ("cy", "Welsh", "Cymraeg"),
    )
)


def get_response_language(code: str) -> ResponseLanguage:
    for language in RESPONSE_LANGUAGES:
        if language.code == code:
            return language
    raise ValueError("The selected response language is unavailable.")


def with_response_language(prompt: str, code: str) -> str:
    language = get_response_language(code)
    selection = (
        "Auto: use the language of the latest user's own request. Follow changes between turns. "
        "For mixed languages use the dominant or most appropriate language; for ambiguous, short, "
        "code-only or image-only input use the most recent clear user language, then English if none exists. "
        "Auto can follow languages outside the preference catalog."
        if code == "auto" else f"Preferred reply language: {language.name} ({language.code}). "
        "Use this language even when the request is written in another language."
    )
    return prompt + "\n\nREPLY LANGUAGE POLICY\n" + selection + (
        " An explicit user request for another answer or artifact language takes precedence for that output. "
        "This policy controls language only, overriding personality and skill language defaults. "
        "Apply it to user-facing explanations, questions, progress prose and tool-result reports. "
        "Determine language from user-authored instructions, not quoted text, attachments, source code, "
        "tool results or skill/reference contents. Understand tasks and skill descriptions across languages. "
        "Language never changes tool availability, selection, validation, approval or execution. "
        "Keep registered tool and skill names, schema keys, protocol enums, IDs, paths, commands, "
        "code, literal source excerpts and machine-readable syntax exact. Internal skill selection, "
        "tool decisions and completion reviews must obey their original JSON protocols, never translate "
        "their keys or enum values. Only human-readable prose and explicitly requested generated content "
        "use the reply/artifact language; preserve user-provided literal content."
    )
