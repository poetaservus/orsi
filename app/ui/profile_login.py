"""A dedicated locked-profile surface, separate from the settings navigation."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsBlurEffect, QLabel, QScrollArea, QVBoxLayout


class ProfileLoginPanel(QFrame):
    def __init__(self, page, parent):
        super().__init__(parent)
        self.setObjectName("profileLoginPanel")
        self.setAccessibleName("Vault login")
        self.page = page
        # Login is a sibling of the application root, so only its backdrop blurs.
        self.backdrop_blur = QGraphicsBlurEffect(parent._root)
        self.backdrop_blur.setBlurRadius(12)
        self.backdrop_blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        parent._root.setGraphicsEffect(self.backdrop_blur)
        self.setStyleSheet("""
            QFrame#profileLoginPanel { background: transparent; border: none; }
            QFrame#profileLoginPanel QWidget { font-family: Saira; color: #e4e5eb; }
            QFrame#profileLoginPanel QLabel { background: transparent; font-size: 14px; }
            QFrame#profileLoginPanel QLabel#loginHeading { font-size: 34px; font-weight: 400; }
            QFrame#loginDivider { background: rgba(207, 214, 227, 42); }
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
        layout.setContentsMargins(36, 26, 36, 28)
        layout.setSpacing(12)
        heading = QLabel("Finish profile deletion" if page.manager.deletion_pending else
                         "Profile deleted" if page.manager.profile_deleted else
                         "Unlock your vault" if page.manager.encrypted else "Open your personal profile")
        heading.setObjectName("loginHeading")
        layout.addWidget(heading)
        subtitle = QLabel("Some profile locations still need to be removed." if page.manager.deletion_pending else
                          "Create or select a profile, or continue without a profile." if page.manager.profile_deleted else
                          "Enter your password or recovery key to continue." if page.manager.encrypted else
                          "Open your profile to continue." if page.manager.locator is not None else
                          "Select a profile to continue.")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        divider = QFrame()
        divider.setObjectName("loginDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(page)
        layout.addWidget(self.scroll, 1)
        self.fit_to_parent()

    def fit_to_parent(self):
        parent = self.parentWidget()
        self.resize(min(720, parent.width() - 32), min(620, parent.height() - 64))
        self.move((parent.width() - self.width()) // 2, max(44, (parent.height() - self.height()) // 2))

    def focus_password(self):
        field = getattr(self.page, "password", None)
        if field is not None:
            field.setFocus()
            self.scroll.ensureWidgetVisible(field)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(self.rect().bottomLeft(), self.rect().topRight())
        gradient.setColorAt(0, QColor("#383b44"))
        gradient.setColorAt(1, QColor("#3b5066"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#48525f"), 1.0))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
