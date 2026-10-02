"""Text-only Markdown presentation; original response text remains copyable."""
from PySide6.QtGui import QFont, QFontDatabase, QImage, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument
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
        emphasis = []
        block = self.document.begin()
        while block.isValid():
            block_format = block.blockFormat()
            block_format.setLineHeight(128, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            if block_format.headingLevel():
                block_format.setTopMargin(12)
                block_format.setBottomMargin(8)
            elif block.textList() is not None:
                block_format.setTopMargin(2)
                block_format.setBottomMargin(4)
            else:
                block_format.setTopMargin(8)
                block_format.setBottomMargin(8)
            QTextCursor(block).setBlockFormat(block_format)
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().fontWeight() >= QFont.Weight.Bold:
                    emphasis.append((fragment.position(), fragment.length()))
                if fragment.isValid() and fragment.charFormat().isImageFormat():
                    images.append((fragment.position(), fragment.length()))
                elif fragment.isValid() and fragment.charFormat().fontFamilies() == ["monospace"]:
                    inline_code.append((fragment.position(), fragment.length()))
                iterator += 1
            block = block.next()
        emphasis_format = QTextCharFormat()
        emphasis_format.setFontWeight(QFont.Weight.Medium)
        for position, length in emphasis:
            cursor = QTextCursor(self.document)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(emphasis_format)
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
