"""Spacious cards and responsive rows for the five ordinary Settings modules."""
from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QFont, QPainter, QPalette
from PySide6.QtWidgets import QBoxLayout, QHBoxLayout, QSizePolicy, QStyle, QStyleOptionButton, QVBoxLayout

from app.ui.localization import QComboBox, QFrame, QLabel, QPushButton, QWidget
from app.ui.settings_style import settings_control_style
from app.ui.theme_runtime import apply_theme_style


class SettingsButton(QPushButton):
    """Content-sized actions that can wrap long captions in narrow cards."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        policy = QSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def minimumSizeHint(self):  # noqa: N802
        return QSize(0, self.fontMetrics().height() + 18)

    def heightForWidth(self, width):  # noqa: N802
        bounds = self.fontMetrics().boundingRect(QRect(0, 0, max(1, width - 24), 1000),
            int(Qt.TextFlag.TextWordWrap), self.text())
        return max(38, bounds.height() + 18)

    def _fit_caption(self):
        height = self.heightForWidth(self.width())
        if self.minimumHeight() != height:
            self.setFixedHeight(height)
            self.updateGeometry()

    def resizeEvent(self, event):  # noqa: N802
        self._fit_caption()
        super().resizeEvent(event)

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange, QEvent.Type.LanguageChange):
            self._fit_caption()

    def paintEvent(self, event):  # noqa: N802
        if self.fontMetrics().horizontalAdvance(self.text()) <= self.width() - 24:
            super().paintEvent(event)
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ""
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)
        bounds = self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, self)
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        painter.setPen(option.palette.color(group, QPalette.ColorRole.ButtonText))
        painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.text())


class SettingsPage(QWidget):
    settings_font_step = 4

    def __init__(self):
        super().__init__()
        self.setObjectName("settingsPage")
        font = self.font()
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
        self.setFont(font)
        self.outer = QHBoxLayout(self)
        self.outer.setContentsMargins(28, 28, 28, 28)
        self.body = QWidget(self)
        self.body.setObjectName("settingsBody")
        self.body.setMaximumWidth(1040)
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(0)
        self.outer.addStretch()
        self.outer.addWidget(self.body, 1)
        self.outer.addStretch()
        apply_theme_style(self, _STYLE)

    def resizeEvent(self, event):  # noqa: N802
        margin = 12 if self.width() < 700 else 28
        self.outer.setContentsMargins(margin, 28, margin, 28)
        super().resizeEvent(event)


def settings_group(layout, title=None):
    if title:
        heading = QLabel(title)
        heading.setObjectName("settingsGroupTitle")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        layout.addSpacing(12)
    card = QFrame()
    card.setObjectName("settingsGroup")
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
    content = QVBoxLayout(card)
    content.setContentsMargins(22, 8, 22, 8)
    content.setSpacing(0)
    layout.addWidget(card)
    layout.addSpacing(32)
    return content


class SettingRow(QFrame):
    def __init__(self, title, hint, control, *, indent=0, separator=True, control_size=(280, 44)):
        super().__init__()
        self.setObjectName("settingRow" if separator else "settingRowPlain")
        self.control, self.control_size = control, control_size
        self.box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.box.setContentsMargins(indent, 20, 0, 20)
        self.box.setSpacing(24)
        self.labels = QWidget(self)
        labels = QVBoxLayout(self.labels)
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(5)
        self.title = title if isinstance(title, QLabel) else QLabel(title)
        self.title.setObjectName("settingName")
        self.title.setWordWrap(True)
        self.title.setBuddy(control)
        labels.addWidget(self.title)
        if hint:
            self.description = QLabel(hint)
            self.description.setObjectName("settingsDescription")
            self.description.setWordWrap(True)
            labels.addWidget(self.description)
        if not control.accessibleDescription():
            control.setAccessibleDescription(hint)
        if not control.toolTip():
            control.setToolTip(hint)
        control.setFixedSize(*control_size)
        control.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if isinstance(control, QComboBox):
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setMinimumContentsLength(1)
        self.box.addWidget(self.labels, 1)
        self.box.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        policy = self.sizePolicy()
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def minimumSizeHint(self):  # noqa: N802
        return QSize(0, 0)

    def heightForWidth(self, width):  # noqa: N802
        margins = self.box.contentsMargins()
        available = max(0, width - margins.left() - margins.right())
        stacked = self.control_size[0] > 72 and available < 620
        label_width = available if stacked else max(1, available - self.control_size[0] - 24)
        label_height = max(self.labels.sizeHint().height(), self.labels.layout().heightForWidth(label_width))
        return (label_height + self.control_size[1] + 14 if stacked else max(label_height, self.control_size[1])) + 40

    def resizeEvent(self, event):  # noqa: N802
        available = max(0, self.width() - self.box.contentsMargins().left())
        stacked = self.control_size[0] > 72 and available < 620
        self.box.setDirection(QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight)
        self.box.setSpacing(14 if stacked else 24)
        self.box.setStretch(0, 0 if stacked else 1)
        self.control.setFixedWidth(available if stacked else self.control_size[0])
        self.box.setAlignment(self.control, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.updateGeometry()
        super().resizeEvent(event)


def settings_row(layout, title, hint, control, **options):
    row = SettingRow(title, hint, control, **options)
    layout.addWidget(row)
    return row


_STYLE = settings_control_style("QWidget#settingsPage") + """
QWidget#settingsPage, QWidget#settingsBody { background: transparent; border: none; }
QWidget#settingsPage QWidget { font-family: Saira; font-size: 14px; color: #e4e5eb; }
QWidget#settingsPage QLabel { background: transparent; border: none; }
QWidget#settingsPage QLabel#settingsSectionTitle { font-size: 26px; font-weight: 500; }
QWidget#settingsPage QLabel#settingsGroupTitle { font-size: 14px; font-weight: 600; }
QWidget#settingsPage QLabel#settingName { font-size: 14px; font-weight: 500; }
QWidget#settingsPage QLabel#settingsDescription { font-size: 12px; color: #b9c2d0; }
QWidget#settingsPage QFrame#settingsGroup { background: #202224; border: 1px solid #35393f; border-radius: 16px; }
QWidget#settingsPage QFrame#settingRow { background: transparent; border: none; border-bottom: 1px solid #35393f; border-radius: 0; }
QWidget#settingsPage QFrame#settingRowPlain { background: transparent; border: none; }
QWidget#settingsPage QListWidget#installedSkills { background: transparent; border: none; padding: 0; }
QWidget#settingsPage QListWidget#installedSkills::item { padding: 14px 10px; border: none; border-bottom: 1px solid #35393f; border-radius: 0; }
QWidget#settingsPage QListWidget#installedSkills::item:selected { background: #3b5675; border-radius: 8px; }
"""
