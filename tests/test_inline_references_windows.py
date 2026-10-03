"""Exercise the Windows Qt importer, which resolves inline code to Courier New."""
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Native Windows Qt font resolution")
def test_windows_inline_font_is_normalized_and_rounded_text_remains_selectable():
    script = r'''
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtWidgets import QApplication
from app.ui.markdown import MarkdownLabel

app = QApplication([])
raw = QTextDocument()
raw.setMarkdown("`main`")
assert raw.begin().begin().fragment().charFormat().fontFixedPitch()
label = MarkdownLabel("1. `orsi_node_2.png`  \n2. `.png`\n\nUse `main`.")
label.setFont(QFont("Segoe UI", 12))
label.refresh_formatting()
label.resize(300, label.heightForWidth(300) + 8)
label.ensurePolished()
app.processEvents()
assert len(label._inline_spans) == 3
for position, length in label._inline_spans:
    block = label.document.findBlock(position)
    iterator = block.begin()
    while not iterator.atEnd():
        fragment = iterator.fragment()
        if fragment.isValid() and fragment.position() == position:
            assert fragment.charFormat().fontFamilies() == label.font().families()
            assert not fragment.charFormat().fontFixedPitch()
        iterator += 1
assert len(label._inline_backgrounds()) == 3
assert all(rect.width() > 6 and rect.height() > 4 for rect in label._inline_backgrounds())
label.selectAll()
assert label.selectedText() == label.plain_text()
assert "orsi_node_2.png" in label.selectedText()
assert label.isReadOnly()
label.close()

# Native Windows list layout must keep hanging indents, numbering and task markers.
from PySide6.QtGui import QTextCursor, QTextListFormat
bullets = MarkdownLabel("- **First:** a sentence that wraps at a narrow width.\n    - Nested `main`\n\n1. Numbered\n\n- [x] Done")
bullets.setFont(QFont("Segoe UI", 12))
bullets.refresh_formatting()
bullets.resize(180, bullets.heightForWidth(180) + 8)
bullets.ensurePolished()
app.processEvents()
markers = bullets._bullet_markers()
assert len(markers) == 2
assert all(3 <= rect.width() <= 6 for rect, style in markers)
assert markers[1][0].left() > markers[0][0].left()
first = bullets.document.begin()
assert first.layout().lineCount() > 1
assert first.textList().format().style() == QTextListFormat.Style.ListDisc
assert bullets.cursorRect(QTextCursor(first)).left() - markers[0][0].right() >= 7
assert "1. " in bullets.document.toMarkdown()
bullets.selectAll()
assert bullets.selectedText() == bullets.plain_text()
assert len(bullets._bullet_markers()) == 2
bullets.close()
'''
    result = subprocess.run([sys.executable, "-c", script],
        env={**os.environ, "QT_QPA_PLATFORM": "windows"}, capture_output=True, text=True,
        timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
