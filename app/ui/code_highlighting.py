from __future__ import annotations

from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Name, Number, Operator, Punctuation, String
from pygments.util import ClassNotFound
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat


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
        colors = (
            (Comment, "#bdc7d7"),
            (String, "#f2d99c"),
            (Number, "#ffbdaa"),
            (Name.Tag, "#aee3c3"),
            (Name.Attribute, "#9de6f5"),
            (Name.Function, "#b1d5ff"),
            (Name.Class, "#aee3c3"),
            (Name.Builtin, "#9de6f5"),
            (Keyword, "#9de6f5" if lexer.name == "CSS" else "#dbc4ff"),
            (Operator, "#dbc4ff"),
            (Punctuation, "#d6dfee"),
        )
        formats = []
        for token, color in colors:
            style = QTextCharFormat()
            style.setForeground(QColor(color))
            style.setFontItalic(token == Comment)
            formats.append((token, style))

        # QPlainTextEdit normalizes paragraph separators on insertion. Highlight
        # its document text; the Copy action retains the original source text.
        text = document.toPlainText()
        line, column = 0, 0
        for _, token, value in lexer.get_tokens_unprocessed(text):
            style = next((style for kind, style in formats if token in kind), None)
            fragments = value.split("\n")
            for index, fragment in enumerate(fragments):
                length = len(fragment.encode("utf-16-le")) // 2
                if length and style is not None:
                    self._lines.setdefault(line, []).append((column, length, style))
                column += length
                if index < len(fragments) - 1:
                    line += 1
                    column = 0
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt API name
        for start, length, style in self._lines.get(self.currentBlock().blockNumber(), ()):
            self.setFormat(start, length, style)
