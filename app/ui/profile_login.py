"""Profile setup and login, separate from the settings navigation."""
from app.ui.localization import ui_text, QFrame, QLabel, QScrollArea, QWidget

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (QGraphicsBlurEffect, QVBoxLayout)

from app.vault.types import ProfileNotFound, RecoveryRequired
from app.ui.theme_runtime import apply_theme_style, apply_theme_tree, theme_color


_LOGIN_PAGE_STYLE = """
QWidget#personalProfilePage QLabel#loginProfileSummary {
    background: transparent; border: none; padding: 0; color: #b9c2d0; font-size: 16px;
}
QWidget#personalProfilePage QLabel#loginFieldLabel { color: #e4e5eb; font-size: 16px; }
QWidget#personalProfilePage QLabel#loginOptionsHeading { color: #a2afc1; font-size: 16px; }
QWidget#personalProfilePage QLineEdit { font-size: 18px; border-radius: 8px; padding: 8px 10px; }
QWidget#personalProfilePage QLineEdit:focus { border-color: #505050; outline: none; }
QWidget#personalProfilePage QPushButton { font-size: 16px; padding: 6px 14px; }
QWidget#personalProfilePage QPushButton:focus { border-color: #505050; outline: none; }
QWidget#personalProfilePage QLabel#profileFeedback {
    background: #252d41; border: 1px solid #505050; border-radius: 6px;
    padding: 10px 12px; color: #f0c5bb; font-size: 16px;
}
QWidget#personalProfilePage QPushButton#loginPrimary {
    background: #3b5675; border-color: #686868; color: #f4f6fb; font-size: 18px; font-weight: 500;
}
QWidget#personalProfilePage QPushButton#loginPrimary:hover { background: #46658a; }
QWidget#personalProfilePage QPushButton#loginPrimary:pressed { background: #304761; }
QWidget#personalProfilePage QPushButton#loginPrimary:focus { border-color: #686868; outline: none; }
QWidget#personalProfilePage QPushButton#loginMore,
QWidget#personalProfilePage QPushButton#loginMore:hover,
QWidget#personalProfilePage QPushButton#loginMore:pressed,
QWidget#personalProfilePage QPushButton#loginMore:checked {
    background: transparent; border: none; padding: 2px 0;
    color: #b9c2d0; font-size: 18px; font-weight: 400; text-decoration: underline;
}
QWidget#personalProfilePage QPushButton#loginMore:focus { color: #e4e5eb; }
"""


