"""One control palette for Settings pages and their app-owned dialogs."""
from pathlib import Path
import re


CONTROL_SURFACE = "#243247"
SETTINGS_BORDER = "#505050"
SETTINGS_BORDER_HOVER = "#686868"
SETTINGS_BORDER_FOCUS = "#888888"


def settings_typography(widget, source):
    """Enlarge only the full-window Settings view, retaining each original style source."""
    while widget is not None:
        step = getattr(widget, "settings_font_step", 0)
        if step:
            return re.sub(r"(font-size\s*:\s*)(\d+)(px\b)",
                          lambda match: f"{match[1]}{int(match[2]) + step}{match[3]}", source)
        if widget.isWindow():
            break  # App-owned dialogs keep their established typography.
        widget = widget.parentWidget()
    return source


def settings_control_style(*roots):
    def select(*widgets):
        return ", ".join(f"{root} {widget}" for root in roots for widget in widgets)

    chevron = (Path(__file__).with_name("assets") / "settings_chevron.svg").as_posix()
    check = (Path(__file__).with_name("assets") / "check.svg").as_posix()
    return f"""
{select('QPushButton')} {{
 background: {CONTROL_SURFACE}; color: #e4e5eb; border: 1px solid {SETTINGS_BORDER};
 border-radius: 6px; padding: 6px 10px; font-size: 14px; outline: none;
}}
{select('QPushButton:hover')} {{ background: #2d4059; border-color: {SETTINGS_BORDER_HOVER}; }}
{select('QPushButton:pressed')} {{ background: #1c2a3f; }}
{select('QPushButton:focus')} {{ border-color: {SETTINGS_BORDER_FOCUS}; }}
{select('QPushButton:disabled')} {{ background: {CONTROL_SURFACE}; color: #a2afc1; border-color: #3d3d3d; }}
{select('QComboBox', 'QLineEdit', 'QSpinBox', 'QDoubleSpinBox', 'QTextEdit', 'QPlainTextEdit', 'QListWidget')} {{
 background: {CONTROL_SURFACE}; color: #e4e5eb; border: 1px solid {SETTINGS_BORDER};
 border-radius: 4px; padding: 5px 8px; font-size: 14px;
 selection-background-color: #3b5675; selection-color: #f4f6fb; outline: none;
}}
{select('QComboBox')} {{ padding-right: 26px; }}
{select('QComboBox:hover', 'QComboBox:focus', 'QLineEdit:focus', 'QSpinBox:focus', 'QDoubleSpinBox:focus', 'QTextEdit:focus', 'QPlainTextEdit:focus', 'QListWidget:focus')} {{ border-color: {SETTINGS_BORDER_FOCUS}; }}
{select('QComboBox:disabled')} {{ color: #a2afc1; border-color: #3d3d3d; }}
{select('QComboBox::drop-down')} {{ width: 24px; border: none; background: transparent; }}
{select('QComboBox::down-arrow')} {{ image: url("{chevron}"); width: 9px; height: 6px; }}
{select('QComboBox QAbstractItemView')} {{
 background: {CONTROL_SURFACE}; color: #e4e5eb; border: 1px solid {SETTINGS_BORDER_HOVER};
 selection-background-color: #3b5675; selection-color: #f4f6fb; outline: 0;
}}
{select('QComboBox QAbstractItemView::item')} {{ border: 1px solid transparent; }}
{select('QComboBox QAbstractItemView::item:selected')} {{ border-color: {SETTINGS_BORDER_HOVER}; outline: none; }}
{select('QListWidget')} {{ outline: 0; padding: 4px; }}
{select('QListWidget::item')} {{ padding: 7px 8px; border: 1px solid transparent; border-radius: 4px; }}
{select('QListWidget::item:hover')} {{ background: #2d4059; }}
{select('QListWidget::item:selected', 'QListWidget::item:selected:!active')} {{
 background: #3b5675; color: #f4f6fb; border: 1px solid {SETTINGS_BORDER_HOVER};
}}
{select('QMenu')} {{ background: {CONTROL_SURFACE}; color: #e4e5eb; border: 1px solid {SETTINGS_BORDER}; padding: 5px; }}
{select('QMenu::item')} {{ padding: 8px 16px; }}
{select('QMenu::item:selected')} {{ background: #3b5675; }}
{select('QRadioButton', 'QCheckBox')} {{ spacing: 8px; outline: none; }}
{select('QRadioButton::indicator', 'QCheckBox::indicator')} {{
 width: 16px; height: 16px; border: 1px solid {SETTINGS_BORDER_HOVER}; background: {CONTROL_SURFACE};
}}
{select('QRadioButton::indicator')} {{ border-radius: 9px; }}
{select('QCheckBox::indicator')} {{ border-radius: 3px; }}
{select('QRadioButton::indicator:hover', 'QRadioButton::indicator:focus', 'QCheckBox::indicator:hover', 'QCheckBox::indicator:focus')} {{ border-color: {SETTINGS_BORDER_FOCUS}; }}
{select('QRadioButton::indicator:checked')} {{ background: #e4e5eb; border-color: {SETTINGS_BORDER_HOVER}; }}
{select('QCheckBox::indicator:checked')} {{ background: {SETTINGS_BORDER_HOVER}; image: url("{check}"); }}
{select('QRadioButton::indicator:disabled', 'QCheckBox::indicator:disabled')} {{ border-color: #3d3d3d; }}
{select('QTabBar::tab')} {{ outline: none; }}
"""
