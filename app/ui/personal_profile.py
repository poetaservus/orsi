"""Personal profile controls shared by settings and the locked-profile login."""
from pathlib import Path
import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from app.ui.notification_settings import NotificationSwitch
from app.ui.inputs import CompactNumberInput, ScrollSafeComboBox
from app.ui.profile_layout import AdaptiveRow, CredentialPolicyChoice, FeedbackLabel, ProfileCard, ProfileTabBar
from app.ui.settings_motion import SettingsPageTransition
from app.ui.settings_style import settings_control_style
from app.vault.credentials import CredentialPolicy
from app.vault.profiles import public_error
from app.vault.types import BackupPolicy, VaultError


_STYLE = settings_control_style("QWidget#personalProfilePage", "QDialog#personalProfileDialog") + """
QWidget#personalProfilePage { background: transparent; }
QDialog#personalProfileDialog { background: #343f50; color: #e4e5eb; }
QDialog#personalProfileDialog QWidget { color: #e4e5eb; font-family: Saira; font-size: 14px; }
QDialog#personalProfileDialog QLabel, QWidget#personalProfilePage QLabel { background: transparent; }
QWidget#personalProfilePage QWidget { font-family: Saira; color: #e4e5eb; }
QWidget#personalProfilePage QLabel#profileHeading { font-size: 26px; font-weight: 600; }
QWidget#personalProfilePage QLabel#profileName { font-size: 18px; font-weight: 500; }
QWidget#personalProfilePage QLabel#profileFeedback { font-size: 14px; color: #c4e3f6; }
QWidget#personalProfilePage QFrame#profileCard { background: rgba(25, 31, 42, 30); border: 1px solid #526171; border-radius: 7px; }
QWidget#personalProfilePage QLabel#profileCardHeading { font-size: 20px; font-weight: 400; }
QWidget#personalProfilePage QLabel#profileHint { font-size: 14px; color: #b9c2d0; }
QWidget#personalProfilePage QRadioButton, QWidget#personalProfilePage QCheckBox { font-size: 14px; }
QWidget#personalProfilePage QMenu { background: #303946; color: #e4e5eb; border: 1px solid #626772; padding: 5px; }
QWidget#personalProfilePage QMenu::item { padding: 8px 16px; }
QWidget#personalProfilePage QMenu::item:selected { background: #51627a; }
QWidget#personalProfilePage QTabWidget::pane { border: none; background: transparent; }
QWidget#personalProfilePage QTabBar, QWidget#personalProfilePage QTabWidget, QWidget#personalProfilePage QStackedWidget { background: transparent; border: none; }
QWidget#personalProfilePage QTabBar::tab { background: transparent; color: #ccd3de; border: none; border-bottom: 2px solid transparent; padding: 10px 12px; font-size: 14px; }
QWidget#personalProfilePage QTabBar::tab:selected { color: #f4f6fb; border-bottom-color: #65bdea; }
QWidget#personalProfilePage QTabBar::tab:hover { background: rgba(185,197,213,12); }
QWidget#personalProfilePage QScrollArea, QWidget#personalProfilePage QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QWidget#personalProfilePage QScrollBar:vertical { width: 5px; background: transparent; }
QWidget#personalProfilePage QScrollBar::handle:vertical { background: #657385; border-radius: 2px; min-height: 28px; }
QWidget#personalProfilePage QScrollBar::add-line:vertical, QWidget#personalProfilePage QScrollBar::sub-line:vertical { height: 0; }
QWidget#personalProfilePage QScrollBar::add-page:vertical, QWidget#personalProfilePage QScrollBar::sub-page:vertical { background: transparent; }
QWidget#personalProfilePage QLineEdit#profilePath { background: transparent; border: none; color: #bcc7d5; padding: 0; }
"""


def profile_dialog(parent):
    dialog = QDialog(parent)
    dialog.setObjectName("personalProfileDialog")
    dialog.setStyleSheet(_STYLE)
    return dialog


def label(text):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    widget.setObjectName("settingsDescription")
    return widget


def secret(name):
    widget = QLineEdit()
    widget.setEchoMode(QLineEdit.EchoMode.Password)
    widget.setAccessibleName(name)
    widget.setPlaceholderText(name)
    return widget


def combo(options):
    widget = ScrollSafeComboBox()
    for title, value in options:
        widget.addItem(title, value)
    widget.setMinimumContentsLength(12)
    widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    widget.setMinimumWidth(0)
    return widget


