"""Small native widgets for the personal-profile settings workspace."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QBoxLayout, QButtonGroup, QFrame, QLabel, QRadioButton, QTabBar,
                              QLayout, QSizePolicy, QVBoxLayout, QWidget)

from app.vault.credentials import CredentialPolicy


class FeedbackLabel(QLabel):
    def __init__(self, text=""):
        super().__init__()
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setObjectName("profileFeedback")
        self.setText(text)

    def setText(self, text):  # noqa: N802
        super().setText(text)
        if not text:
            self.hide()
        elif self.parentWidget() is not None:
            self.show()


class AdaptiveRow(QWidget):
    """Keep actions content-sized and stack them when a narrow window needs it."""
    def __init__(self, widgets, *, threshold=None, trailing=False):
        super().__init__()
        self.widgets = widgets
        self.threshold, self.trailing = threshold, trailing
        self.box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(12)
        self.box.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        policy = self.sizePolicy()
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        for widget in widgets:
            self.box.addWidget(widget)
        self.box.addStretch(0 if trailing else 1)

    def _required_width(self):
        return self.threshold or sum(w.sizeHint().width() for w in self.widgets) + 12 * (len(self.widgets) - 1)

    def minimumSizeHint(self):  # noqa: N802
        return QSize(max(w.minimumSizeHint().width() for w in self.widgets), 0)

    def heightForWidth(self, width):  # noqa: N802
        heights = [max(w.sizeHint().height(), w.heightForWidth(width)) for w in self.widgets]
        return sum(heights) + 12 * (len(heights) - 1) if width < self._required_width() else max(heights)

    def resizeEvent(self, event):  # noqa: N802
        self.adapt()
        super().resizeEvent(event)

    def adapt(self):
        required = self._required_width()
        stacked = self.width() < required
        self.box.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
        self.box.setStretch(0, 1 if self.trailing and not stacked else 0)
        for widget in self.widgets:
            self.box.setAlignment(widget, Qt.AlignmentFlag.AlignRight if stacked and self.trailing and widget is self.widgets[-1]
                                  else Qt.AlignmentFlag.AlignLeft if widget.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
                                  else Qt.AlignmentFlag(0))
        self.updateGeometry()


class ProfileTabBar(QTabBar):
    def wheelEvent(self, event):  # noqa: N802
        event.ignore()


class ProfileCard(QFrame):
    def __init__(self, title="", description=""):
        super().__init__()
        self.setObjectName("profileCard")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(18, 16, 18, 16)
        self.body.setSpacing(12)
        if title:
            heading = QLabel(title)
            heading.setObjectName("profileCardHeading")
            self.body.addWidget(heading)
        if description:
            text = QLabel(description)
            text.setTextFormat(Qt.TextFormat.PlainText)
            text.setWordWrap(True)
            text.setObjectName("profileHint")
            self.body.addWidget(text)


class CredentialPolicyChoice(QWidget):
    """Radio choices with the same selection API as the former policy combo."""
    currentIndexChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.group = QButtonGroup(self)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        for index, title in enumerate(("Ask whenever Cloud is selected", "Use saved encrypted credentials")):
            choice = QRadioButton(title)
            choice.setAccessibleName(title)
            self.group.addButton(choice, index)
            box.addWidget(choice)
            choice.toggled.connect(lambda checked, i=index: self.currentIndexChanged.emit(i) if checked else None)
        self.setCurrentIndex(0)

    def currentIndex(self):  # noqa: N802
        return self.group.checkedId()

    def setCurrentIndex(self, index):  # noqa: N802
        button = self.group.button(index)
        if button is not None:
            button.setChecked(True)

    def currentData(self):  # noqa: N802
        return CredentialPolicy.SAVED if self.currentIndex() == 1 else CredentialPolicy.ASK
