"""Offline Qt translations and explicitly marked, state-preserving UI text.

Only UiText values are rebound on LanguageChange. User/model/file text remains
ordinary str, even when it happens to equal an interface label.
"""
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QLocale, QObject, QSignalBlocker, Qt, QTranslator, Signal
from PySide6 import QtWidgets

from app.conversation.response_language import RESPONSE_LANGUAGES


LANGUAGES = RESPONSE_LANGUAGES
CODES = frozenset(item.code for item in LANGUAGES)
CATALOGS = Path(__file__).with_name("translations")
TEXT_ROLE = int(Qt.ItemDataRole.UserRole) + 291


class UiText(str):
    def __new__(cls, source, **values):
        value = super().__new__(cls, cls.render(source, values))
        value.source, value.values = source, values
        return value

    @staticmethod
    def render(source, values):
        translated = QCoreApplication.translate("OrsiUI", source)
        resolved = {key: value.resolve() if isinstance(value, UiText) else value for key, value in values.items()}
        return translated.format_map(resolved) if values else translated

    def resolve(self):
        return self.render(self.source, self.values)


def ui_text(source, **values):
    if isinstance(source, UiText) and not values:
        return source
    return UiText(source, **values)


def system_language():
    # OS preferences, never conversation text. Keep Bokmål and Nynorsk distinct.
    for tag in QLocale.system().uiLanguages():
        code = tag.replace("_", "-").split("-")[0].lower()
        code = {"no": "nb"}.get(code, code)
        if code in CODES - {"auto"}:
            return code
    return "en"


class LanguageRuntime(QObject):
    changed = Signal()

    def __init__(self, application):
        super().__init__(application)
        self.application = application
        self.code = "en"
        self.translator = None

    def prepare(self, selection):
        if selection not in CODES:
            raise ValueError("Unsupported GUI language")
        code = system_language() if selection == "auto" else selection
        translator = None
        if code != "en":
            translator = QTranslator(self)
            if not translator.load(str(CATALOGS / f"{code}.qm")):
                translator.deleteLater()
                raise ValueError("The GUI translation is unavailable")
        return code, translator

    def apply(self, prepared):
        code, translator = prepared
        previous = self.translator
        # Install the replacement first, so intermediate LanguageChange events
        # never expose another profile's language or an untranslated interface.
        if translator is not None:
            self.application.installTranslator(translator)
        self.code, self.translator = code, translator
        if previous is not None:
            self.application.removeTranslator(previous)
            previous.deleteLater()
        self.changed.emit()


def language_runtime():
    application = QCoreApplication.instance()
    runtime = getattr(application, "_orsi_language_runtime", None)
    if runtime is None:
        runtime = LanguageRuntime(application)
        application._orsi_language_runtime = runtime
    return runtime


class _Localized:
    def __init__(self, *args, **kwargs):
        self._ui_bindings = {}
        initial = args[0] if args and isinstance(args[0], UiText) else None
        super().__init__(*args, **kwargs)
        if initial is not None:
            if isinstance(self, (QtWidgets.QGroupBox, QtWidgets.QMenu)):
                self.setTitle(initial)
            else:
                self.setText(initial)

    def changeEvent(self, event):  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslate_ui()

    def clear(self):
        # Native clear() does not call Python's setText override. Discard the
        # binding too, so a later language switch cannot resurrect cleared text.
        self._ui_bindings.pop("setText", None)
        return super().clear()

    def use_description_as_tooltip(self):
        self.setToolTip(self._ui_bindings.get("setAccessibleDescription", self.accessibleDescription()))

    def retranslate_ui(self):
        blocker = QSignalBlocker(self)
        for setter, text in self._ui_bindings.items():
            getattr(super(), setter)(text.resolve())
        if isinstance(self, QtWidgets.QComboBox):
            for index in range(self.count()):
                text = self.itemData(index, TEXT_ROLE)
                if isinstance(text, dict) and set(text) == {"source", "values"}:
                    QtWidgets.QComboBox.setItemText(self, index, UiText.render(text["source"], text["values"]))
        if isinstance(self, QtWidgets.QTabWidget):
            for index in range(self.count()):
                text = getattr(self.widget(index), "_ui_tab_text", None)
                if isinstance(text, UiText):
                    QtWidgets.QTabWidget.setTabText(self, index, text.resolve())
        if isinstance(self, QtWidgets.QListWidget):
            for index in range(self.count()):
                item = self.item(index)
                text = item.data(TEXT_ROLE)
                if isinstance(text, UiText):
                    item.setText(text.resolve())
        if isinstance(self, QtWidgets.QMenu):
            for action in self.actions():
                text = getattr(action, "_ui_action_text", None)
                if isinstance(text, UiText):
                    action.setText(text.resolve())
        del blocker
        self.updateGeometry()


