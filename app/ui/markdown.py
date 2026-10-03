"""Selectable Markdown text with rounded backgrounds for inline references."""
from math import ceil

from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextListFormat
from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import QFrame, QTextEdit


_INLINE_REFERENCE = QTextFormat.Property.UserProperty.value + 1
_CUSTOM_BULLET = QTextFormat.Property.UserProperty.value + 2
_BULLET_STYLES = (
    QTextListFormat.Style.ListDisc,
    QTextListFormat.Style.ListCircle,
    QTextListFormat.Style.ListSquare,
)


class _TextDocument(QTextDocument):
    def loadResource(self, resource_type, url):  # noqa: N802 - Qt API name
        # Rendering a reply must never fetch a file or network image.
        return QImage()


class MarkdownLabel(QTextEdit):
    def __init__(self, source: str):
        super().__init__()
        self._source = str(source)
        self._rendered_font = None
        self._inline_spans = []
        self.document = _TextDocument(self)
        self.document.setDocumentMargin(3)
        self.setDocument(self.document)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setAcceptRichText(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursorWidth(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.refresh_formatting()

    def text(self) -> str:
        return self._source

    def setWordWrap(self, enabled: bool) -> None:  # noqa: N802
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth if enabled else QTextEdit.LineWrapMode.NoWrap)

    def setSelection(self, start: int, length: int) -> None:  # noqa: N802
        cursor = QTextCursor(self.document)
        limit = self.document.characterCount() - 1
        cursor.setPosition(min(max(0, start), limit))
        cursor.setPosition(min(max(0, start + length), limit), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def selectedText(self) -> str:  # noqa: N802
        return self.textCursor().selectedText().replace("\u2029", "\n")

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        self.document.setTextWidth(max(1, width))
        return ceil(self.document.size().height())

    def wheelEvent(self, event) -> None:  # noqa: N802
        # Only the outer conversation scrolls; inline text has no nested scroll area.
        event.ignore()

    def refresh_formatting(self) -> None:
        font = self.font()
        if self._rendered_font == font:
            return
        self.document.setDefaultFont(font)
        self.document.setMarkdown(self._source,
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub
            | QTextDocument.MarkdownFeature.MarkdownNoHTML)
        # Image and HTML responses cannot load local or remote resources.
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
                style = block.textList().format().style()
                if style in _BULLET_STYLES and block_format.marker() == QTextBlockFormat.MarkerType.NoMarker:
                    # Suppress only the native marker; retain the actual list and its indentation.
                    # A per-block override also leaves numbered and task-list markers intact.
                    block_format.setProperty(QTextFormat.Property.ListStyle,
                        QTextListFormat.Style.ListStyleUndefined.value)
                    block_format.setProperty(_CUSTOM_BULLET, style.value)
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
                elif fragment.isValid() and fragment.charFormat().fontFixedPitch():
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
        code_format.setFontFamilies(font.families())
        code_format.setFontFixedPitch(font.fixedPitch())
        code_format.setProperty(_INLINE_REFERENCE, True)
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
        # Replacing image objects changes positions; read the surviving text formats.
        self._inline_spans = []
        block = self.document.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().boolProperty(_INLINE_REFERENCE):
                    self._inline_spans.append((fragment.position(), fragment.length()))
                iterator += 1
            block = block.next()
        self._rendered_font = font
        self.viewport().update()

    def plain_text(self) -> str:
        return self.document.toPlainText()

    def _inline_backgrounds(self) -> list[QRectF]:
        """Follow the actual laid-out text across lines, including UTF-16 positions."""
        rectangles = []
        for position, length in self._inline_spans:
            block = self.document.findBlock(position)
            layout = block.layout()
            start, end = position - block.position(), position + length - block.position()
            for index in range(layout.lineCount()):
                line = layout.lineAt(index)
                first = max(start, line.textStart())
                last = min(end, line.textStart() + line.textLength())
                if last <= first:
                    continue
                cursor = QTextCursor(self.document)
                cursor.setPosition(block.position() + first)
                origin = self.cursorRect(cursor)
                metrics = QFontMetricsF(cursor.charFormat().font().resolve(self.document.defaultFont()))
                left, right = line.cursorToX(first), line.cursorToX(last)
                left = left[0] if isinstance(left, tuple) else left
                right = right[0] if isinstance(right, tuple) else right
                delta = right - left
                baseline = origin.top() + metrics.ascent()
                rectangles.append(QRectF(origin.left() + min(0, delta) - 3,
                    baseline - metrics.capHeight() - 2, abs(delta) + 6,
                    metrics.capHeight() + metrics.descent() + 4))
        return rectangles

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#303030"))
        for rectangle in self._inline_backgrounds():
            painter.drawRoundedRect(rectangle, 4, 4)
        for rectangle, style in self._bullet_markers():
            color = self.palette().color(self.foregroundRole())
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            if style == QTextListFormat.Style.ListCircle:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(color, 1))
            if style == QTextListFormat.Style.ListSquare:
                painter.drawRect(rectangle)
            else:
                painter.drawEllipse(rectangle)
        painter.end()
        super().paintEvent(event)

    def _bullet_markers(self) -> list[tuple[QRectF, QTextListFormat.Style]]:
        """Place one small marker beside the first line, including wrapped and RTL items."""
        markers = []
        block = self.document.begin()
        while block.isValid():
            block_format = block.blockFormat()
            layout = block.layout()
            if block_format.hasProperty(_CUSTOM_BULLET) and layout.lineCount():
                cursor = QTextCursor(block)
                origin = self.cursorRect(cursor)
                metrics = QFontMetricsF(cursor.charFormat().font().resolve(self.document.defaultFont()))
                size = max(3.5, metrics.capHeight() * 0.34)
                gap = max(7, metrics.horizontalAdvance(" ") * 1.75)
                baseline = origin.top() + layout.lineAt(0).ascent()
                left = (origin.right() + gap if block.textDirection() == Qt.LayoutDirection.RightToLeft
                    else origin.left() - gap - size)
                rectangle = QRectF(left, baseline - metrics.capHeight() / 2 - size / 2, size, size)
                markers.append((rectangle, QTextListFormat.Style(block_format.intProperty(_CUSTOM_BULLET))))
            block = block.next()
        return markers