class ProfileLoginPanel(QFrame):
    def __init__(self, page, parent):
        super().__init__(parent)
        self.setObjectName("profileLoginPanel")
        self.setAccessibleName(ui_text('Profile login'))
        self.page = page
        if page.compact_login:
            self._center_login_controls(page)
        font = self.font()
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
        self.setFont(font)
        page._theme_focus_border_role = "border"
        apply_theme_style(page, page._theme_style_source + _LOGIN_PAGE_STYLE)
        # Login is a sibling of the application root, so only its backdrop blurs.
        self.backdrop_blur = QGraphicsBlurEffect(parent._root)
        self.backdrop_blur.setBlurRadius(12)
        self.backdrop_blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        parent._root.setGraphicsEffect(self.backdrop_blur)
        apply_theme_style(self, """
            QFrame#profileLoginPanel { background: transparent; border: none; }
            QFrame#profileLoginPanel QWidget { font-family: Saira; color: #e4e5eb; font-size: 16px; }
            QFrame#profileLoginPanel QLabel { background: transparent; font-size: 16px; }
            QFrame#profileLoginPanel QLabel#loginHeading { font-size: 30px; font-weight: 500; }
            QFrame#profileLoginPanel QLabel#loginSubtitle { color: #b9c2d0; font-size: 16px; }
            QWidget#loginContent { background: transparent; }
            QFrame#profileLoginPanel QScrollArea,
            QFrame#profileLoginPanel QScrollArea > QWidget > QWidget { background: transparent; border: none; }
            QFrame#profileLoginPanel QScrollBar:vertical { width: 5px; background: transparent; }
            QFrame#profileLoginPanel QScrollBar::handle:vertical { background: #657385; border-radius: 2px; min-height: 28px; }
            QFrame#profileLoginPanel QScrollBar::add-line:vertical,
            QFrame#profileLoginPanel QScrollBar::sub-line:vertical { height: 0; }
            QFrame#profileLoginPanel QScrollBar::add-page:vertical,
            QFrame#profileLoginPanel QScrollBar::sub-page:vertical { background: transparent; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("loginContent")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(28)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        header = QVBoxLayout()
        header.setSpacing(8)
        heading = QLabel(ui_text('Create your profile') if page.setup_required else
                         ui_text('Finish profile deletion') if page.manager.deletion_pending else
                         ui_text('Profile deleted') if page.manager.profile_deleted else
                         ui_text('Profile not found') if isinstance(page.location_error, ProfileNotFound) else
                         ui_text('Profile needs recovery') if isinstance(page.location_error, RecoveryRequired) else
                         ui_text('Profile unavailable') if page.location_error is not None else
                         ui_text('Unlock your profile') if page.manager.encrypted else ui_text('Open your personal profile'))
        heading.setObjectName("loginHeading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setWordWrap(True)
        header.addWidget(heading)
        subtitle = QLabel(ui_text('Set up your personal profile to get started.') if page.setup_required else
                          ui_text('Some profile locations still need to be removed.') if page.manager.deletion_pending else
                          ui_text('Create or select a profile, or continue without a profile.') if page.manager.profile_deleted else
                          ui_text('Choose how to continue, or reconnect its drive and check again.') if page.location_error is not None else
                          ui_text('Enter your password or recovery key to continue.') if page.manager.encrypted else
                          ui_text('Open your profile to continue.') if page.manager.locator is not None else
                          ui_text('Select a profile to continue.'))
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setObjectName("loginSubtitle")
        if not page.compact_login:
            header.addWidget(subtitle)
        else:
            subtitle.deleteLater()
        body.addLayout(header)
        body.addWidget(page)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll)
        apply_theme_tree(self)
        page.login_layout_changed.connect(self.fit_to_parent)
        parent.theme_controller.changed.connect(self.fit_to_parent)
        self.fit_to_parent()

    @staticmethod
    def _center_login_controls(page):
        # Change only the locked login instance; the shared profile workspace
        # retains its own layouts, spacing and typography.
        root = QWidget.layout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        for caption in page.findChildren(QLabel, "loginFieldLabel"):
            if caption.buddy() is page.password:
                root.removeWidget(caption)
                caption.hide()
                caption.deleteLater()
        def center(layout):
            for index in range(layout.count()):
                item = layout.itemAt(index)
                if item.widget() in (page.unlock_button, page.more_button):
                    layout.setAlignment(item.widget(), Qt.AlignmentFlag.AlignHCenter)
                elif item.layout() is not None:
                    center(item.layout())
        center(root)
        page.password.setFixedHeight(52)
        page.unlock_button.setFixedHeight(48)

    def fit_to_parent(self):
        parent = self.parentWidget()
        self.scroll.widget().ensurePolished()
        # Recompute the page before its container: More/Less changes its hint.
        page_layout = QWidget.layout(self.page)
        page_layout.invalidate()
        page_layout.activate()
        self.page.updateGeometry()
        self.scroll.widget().layout().activate()
        minimum = 300 if self.page.compact_login else 280
        preferred_height = max(minimum, self.scroll.widget().sizeHint().height() + 56)
        self.resize(min(480, parent.width() - 32), min(preferred_height, parent.height() - 72))
        self.move((parent.width() - self.width()) // 2, max(44, (parent.height() - self.height()) // 2))

    def focus_password(self):
        field = getattr(self.page, "password", None)
        if field is not None:
            field.setFocus()
            self.scroll.ensureWidgetVisible(field)
        elif hasattr(self.page, "create_profile"):
            self.page.create_profile.setFocus()
            self.scroll.ensureWidgetVisible(self.page.create_profile)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(self.rect().bottomLeft(), self.rect().topRight())
        gradient.setColorAt(0, theme_color(self, "#090c15", "settings_bottom"))
        gradient.setColorAt(1, theme_color(self, "#1d2637", "settings_top"))
        painter.setBrush(gradient)
        painter.setPen(QPen(theme_color(self, "#505050", "border"), 1.0))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
