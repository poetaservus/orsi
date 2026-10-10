"""One control palette for Settings pages and their app-owned dialogs."""
from pathlib import Path


CONTROL_SURFACE = "#243247"


def settings_control_style(*roots):
    def select(*widgets):
        return ", ".join(f"{root} {widget}" for root in roots for widget in widgets)

    chevron = (Path(__file__).with_name("assets") / "settings_chevron.svg").as_posix()
    return f"""
{select('QPushButton')} {{
 background: {CONTROL_SURFACE}; color: #e4e5eb; border: 1px solid #40536d;
 border-radius: 6px; padding: 6px 10px; font-size: 14px;
}}
{select('QPushButton:hover')} {{ background: #2d4059; border-color: #6983a2; }}
{select('QPushButton:pressed')} {{ background: #1c2a3f; }}
{select('QPushButton:focus')} {{ border-color: #91bfe0; }}
{select('QPushButton:disabled')} {{ background: {CONTROL_SURFACE}; color: #a2afc1; border-color: #35465e; }}
{select('QComboBox', 'QLineEdit', 'QSpinBox', 'QTextEdit', 'QListWidget')} {{
 background: {CONTROL_SURFACE}; color: #e4e5eb; border: 1px solid #40536d;
 border-radius: 4px; padding: 5px 8px; font-size: 14px;
 selection-background-color: #3b5675; selection-color: #f4f6fb;
}}
{select('QComboBox')} {{ padding-right: 26px; }}
{select('QComboBox:hover', 'QComboBox:focus', 'QLineEdit:focus', 'QSpinBox:focus', 'QTextEdit:focus')} {{ border-color: #91bfe0; }}
{select('QComboBox:disabled')} {{ color: #a2afc1; border-color: #35465e; }}
{select('QComboBox::drop-down')} {{ width: 24px; border: none; background: transparent; }}
{select('QComboBox::down-arrow')} {{ image: url("{chevron}"); width: 9px; height: 6px; }}
{select('QComboBox QAbstractItemView')} {{
 background: {CONTROL_SURFACE}; color: #e4e5eb; border: 1px solid #6983a2;
 selection-background-color: #3b5675; selection-color: #f4f6fb; outline: 0;
}}
{select('QListWidget')} {{ outline: 0; padding: 4px; }}
{select('QListWidget::item')} {{ padding: 7px 8px; border: 1px solid transparent; border-radius: 4px; }}
{select('QListWidget::item:hover')} {{ background: #2d4059; }}
{select('QListWidget::item:selected', 'QListWidget::item:selected:!active')} {{
 background: #3b5675; color: #f4f6fb; border: 1px solid #6983a2;
}}
{select('QMenu')} {{ background: {CONTROL_SURFACE}; color: #e4e5eb; border: 1px solid #40536d; padding: 5px; }}
{select('QMenu::item')} {{ padding: 8px 16px; }}
{select('QMenu::item:selected')} {{ background: #3b5675; }}
"""
