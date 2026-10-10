"""A dedicated locked-profile surface, separate from the settings navigation."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsBlurEffect, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget
from app.ui.settings_style import CONTROL_SURFACE


class VaultLoginEmblem(QWidget):
    """A small public vault mark; it contains no profile information."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 48)

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(CONTROL_SURFACE))
        painter.setPen(QPen(QColor("#40536d"), 1))
        painter.drawEllipse(QRectF(0.5, 0.5, 47, 47))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#a9cbe5"), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(QRectF(18, 13, 12, 20), 0, 180 * 16)
        painter.drawRoundedRect(QRectF(15, 23, 18, 14), 3, 3)
        painter.drawLine(24, 28, 24, 32)


_LOGIN_PAGE_STYLE = """
QWidget#personalProfilePage QLabel#loginProfileSummary {
    background: #162235; border: 1px solid #35465e; border-radius: 8px;
    padding: 12px; color: #bccbdc; font-size: 12px;
}
QWidget#personalProfilePage QLabel#loginFieldLabel { color: #e4e5eb; font-size: 14px; }
QWidget#personalProfilePage QLabel#loginOptionsHeading { color: #a2afc1; font-size: 12px; }
QWidget#personalProfilePage QLabel#profileFeedback {
    background: #252d41; border: 1px solid #61748f; border-radius: 6px;
    padding: 10px 12px; color: #f0c5bb; font-size: 13px;
}
QWidget#personalProfilePage QPushButton#loginPrimary {
    background: #3b5675; border-color: #6983a2; color: #f4f6fb; font-size: 15px; font-weight: 500;
}
QWidget#personalProfilePage QPushButton#loginPrimary:hover { background: #46658a; }
QWidget#personalProfilePage QPushButton#loginPrimary:pressed { background: #304761; }
QWidget#personalProfilePage QPushButton#loginPrimary:focus { border-color: #91bfe0; }
"""


class ProfileLoginPanel(QFrame):
    def __init__(self, page, parent):
        super().__init__(parent)
        self.setObjectName("profileLoginPanel")
        self.setAccessibleName("Vault login")
        self.page = page
        page.setStyleSheet(page.styleSheet() + _LOGIN_PAGE_STYLE)
        page.layout.setContentsMargins(0, 0, 6, 0)
        # Login is a sibling of the application root, so only its backdrop blurs.
        self.backdrop_blur = QGraphicsBlurEffect(parent._root)
        self.backdrop_blur.setBlurRadius(12)
        self.backdrop_blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        parent._root.setGraphicsEffect(self.backdrop_blur)
        self.setStyleSheet("""
            QFrame#profileLoginPanel { background: transparent; border: none; }
            QFrame#profileLoginPanel QWidget { font-family: Saira; color: #e4e5eb; }
            QFrame#profileLoginPanel QLabel { background: transparent; font-size: 14px; }
            QFrame#profileLoginPanel QLabel#loginBrand { font-size: 17px; font-weight: 500; letter-spacing: 2px; }
            QFrame#profileLoginPanel QLabel#loginHeading { font-size: 30px; font-weight: 500; }
            QFrame#profileLoginPanel QLabel#loginSubtitle { color: #b9c7d9; font-size: 14px; }
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
        layout.setContentsMargins(32, 28, 26, 28)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("loginContent")
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(22)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        header = QVBoxLayout()
        header.setSpacing(8)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addStretch()
        brand.addWidget(VaultLoginEmblem())
        wordmark = QLabel("O.R.S.I")
        wordmark.setObjectName("loginBrand")
        brand.addWidget(wordmark)
        brand.addStretch()
        header.addLayout(brand)
        header.addSpacing(8)
        heading = QLabel("Finish profile deletion" if page.manager.deletion_pending else
                         "Profile deleted" if page.manager.profile_deleted else
                         "Unlock your vault" if page.manager.encrypted else "Open your personal profile")
        heading.setObjectName("loginHeading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setWordWrap(True)
        header.addWidget(heading)
        subtitle = QLabel("Some profile locations still need to be removed." if page.manager.deletion_pending else
                          "Create or select a profile, or continue without a profile." if page.manager.profile_deleted else
                          "Enter your password or recovery key to continue." if page.manager.encrypted else
                          "Open your profile to continue." if page.manager.locator is not None else
                          "Select a profile to continue.")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setObjectName("loginSubtitle")
        header.addWidget(subtitle)
        body.addLayout(header)
        body.addWidget(page)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll)
        self.fit_to_parent()

    def fit_to_parent(self):
        parent = self.parentWidget()
        self.resize(min(600, parent.width() - 32), min(720, parent.height() - 72))
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
        gradient.setColorAt(0, QColor("#090c15"))
        gradient.setColorAt(1, QColor("#1d2637"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#48525f"), 1.0))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
