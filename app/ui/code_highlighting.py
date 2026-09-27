from __future__ import annotations

from pygments.lexers import get_lexer_by_name
from pygments.lexers.special import TextLexer
from pygments.styles import get_style_by_name
from pygments.token import Comment
from pygments.util import ClassNotFound
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


_SYNTAX_STYLE = get_style_by_name("github-dark")


def _token_format(token) -> QTextCharFormat:
    # Use the theme's full token hierarchy, including language-specific subtypes,
    # instead of collapsing every keyword/name/string to a custom category color.
    values = _SYNTAX_STYLE.style_for_token(token)
    style = QTextCharFormat()
    color = values["color"]
    if token in Comment:
        # GitHub's comment gray assumes an almost black background. Lift only
        # this low-contrast color for the lighter glass surface.
        color = "b4becd"
    if color:
        style.setForeground(QColor(f"#{color}"))
    style.setFontWeight(QFont.Weight.Bold if values["bold"] else QFont.Weight.Normal)
    style.setFontItalic(values["italic"])
    style.setFontUnderline(values["underline"])
    return style


class CodeHighlighter(QSyntaxHighlighter):
    """Highlight a read-only code document without changing its source text.

    Tokenize the complete snippet once so multiline strings/comments keep their
    state. Qt indexes UTF-16 code units, while Pygments indexes Python characters.
    """

    def __init__(self, document, language: str):
        super().__init__(document)
        self._lines: dict[int, list[tuple[int, int, QTextCharFormat]]] = {}
        try:
            lexer = get_lexer_by_name(language.strip().split()[0].lower())
        except (ClassNotFound, IndexError):
            return
        if isinstance(lexer, TextLexer):
            return
        formats = {}

        # QPlainTextEdit normalizes paragraph separators on insertion. Highlight
        # its document text; the Copy action retains the original source text.
        text = document.toPlainText()
        line, column = 0, 0
        for _, token, value in lexer.get_tokens_unprocessed(text):
            if token not in formats:
                formats[token] = _token_format(token)
            style = formats[token]
            fragments = value.split("\n")
            for index, fragment in enumerate(fragments):
                length = len(fragment.encode("utf-16-le")) // 2
                if length:
                    self._lines.setdefault(line, []).append((column, length, style))
                column += length
                if index < len(fragments) - 1:
                    line += 1
                    column = 0
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API name
        for start, length, style in self._lines.get(self.currentBlock().blockNumber(), ()):
            self.setFormat(start, length, style)
