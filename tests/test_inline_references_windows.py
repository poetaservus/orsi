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
'''
    result = subprocess.run([sys.executable, "-c", script],
        env={**os.environ, "QT_QPA_PLATFORM": "windows"}, capture_output=True, text=True,
        timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, result.stderr