def confirm(parent, title, text):
    return QMessageBox.question(parent, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes


class ProfileChoice(QDialog):
    def __init__(self, manager, *, existing=False, parent=None):
        super().__init__(parent)
        self.setObjectName("personalProfileDialog")
        self.setStyleSheet(_STYLE)
        self.setWindowTitle("Select personal profile" if existing else "Set up personal profile")
        self.resize(560, 400)
        layout = QVBoxLayout(self)
        layout.addWidget(label("History, images, imported copies, skills, documentation, your greeting and setup preferences "
            "stay together. Host projects remain outside unless you import a copy."))
        form = QFormLayout()
        self.mode = combo((("Local computer", "local"), ("Portable drive", "portable")))
        self.mode.setAccessibleName("Storage mode")
        self.encryption = QCheckBox("Encrypt personal storage")
        self.encryption.setChecked(True)
        self.location = QLineEdit(str(manager.default_location()))
        self.location.setAccessibleName("Personal profile location")
        browse = QPushButton("Choose location…")
        def choose():
            path = QFileDialog.getExistingDirectory(self, "Select existing profile" if existing else "Choose containing folder")
            if path:
                self.location.setText(path if existing else str(Path(path) / "orsi-profile"))
        browse.clicked.connect(choose)
        location_row = QWidget()
        location_layout = QHBoxLayout(location_row)
        location_layout.setContentsMargins(0, 0, 0, 0)
        location_layout.addWidget(self.location, 1)
        location_layout.addWidget(browse)
        self.mode.currentIndexChanged.connect(lambda: self.location.setText(str(manager.default_location(self.mode.currentData()))))
        self.password, self.repeat = secret("Vault password"), secret("Repeat vault password")
        self.quota = CompactNumberInput()
        self.quota.setRange(1, 1_000_000)
        self.quota.setValue(1)
        self.quota.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quota.setAccessibleName("Vault quota")
        self.policy = combo((("Ask whenever cloud is selected", CredentialPolicy.ASK),
                             ("Allow explicitly saved encrypted credentials", CredentialPolicy.SAVED)))
        self.policy.setAccessibleName("Credential policy")
        form.addRow("Storage", self.mode)
        form.addRow(self.encryption)
        form.addRow("Location", location_row)
        if existing:
            form.addRow("Password", self.password)
        if not existing:
            password_row = QWidget()
            password_layout = QHBoxLayout(password_row)
            password_layout.setContentsMargins(0, 0, 0, 0)
            password_layout.addWidget(self.password)
            password_layout.addWidget(self.repeat)
            form.addRow("Password", password_row)
            quota_row = QWidget()
            quota_layout = QHBoxLayout(quota_row)
            quota_layout.setContentsMargins(0, 0, 0, 0)
            quota_layout.addWidget(self.quota)
            quota_layout.addWidget(label("GiB"))
            quota_layout.addStretch()
            form.addRow("Quota (grows with usage)", quota_row)
            form.addRow("Credentials", self.policy)
        layout.addLayout(form)
        self.storage_info = label("Recommended: encrypted copies are protected while locked. Unencrypted profiles use "
            "session-only credentials. Saving a key always needs separate consent.")
        layout.addWidget(self.storage_info)
        self.error = label("")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        def encryption_changed(enabled):
            for item in (self.password, self.repeat, self.quota):
                item.setEnabled(enabled)
            if not enabled:
                self.password.clear()
                self.repeat.clear()
                self.policy.setCurrentIndex(0)
            self.policy.setEnabled(enabled)
            self.storage_info.setText("Recommended: encrypted copies are protected while locked. Saving a key always needs separate consent."
                if enabled else "This profile stores personal data without encryption. Connection credentials remain session-only.")
        self.encryption.toggled.connect(encryption_changed)
        self.finished.connect(lambda: (self.password.clear(), self.repeat.clear()))
        self.existing, self.selection = existing, None

    def _accept(self):
        if not self.location.text().strip() or (self.encryption.isChecked() and
            (not self.password.text() or not self.existing and self.password.text() != self.repeat.text())):
            self.error.setText("Choose a location and enter matching passwords.")
            return
        self.selection = {"root": Path(self.location.text().strip()), "mode": self.mode.currentData(),
            "encrypted": self.encryption.isChecked(), "password": self.password.text().encode(),
            "quota_bytes": self.quota.value() * 1024**3, "credential_policy": str(self.policy.currentData())}
        self.accept()


class PersonalProfilePage(QWidget):
    transition_requested = Signal(object)
    reload_requested = Signal(object)

    def __init__(self, manager, window, *, message="", login=False):
        super().__init__()
        self.setObjectName("personalProfilePage")
        self.setStyleSheet(_STYLE)
        self.manager, self.window = manager, window
        self.login = login
        self.tabbed = manager.active and not login
        if manager.active:
            unregister = manager.session.register(clear=self._clear_private_controls)
            self.destroyed.connect(unregister)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 6, 0)
        self.layout.setSpacing(10 if login else 12)
        if not login and not self.tabbed:
            heading = label("Personal profile")
            heading.setObjectName("profileHeading")
            self.layout.addWidget(heading)
            self.layout.addWidget(label("Set up a profile to keep your personal storage and preferences together."))
        self.summary = label("")
        self.summary.setAccessibleName("Selected personal profile")
        self.layout.addWidget(self.summary)
        self.status = FeedbackLabel(message)
        self.status.setAccessibleName("Personal profile status")
        if self.tabbed:
            self.layout.removeWidget(self.summary)
            self._workspace(message)
            return
        self.layout.addWidget(self.status)
        if login:
            self.status.setVisible(bool(message))
        else:
            self._buttons((("New profile…", self._new), ("Select existing…", self._select)))
        if manager.locator is not None and not manager.active:
            self.password, self.recovery = secret("Vault password"), secret("Recovery key (optional)")
            if login:
                self.password.setFixedHeight(42)
                self.recovery.setFixedHeight(42)
            self.layout.addWidget(self.password)
            self.layout.addWidget(self.recovery)
            self._buttons((("Unlock vault" if login and manager.encrypted else
                            "Unlock profile" if manager.encrypted else "Open profile", self._unlock),))
            self.password.returnPressed.connect(self._unlock)
            self.recovery.returnPressed.connect(self._unlock)
        if login:
            choices = QHBoxLayout()
            for title, action in (("New profile…", self._new), ("Select existing…", self._select)):
                button = QPushButton(title)
                button.clicked.connect(action)
                choices.addWidget(button)
            self.layout.addLayout(choices)
        self._buttons((("Use current unencrypted storage", self._legacy),))
        self.layout.addStretch()
        self.refresh_summary()
        if message:
            self.status.setText(message)

    def _workspace(self, message):
        outer = self.layout
        heading = label("Personal profile")
        heading.setObjectName("profileHeading")
        outer.addWidget(heading)
        self.subtitle = label("Your vault, access and backups.")
        outer.addWidget(self.subtitle)
        identity = QWidget()
        identity_box = QVBoxLayout(identity)
        identity_box.setContentsMargins(0, 0, 0, 0)
        identity_box.setSpacing(5)
        name = label("Personal vault")
        name.setObjectName("profileName")
        name.setToolTip(str(self.manager.locator.root))
        identity_box.addWidget(name)
        self.summary.deleteLater()
        self.summary = self._location_field()
        self.summary.setAccessibleName("Selected personal profile")
        identity_box.addWidget(self.summary)
        self.manage_profile = self._button("Manage profile", None)
        menu = QMenu(self.manage_profile)
        for title, action in (("New profile…", self._new), ("Select existing…", self._select),
                              ("Use current unencrypted storage", self._legacy)):
            menu.addAction(title, action)
        self.manage_profile.setMenu(menu)
        self.lock_profile = self._button("Lock", lambda: self.transition_requested.emit(self.manager.lock))
        actions = QWidget()
        action_box = QHBoxLayout(actions)
        action_box.setContentsMargins(0, 0, 0, 0)
        action_box.setSpacing(10)
        action_box.addWidget(self.manage_profile)
        action_box.addWidget(self.lock_profile)
        actions.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        summary = ProfileCard()
        self.summary_row = AdaptiveRow([identity, actions], threshold=650, trailing=True)
        summary.body.addWidget(self.summary_row)
        outer.addWidget(summary)
        outer.addWidget(self.status)
        self.tabs = QTabWidget()
        self.tabs.setTabBar(ProfileTabBar())
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setObjectName("profileTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setMinimumSize(0, 0)
        self.tabs.setAccessibleName("Personal profile sections")
        self.sections, self.section_layouts = {}, {}
        for title in ("Storage", "Cloud access", "Backups", "Security", "Data"):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            content = QWidget()
            box = QVBoxLayout(content)
            box.setContentsMargins(0, 16, 6, 0)
            box.setSpacing(14)
            scroll.setWidget(content)
            self.tabs.addTab(scroll, title)
            self.sections[title], self.section_layouts[title] = scroll, box
        self.tab_transition = SettingsPageTransition(self.tabs.findChild(QStackedWidget))
        outer.addWidget(self.tabs, 1)
        self._section("Storage")
        self._card("Vault storage", "Personal storage grows with usage, up to your quota.")
        self.usage = label("")
        self.usage.setAccessibleName("Storage usage")
        self.layout.addWidget(self.usage)
        self._buttons((("Refresh usage", self._refresh_usage),))
        if self.manager.encrypted:
            self._quota_controls()
        self._card("Automatic lock")
        self._idle_controls()
        self._section("Cloud access")
        self._credential_controls()
        self._section("Backups")
        if self.manager.encrypted:
            self._card("Encrypted backups", "Keep an independent copy on another device to protect against disk loss.")
            self._buttons((("Create managed backup", lambda: self._perform(lambda: self.manager.vault().backup(), "Encrypted backup verified.")),
                           ("Backup elsewhere…", self._backup), ("Restore backup…", self._restore)))
            self._card("Managed retention", "Applies only to backups managed by O.R.S.I.")
            self._backup_retention_controls()
        else:
            self._card("Encrypted backups", "Encrypted backup creation and retention require an encrypted profile.")
        self._section("Security")
        if self.manager.encrypted:
            self._card("Vault password", "Changing your password keeps existing vault data. Older backups retain their previous password.")
            self._buttons((("Change password…", self._change_password),))
            self._card("Recovery key", "Keep your recovery key somewhere accessible without this vault or its disk.")
            self._buttons((("Generate recovery key…", self._recovery_key), ("Disable recovery key", self._disable_recovery)))
        else:
            self._card("Profile security", "This profile stores personal data without encryption. Password and recovery controls require an encrypted profile.")
        self._card("Storage location", "Relocation creates and verifies a copy before selecting it. The source remains intact.")
        self.layout.addWidget(self._location_field())
        if self.manager.encrypted:
            self._buttons((("Relocate verified copy…", self._relocate),))
        self._section("Data")
        if self.manager.encrypted:
            self._card("Import copies", "Originals stay outside the vault until you separately choose cleanup.")
            self._migration_controls()
            self._retention_controls()
        else:
            self._card("Personal data", "This profile uses unencrypted personal storage. Protected import, saved-record and cleanup controls require an encrypted profile.")
        for box in self.section_layouts.values():
            box.addStretch()
        self.layout = outer
        self._refresh_usage()
        self.status.setText(message)

    def _section(self, name):
        self._section_box = self.section_layouts[name]

    def _location_field(self):
        path = str(self.manager.locator.root)
        field = QLineEdit(path)
        field.setObjectName("profilePath")
        field.setAccessibleName("Personal profile location")
        field.setReadOnly(True)
        field.setMinimumWidth(0)
        field.setToolTip(path)
        field.setCursorPosition(0)
        return field

    def _card(self, title, description=""):
        card = ProfileCard(title, description)
        self._section_box.addWidget(card)
        self.layout = card.body
        return card

    def show_section(self, name):
        self.tabs.setCurrentIndex(tuple(self.sections).index(name))

    def resizeEvent(self, event):  # noqa: N802
        if self.tabbed and hasattr(self, "summary_row"):
            compact = self.width() < 620
            self.subtitle.setVisible(not compact)
            self.summary.setVisible(not compact)
            self.manage_profile.setText("Profile" if compact else "Manage profile")
            self.summary_row.threshold = None if compact else 650
            self.summary_row.adapt()
        super().resizeEvent(event)

    def _button(self, title, action):
        button = QPushButton(title)
        button.setAccessibleName(title.removesuffix("…"))
        button.setFixedHeight(36)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if action is not None:
            button.clicked.connect(action)
        return button

    def _clear_private_controls(self):
        if self.tabbed:
            self.tab_transition.cancel()
            self.window.settings_panel.page_transition.cancel()
        for widget in self.findChildren(QLineEdit):
            widget.clear()
        for widget in self.findChildren(QTextEdit):
            widget.clear()
        for widget in self.findChildren(QListWidget):
            widget.clear()
        for dialog in self.findChildren(QDialog):
            dialog.reject()

    def _buttons(self, actions):
        if not self.login:
            buttons = [self._button(title, action) for title, action in actions]
            self.layout.addWidget(AdaptiveRow(buttons))
            return buttons
        row = QVBoxLayout()
        buttons = []
        for title, action in actions:
            button = QPushButton(title)
            button.setAccessibleName(title.removesuffix("…"))
            button.clicked.connect(action)
            row.addWidget(button)
            buttons.append(button)
        self.layout.addLayout(row)
        return buttons

    def _form(self):
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.layout.addLayout(form)
        return form

    def refresh_summary(self):
        locator = self.manager.locator
        self.summary.setText("Current unencrypted storage. Set up or select a personal profile here." if locator is None else
            f"{'Local' if locator.mode == 'local' else 'Portable'} · {'Encrypted' if locator.encrypted else 'Unencrypted'} · "
            f"{'Unlocked' if self.manager.active else 'Locked / unavailable'}\n{locator.root}")
        if self.manager.bootstrap_error:
            self.summary.setText("The saved profile selection could not be read. Select an existing profile to continue.")

    def _perform(self, action, success="Saved."):
        try:
            action()
            self.status.setText(success)
            return True
        except Exception as error:
            self.status.setText(public_error(error))
            return False

    def _new(self):
        dialog = ProfileChoice(self.manager, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selection, dialog.selection = dialog.selection, None
            self.transition_requested.emit(lambda: self.manager.create(**selection))

    def _select(self):
        dialog = ProfileChoice(self.manager, existing=True, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selection, dialog.selection = dialog.selection, None
            selection.pop("quota_bytes")
            selection.pop("credential_policy")
            self.transition_requested.emit(lambda: self.manager.select(**selection))

    def _unlock(self):
        password, key = self.password.text().encode(), self.recovery.text().strip()
        self.password.clear()
        self.recovery.clear()
        def unlock():
            self.manager.unlock(password if not key else None, recovery_key=bytes.fromhex(key) if key else None)
        self.transition_requested.emit(unlock)

    def _legacy(self):
        if confirm(self, "Use unencrypted storage", "Open the existing unencrypted personal storage? No data will be copied or merged."):
            self.transition_requested.emit(self.manager.use_legacy)

    def _refresh_usage(self):
        def refresh():
            usage = self.manager.usage()
            def size(value):
                return f"{value / 1024**3:.2f} GiB"
            quota = " / " + size(usage["quota"]) + " quota" if usage["quota"] else ""
            self.usage.setText(f"Application/runtime: {size(usage['application'])}\nModels: {size(usage['models'])}\n"
                f"Personal storage: {size(usage['personal'])}{quota}\nDisk free space: {size(usage['free'])}")
        self._perform(refresh, "Storage usage refreshed.")

    def _idle_controls(self):
        settings = self.manager.settings().load({})
        minutes = settings.get("idle_lock_minutes", 0)
        self.idle_controls = QWidget(self)
        row = QHBoxLayout(self.idle_controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.idle_toggle = NotificationSwitch(self.idle_controls)
        self.idle_toggle.setAccessibleName("Idle lock")
        self.idle_toggle.setAccessibleDescription("Turn automatic idle locking on or off, then save idle lock.")
        self.idle_toggle.setChecked(minutes > 0)
        self.idle = CompactNumberInput(self.idle_controls)
        self.idle.setRange(1, 1440)
        self.idle.setValue(minutes or 5)
        self.idle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.idle.setAccessibleName("Idle lock minutes")
        self.idle.setToolTip("Minutes of inactivity before locking (1–1440)")
        self.idle.setEnabled(self.idle_toggle.isChecked())
        self.idle_toggle.toggled.connect(self.idle.setEnabled)
        self.idle_save = QPushButton("Save idle lock", self.idle_controls)
        self.idle_save.setFixedSize(128, 36)
        self.idle_save.clicked.connect(self._save_idle_lock)
        title = label("Idle lock")
        title.setBuddy(self.idle_toggle)
        for widget in (title, self.idle_toggle, self.idle, label("minutes"), self.idle_save):
            row.addWidget(widget)
        row.addStretch()
        self.layout.addWidget(self.idle_controls)
        if self.manager.encrypted:
            self.guidance = QCheckBox("Show vault storage recommendations")
            self.guidance.setChecked(not settings.get("storage_guidance_dismissed", False))
            self.guidance.toggled.connect(lambda enabled: self._perform(
                lambda: self.manager.configure(storage_guidance_dismissed=not enabled)))
            self.layout.addWidget(self.guidance)

    def _save_idle_lock(self):
        self.idle.interpretText()
        minutes = self.idle.value() if self.idle_toggle.isChecked() else 0
        self._perform(lambda: self.manager.configure(idle_lock_minutes=minutes),
                      "Idle lock saved." if minutes else "Idle lock disabled.")

    def _credential_controls(self):
        self._section_box.addWidget(label("Cloud chat and image generation"))
        if not self.manager.encrypted:
            self._card("Session credentials", "Enter a key when selecting Cloud. It is released on leaving Cloud, closing this profile or exiting. Saved credentials require an encrypted profile.")
            return
        self.provider = getattr(self.window.inference, "credential_provider", None)
        self.connection = getattr(self.window.inference, "connection_id", "cloud-chat")
        if self.provider is None:
            self._card("Cloud connection unavailable", "Configure a cloud connection in Models before saving credentials here.")
            return
        self.credential_status = label("")
        self.credential_status.setAccessibleName("Saved cloud API key status")
        self._section_box.addWidget(self.credential_status)
        self._card("Connection policy", "Choose how O.R.S.I uses your saved key.")
        self.policy = CredentialPolicyChoice()
        policy = self.provider.policy(self.connection) if self.provider else CredentialPolicy.ASK
        self.policy.setCurrentIndex(0 if policy == CredentialPolicy.ASK else 1)
        self.policy.setEnabled(self.manager.encrypted and self.provider is not None)
        self.policy.setAccessibleName("Cloud credential policy")
        self.policy_save = self._button("Apply policy", self._policy)
        self.layout.addWidget(AdaptiveRow([self.policy, self.policy_save], trailing=True))
        self._card("Saved credential")
        self.kind = combo((("API key", "api_key"), ("Login token", "login_token"),
                           ("Access token", "access_token"), ("Refresh token", "refresh_token")))
        self.kind.setAccessibleName("Credential type")
        self.kind.setMaximumWidth(240)
        self.kind.setFixedHeight(36)
        self.key = secret("New connection credential")
        self.key.setPlaceholderText("Paste a replacement key")
        self.key.setFixedHeight(36)
        self.consent = QCheckBox("Save this credential encrypted in this vault")
        self.consent.setEnabled(self.manager.encrypted)
        form = self._form()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setVerticalSpacing(12)
        form.addRow("Credential type", self.kind)
        self.key_caption = label("Replace API key")
        self.key_caption.setBuddy(self.key)
        form.addRow(self.key_caption, self.key)
        self._refresh_credential_status()
        self.credential_save = self._button("Save credential", self._save_key)
        self.credential_delete = self._button("Delete saved key", self._delete_key)
        self.credential_save.setToolTip("Save this value encrypted and apply the selected connection policy.")
        credential_actions = QWidget()
        buttons = QHBoxLayout(credential_actions)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(12)
        buttons.addWidget(self.credential_save)
        buttons.addWidget(self.credential_delete)
        credential_actions.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.layout.addWidget(AdaptiveRow([self.consent, credential_actions], trailing=True))
        self.kind.currentIndexChanged.connect(self._credential_kind_changed)
        self.manager.session.register(clear=lambda: (self.key.clear(), self.consent.setChecked(False)))

    def _credential_kind_changed(self):
        api_key = self.kind.currentData() == "api_key"
        self.key_caption.setText("Replace API key" if api_key else "New token value")
        self.key.setPlaceholderText("Paste a replacement key" if api_key else "Paste a token")
        self.credential_delete.setText("Delete saved key" if api_key else "Delete saved token")

    def _refresh_credential_status(self):
        saved = self.provider.has_saved_api_key(self.connection)
        policy = self.provider.policy(self.connection)
        self.credential_status.setText("No API key is saved for this cloud connection in this profile." if not saved else
            "API key saved encrypted · Automatic use enabled." if policy == CredentialPolicy.SAVED else
            "API key saved encrypted · Ask mode: choose whether to use it when selecting Cloud.")

    def _policy(self):
        if self.provider:
            self._perform(lambda: (self.provider.configure(self.connection, self.policy.currentData()),
                self.manager.configure(credential_policy=str(self.policy.currentData())),
                self._refresh_credential_status()), "Credential policy saved. No new credential was saved.")

    def _save_key(self):
        value = self.key.text()
        self.key.clear()
        consent = self.consent.isChecked()
        self.consent.setChecked(False)
        if self.provider:
            kind, policy = self.kind.currentData(), self.policy.currentData()
            def save():
                # Validate and save first: denied consent/invalid input must not
                # enable use of a previously saved credential.
                self.provider.save(self.connection, value, consent=consent, kind=kind)
                self.provider.configure(self.connection, policy)
                self.manager.configure(credential_policy=str(policy))
                self._refresh_credential_status()
            message = ("Credential saved encrypted. Cloud will still ask because the selected policy is Ask whenever cloud is selected."
                if policy == CredentialPolicy.ASK else "Credential saved encrypted. Cloud will use the saved API key for this connection.")
            if kind != "api_key":
                message = "Token saved encrypted with the selected policy. Cloud chat requires a separately saved API key."
            self._perform(save, message)

    def _delete_key(self):
        if self.provider and confirm(self, "Delete credential", "Delete this saved credential and end its connection session? Older backups may retain it."):
            self._perform(lambda: (self.provider.delete_saved(self.connection, kind=self.kind.currentData()),
                self._refresh_credential_status()))

    def _import_key(self):
        if not self.consent.isChecked() or self.provider is None:
            self.status.setText("Select explicit encrypted-save consent before importing a credential.")
            return
        source, _ = QFileDialog.getOpenFileName(self, "Import credential without displaying its value", "", "Credential JSON (*.json)")
        if not source:
            return
        from app.vault.migration import prepare_credential_import, apply_migration
        kind, connection, policy = self.kind.currentData(), self.connection, self.policy.currentData()
        self.consent.setChecked(False)
        def migrate():
            plan = prepare_credential_import(source, connection, kind, consent=True)
            apply_migration(self.manager.session, plan, replace=True)
            # Reload revokes this page's old provider before importing. Configure
            # the renewed session; the rebuilt app loads the same persisted policy.
            from app.vault.credentials import CredentialProvider
            CredentialProvider(self.manager.session).configure(connection, policy)
            self.manager.configure(credential_policy=str(policy))
        self.reload_requested.emit(migrate)

    def _quota_controls(self):
        self.quota_controls = QWidget(self)
        row = QHBoxLayout(self.quota_controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.quota = CompactNumberInput(self.quota_controls)
        self.quota.setRange(1, 1_000_000)
        self.quota.setValue(max(1, (self.manager.vault().quota_bytes + 1024**3 - 1) // 1024**3))
        self.quota.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quota.setAccessibleName("Vault quota")
        self.quota.setToolTip("Personal storage quota in GiB (1–1,000,000)")
        self.quota_save = QPushButton("Change quota", self.quota_controls)
        self.quota_save.setFixedSize(128, 36)
        self.quota_save.clicked.connect(self._save_quota)
        title = label("Vault quota")
        title.setBuddy(self.quota)
        for widget in (title, self.quota, label("GiB"), self.quota_save):
            row.addWidget(widget)
        row.addStretch()
        self.layout.addWidget(self.quota_controls)

    def _save_quota(self):
        self.quota.interpretText()
        if self._perform(lambda: self.manager.vault().set_quota(self.quota.value() * 1024**3), "Vault quota saved."):
            self._refresh_usage()
            self.status.setText("Vault quota saved.")

    def _change_password(self):
        dialog = profile_dialog(self)
        dialog.setWindowTitle("Change vault password")
        layout = QVBoxLayout(dialog)
        first, second = secret("New vault password"), secret("Repeat new password")
        layout.addWidget(first)
        layout.addWidget(second)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            value = first.text().encode()
            if value and first.text() == second.text():
                self._perform(lambda: self.manager.vault().change_password(value), "Password changed. Older backups keep their previous password.")
            else:
                self.status.setText("Enter matching new passwords.")
        first.clear()
        second.clear()

    def _recovery_key(self):
        def show():
            key = self.manager.vault().generate_recovery_key()
            dialog = profile_dialog(self)
            dialog.setWindowTitle("Save your recovery key separately")
            layout = QVBoxLayout(dialog)
            layout.addWidget(label("This new key replaces the previous recovery key. Keep a copy somewhere accessible "
                "without this vault or its disk. Anyone with this key can unlock this profile. There is no password-reset backdoor."))
            value = QLineEdit(key.hex())
            value.setReadOnly(True)
            value.setAccessibleName("Recovery key")
            layout.addWidget(value)
            export = QPushButton("Export recovery key outside vault…")
            layout.addWidget(export)
            def save():
                path, _ = QFileDialog.getSaveFileName(dialog, "Save independent recovery key", "orsi-recovery-key.txt")
                if path:
                    target = Path(path).absolute()
                    if any(target.is_relative_to(root) for root in self.manager.known_roots):
                        raise VaultError("Choose an independent location outside profile storage.")
                    from app.vault.files import atomic_write
                    atomic_write(target, (key.hex() + "\n").encode())
            export.clicked.connect(lambda: self._perform(save, "Recovery key exported outside the vault."))
            close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            close.rejected.connect(dialog.reject)
            layout.addWidget(close)
            dialog.exec()
            value.clear()
        self._perform(show, "Recovery key created. Keep its copy independently accessible.")

    def _disable_recovery(self):
        if confirm(self, "Disable recovery", "Disable the current recovery key? Older independent backups may still accept it."):
            self._perform(lambda: self.manager.vault().disable_recovery())

    def _destination(self, title):
        from PySide6.QtWidgets import QInputDialog
        from uuid import uuid4
        parent = QFileDialog.getExistingDirectory(self, title + " · choose containing folder", str(self.manager.locator.root.parent))
        if not parent:
            return None
        name, accepted = QInputDialog.getText(self, title, "Name for the new directory (must not exist):",
            text="orsi-profile-" + uuid4().hex[:8])
        name = name.strip()
        if not accepted or not name:
            return None
        if Path(name).name != name or name in {".", ".."}:
            self.status.setText("Enter a new directory name without a path.")
            return None
        return Path(parent).absolute() / name

    def _backup(self):
        path = self._destination("Encrypted backup")
        if path:
            self._perform(lambda: (self.manager._new_location(path), self.manager.vault().backup(path)),
                          "Encrypted backup verified. This independent copy has its own retention.")

    def _restore(self):
        # Available while unlocked here; locked recovery also exposes this control below.
        restore_dialog(self, self.manager, self.transition_requested.emit)

    def _relocate(self):
        mode, accepted = choose_mode(self)
        if not accepted:
            return
        path = self._destination("Relocate personal profile")
        if path and confirm(self, "Relocate verified copy", "Create and verify a copy, then select it? The source and independent backups remain intact; this does not synchronize them."):
            self.transition_requested.emit(lambda: self.manager.relocate(path, mode=mode))

    def _migration_controls(self):
        self._buttons((("Migrate selected personal data…", self._migrate), ("Import a copy into vault…", self._import_copy),
                       ("Review retained originals…", self._originals)))

    def _migrate(self):
        from app.vault.migration import CATEGORIES, prepare_migration, apply_migration
        dialog = profile_dialog(self)
        dialog.setWindowTitle("Choose personal data to migrate")
        dialog.resize(620, 560)
        outer = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        source = QLineEdit(str(self.manager.application_root))
        source.setAccessibleName("Existing application folder")
        skills = QLineEdit(str(Path.home() / ".orsi/skills"))
        skills.setAccessibleName("Existing personal skills folder")
        layout.addWidget(label("Choose an existing O.R.S.I application folder. Select only the categories you want. "
            "Conversations become saved archives. Unsupported features are not added; existing files in the named personal folders are imported."))
        layout.addWidget(source)
        layout.addWidget(skills)
        checks = {}
        for name, title in CATEGORIES.items():
            checks[name] = QCheckBox(title)
            layout.addWidget(checks[name])
        replace = QCheckBox("Replace matching selected settings or records already in this vault")
        layout.addWidget(replace)
        layout.addWidget(label("Import verifies every selected copy before reporting completion. Originals stay unchanged; "
            "you can review their exact locations and choose cleanup separately afterward."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        outer.addWidget(buttons)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            categories = tuple(name for name, check in checks.items() if check.isChecked())
            root, skills_root, replacement = source.text(), skills.text(), replace.isChecked()
            def migrate():
                plan = prepare_migration(root, categories, skills_root=Path(skills_root))
                apply_migration(self.manager.session, plan, replace=replacement)
            self.reload_requested.emit(migrate)

    def _import_copy(self):
        title = "Import a copy into vault; original remains unchanged"
        if self.manager.guidance():
            title = "Recommended: " + title
        source, _ = QFileDialog.getOpenFileName(self, title)
        if not source:
            return
        def copy():
            from app.vault.migration import MigrationPlan, _add, apply_migration
            from uuid import uuid4
            plan = MigrationPlan(("explicit_import",))
            _add(plan, source, "imports/" + uuid4().hex + "/" + Path(source).name)
            apply_migration(self.manager.session, plan)
        self.reload_requested.emit(copy)

    def _originals(self):
        from app.vault.migration import retained_originals, cleanup_originals
        dialog = profile_dialog(self)
        dialog.setWindowTitle("Retained plaintext originals")
        dialog.resize(720, 430)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("These originals remain outside the vault. Select specific originals to remove. "
            "Credential cleanup removes only its imported JSON field. Exports and independent backups are not swept. "
            "Deletion does not guarantee physical erasure on an SSD."))
        listing = QListWidget()
        listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        listing.setAccessibleName("Retained original locations")
        layout.addWidget(listing)
        vault = self.manager.vault()
        for key in vault.list_paths():
            if key.startswith("migration/"):
                try:
                    originals = retained_originals(self.manager.session, key)
                except VaultError:
                    continue
                for path in originals:
                    item = QListWidgetItem(path)
                    item.setData(Qt.ItemDataRole.UserRole, (key, path))
                    listing.addItem(item)
        remove = QPushButton("Remove selected verified originals")
        layout.addWidget(remove)
        def cleanup():
            selected = {}
            for item in listing.selectedItems():
                key, path = item.data(Qt.ItemDataRole.UserRole)
                selected.setdefault(key, []).append(path)
            if selected and confirm(dialog, "Remove originals", "Remove only the selected originals after rechecking their protected copies? This cannot guarantee physical erasure."):
                def action():
                    for key, paths in selected.items():
                        cleanup_originals(self.manager.session, key, paths, consent=True)
                    dialog.accept()
                self._perform(action, "Selected originals removed. Outside exports and independent backups remain.")
        remove.clicked.connect(cleanup)
        dialog.exec()

    def _backup_retention_controls(self):
        self.retention_controls = QWidget(self)
        row = QGridLayout(self.retention_controls)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.backup_count = CompactNumberInput(self.retention_controls)
        self.backup_days = CompactNumberInput(self.retention_controls)
        policy = self.manager.vault()._catalog["backup_policy"]
        self.backup_count.setRange(0, 100)
        self.backup_count.setValue(policy["max_count"])
        self.backup_count.setAccessibleName("Managed backup count")
        self.backup_count.setToolTip("Maximum managed backups (0 disables managed backups)")
        self.backup_days.setRange(0, 3650)
        self.backup_days.setValue(policy["max_age_seconds"] // 86400)
        self.backup_days.setAccessibleName("Managed backup age in days")
        self.backup_days.setToolTip("Maximum backup age in days (0 means no age limit)")
        for index, (title, field, unit) in enumerate((("Managed backups", self.backup_count, "copies"),
                                                     ("Backup days", self.backup_days, "days"))):
            field.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption = label(title)
            caption.setBuddy(field)
            row.addWidget(caption, index, 0)
            row.addWidget(field, index, 1)
            row.addWidget(label(unit), index, 2)
        self.backup_save = QPushButton("Apply retention", self.retention_controls)
        self.backup_save.setFixedSize(128, 36)
        self.backup_save.clicked.connect(self._backup_retention)
        row.addWidget(self.backup_save, 1, 3)
        row.setColumnStretch(4, 1)
        self.layout.addWidget(self.retention_controls)
        self.layout.addWidget(label("0 backups disables managed backups. 0 days means no age limit."))

    def _retention_controls(self):
        self._card("Saved records", "Browse archived conversations and imported material. View a record to export a copy.")
        self.records = QListWidget()
        self.records.setAccessibleName("Saved personal records")
        self.records.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.records.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.records.setSpacing(3)
        self.records.setMinimumHeight(160)
        self.records.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.layout.addWidget(self.records)
        self._buttons((("Refresh saved records", self._refresh_records), ("View selected record…", self._view_record),
                       ("Delete selected records…", self._delete_records)))
        self.records.itemDoubleClicked.connect(lambda _: self._view_record())
        self._refresh_records()
        self._card("Cleanup", "Unsent attachment drafts expire after 24 hours. Independent copies and current composer drafts remain.")
        self._buttons((("Clean expired drafts and caches", lambda: self._perform(self.manager.maintenance, "Expired data cleaned; retained records and independent copies remain.")),
                       ("Delete abandoned drafts…", self._delete_abandoned_drafts)))
        self.layout.addWidget(label("Deleting saved records removes their unshared assets. Shared assets, outside originals, exports and independent backups remain."))

    def _backup_retention(self):
        self.backup_count.interpretText()
        self.backup_days.interpretText()
        if confirm(self, "Apply backup retention", "Apply this policy and remove excess application-managed backups? Independent backups remain unchanged and may retain deleted data or old credentials."):
            self._perform(lambda: self.manager.vault().set_backup_policy(BackupPolicy(
                self.backup_count.value(), self.backup_days.value() * 86400)))

    def _delete_abandoned_drafts(self):
        if confirm(self, "Delete abandoned drafts", "Remove uncommitted attachment copies left by earlier sessions? Current composer drafts and retained images remain; external originals and backups remain."):
            def remove():
                store = getattr(getattr(self.window.service, "store", None), "attachment_store", None)
                if store is None:
                    raise VaultError("Draft cleanup is unavailable in this session.")
                with store.protect_drafts():
                    self.manager.delete_abandoned_drafts(owned_ids=tuple(store._drafts))
            self._perform(remove, "Abandoned attachment drafts removed. Current drafts and retained records remain.")

    def _refresh_records(self):
        self.records.clear()
        for path in self.manager.vault().list_paths():
            if path.startswith(("state/conversation_v1/archives/", "imports/", "documents/", "templates/", "instructions/",
                                "personality/", "memory/", "context/", "indexes/", "drafts/")):
                item = QListWidgetItem(path)
                item.setToolTip(path)
                self.records.addItem(item)

    def _delete_records(self):
        paths = [item.text() for item in self.records.selectedItems()]
        if paths and confirm(self, "Delete saved personal data", "Delete selected records and their unshared associated data? Shared assets, outside originals, exports and independent backups remain. Physical erasure is not guaranteed."):
            if self._perform(lambda: self.manager.delete_records(paths), "Selected records deleted. Independent copies remain."):
                self._refresh_records()

    def _view_record(self):
        current = self.records.currentItem()
        if current is None:
            return
        def view():
            key = current.text()
            data = self.manager.vault().read(key)
            dialog = profile_dialog(self)
            dialog.setWindowTitle("Saved personal record")
            dialog.resize(700, 500)
            layout = QVBoxLayout(dialog)
            body = QTextEdit()
            body.setReadOnly(True)
            body.setAccessibleName("Saved record contents")
            layout.addWidget(body)
            refs = ()
            if key.startswith("state/conversation_v1/archives/"):
                from app.conversation.store import Conversation
                conversation = Conversation.model_validate_json(data)
                body.setPlainText("\n\n".join(m.role + ": " + m.content for m in conversation.messages))
                refs = tuple({r.id: r for m in conversation.messages for r in (*m.attachments, *m.generated_images) if r.kind == "image"}.values())
            else:
                body.setPlainText(data[:2 * 1024 * 1024].decode("utf-8", errors="replace"))
                if key.startswith("imports/images/"):
                    from app.inference.attachments import AttachmentReference
                    refs = (AttachmentReference.model_validate_json(json.dumps(json.loads(data)["image"])),)
            if refs:
                image = QPushButton("View saved images…")
                layout.addWidget(image)
                image.clicked.connect(lambda: (dialog.accept(), self.window._open_image_viewer(refs, 0)))
            export = QPushButton("Export outside vault…")
            layout.addWidget(label("An exported copy remains outside vault protection after locking or deleting this record."))
            layout.addWidget(export)
            def save():
                path, _ = QFileDialog.getSaveFileName(dialog, "Export outside vault", Path(key).name)
                if path:
                    target = Path(path).absolute()
                    if any(target.is_relative_to(root) for root in self.manager.known_roots):
                        raise VaultError("Choose an export destination outside profile storage.")
                    from app.vault.files import atomic_write
                    atomic_write(target, data)
            export.clicked.connect(lambda: self._perform(save, "Copy exported outside vault."))
            unregister = self.manager.session.register(clear=lambda: (body.clear(), dialog.reject()))
            try:
                dialog.exec()
            finally:
                unregister()
                body.clear()
        self._perform(view, "")


def choose_mode(parent):
    from PySide6.QtWidgets import QInputDialog
    value, accepted = QInputDialog.getItem(parent, "Storage mode", "Destination storage:", ("Local", "Portable"), 0, False)
    return value.lower(), accepted


def restore_dialog(parent, manager, transition):
    source = QFileDialog.getExistingDirectory(parent, "Select encrypted backup directory")
    if not source:
        return
    dialog = profile_dialog(parent)
    dialog.setWindowTitle("Restore encrypted backup")
    layout = QVBoxLayout(dialog)
    layout.addWidget(label("Restore to a new directory. The backup and current source remain intact. Use the backup's password or recovery key."))
    mode = combo((("Local", "local"), ("Portable", "portable")))
    path = QLineEdit(str(manager.default_location()))
    path.setAccessibleName("Restore destination")
    password, recovery = secret("Backup password"), secret("Backup recovery key (optional)")
    for item in (mode, path, password, recovery):
        layout.addWidget(item)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        secret_value, key = password.text().encode(), recovery.text().strip()
        destination, destination_mode = Path(path.text()), mode.currentData()
        password.clear()
        recovery.clear()
        transition(lambda: manager.restore(source, destination, mode=destination_mode,
            password=secret_value if not key else None, recovery_key=bytes.fromhex(key) if key else None))
    password.clear()
    recovery.clear()
