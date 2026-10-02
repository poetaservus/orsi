"""Text-only Markdown presentation; original response text remains copyable."""
from PySide6.QtGui import QFontDatabase, QImage, QTextCharFormat, QTextCursor, QTextDocument
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class _TextDocument(QTextDocument):
    def loadResource(self, resource_type, url):  # noqa: N802 - Qt API name
        # Rendering a reply must never fetch a file or network image.
        return QImage()


class MarkdownLabel(QLabel):
    def __init__(self, source: str):
        super().__init__()
        self._source = str(source)
        self._rendered_font = None
        self.document = _TextDocument(self)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.refresh_formatting()

    def text(self) -> str:
        return self._source

    def refresh_formatting(self) -> None:
        font = self.font()
        if self._rendered_font == font:
            return
        self.document.setDefaultFont(font)
        self.document.setMarkdown(self._source,
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub
            | QTextDocument.MarkdownFeature.MarkdownNoHTML)
        # Remove image objects before passing the document to QLabel's renderer.
        images = []
        inline_code = []
        block = self.document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    images.append((fragment.position(), fragment.length()))
                elif fragment.isValid() and fragment.charFormat().fontFamilies() == ["monospace"]:
                    inline_code.append((fragment.position(), fragment.length()))
                iterator += 1
            block = block.next()
        code_format = QTextCharFormat()
        code_format.setFontFamilies([QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()])
        for position, length in inline_code:
            cursor = QTextCursor(self.document)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(code_format)
        for position, length in reversed(images):
            cursor = QTextCursor(self.document)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText("[Image]", QTextCharFormat())
        super().setText(self.document.toHtml())
        self._rendered_font = font

    def plain_text(self) -> str:
        return self.document.toPlainText()