def _setter(name):
    def setter(self, value):
        if isinstance(value, UiText):
            self._ui_bindings[name] = value
            value = value.resolve()
        else:
            self._ui_bindings.pop(name, None)
        getattr(super(_Localized, self), name)(value)
    return setter


for _name in ("setText", "setTitle", "setWindowTitle", "setToolTip", "setStatusTip",
              "setAccessibleName", "setAccessibleDescription", "setPlaceholderText", "setInformativeText"):
    setattr(_Localized, _name, _setter(_name))


def _widget(name):
    return type(name, (_Localized, getattr(QtWidgets, name)), {"__module__": __name__})


for _name in ("QWidget", "QFrame", "QMainWindow", "QDialog", "QLabel", "QPushButton",
              "QToolButton", "QCheckBox", "QRadioButton", "QLineEdit", "QPlainTextEdit",
              "QTextEdit", "QGroupBox", "QListWidget", "QSpinBox", "QScrollArea", "QMessageBox", "QInputDialog", "QSlider", "QProgressBar"):
    globals()[_name] = _widget(_name)


class QComboBox(_Localized, QtWidgets.QComboBox):
    def addItem(self, *args, **kwargs):  # noqa: N802
        text = next((arg for arg in args if isinstance(arg, UiText)), None)
        super().addItem(*args, **kwargs)
        if text is not None:
            self.setItemData(self.count() - 1, {"source": text.source, "values": text.values}, TEXT_ROLE)

    def setItemText(self, index, text):  # noqa: N802
        self.setItemData(index, {"source": text.source, "values": text.values} if isinstance(text, UiText) else None, TEXT_ROLE)
        super().setItemText(index, text.resolve() if isinstance(text, UiText) else text)

    def insertItem(self, index, *args, **kwargs):  # noqa: N802
        super().insertItem(index, *args, **kwargs)
        text = next((arg for arg in args if isinstance(arg, UiText)), None)
        if text is not None:
            self.setItemData(index, {"source": text.source, "values": text.values}, TEXT_ROLE)


class QFileDialog(_Localized, QtWidgets.QFileDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if len(args) > 1 and isinstance(args[1], UiText):
            self.setWindowTitle(args[1])


class QTabWidget(_Localized, QtWidgets.QTabWidget):
    def addTab(self, widget, *args):  # noqa: N802
        index = super().addTab(widget, *args)
        self.setTabText(index, args[-1])
        return index

    def setTabText(self, index, text):  # noqa: N802
        self.widget(index)._ui_tab_text = text if isinstance(text, UiText) else None
        super().setTabText(index, text.resolve() if isinstance(text, UiText) else text)


class QFormLayout(QtWidgets.QFormLayout):
    def addRow(self, *args):  # noqa: N802
        if args and isinstance(args[0], UiText):
            label = QLabel(args[0])
            label.setWordWrap(True)
            if len(args) > 1 and isinstance(args[1], QtWidgets.QWidget):
                label.setBuddy(args[1])
            args = (label, *args[1:])
        super().addRow(*args)


class QMenu(_Localized, QtWidgets.QMenu):
    def addAction(self, *args):  # noqa: N802
        action = super().addAction(*args)
        text = next((arg for arg in args if isinstance(arg, UiText)), None)
        if text is not None:
            action._ui_action_text = text
        return action


class QDialogButtonBox(_Localized, QtWidgets.QDialogButtonBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.retranslate_ui()

    def retranslate_ui(self):
        super().retranslate_ui()
        for name, source in (("Ok", "OK"), ("Save", "Save"), ("Cancel", "Cancel"),
                             ("Close", "Close"), ("Yes", "Yes"), ("No", "No"),
                             ("Apply", "Apply"), ("Reset", "Reset")):
            button = self.button(getattr(self.StandardButton, name))
            if button is not None:
                button.setText(str(ui_text(source)))
