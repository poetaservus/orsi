"""One control palette for Settings pages and their app-owned dialogs."""
from pathlib import Path


def settings_control_style(*roots):
    def select(*widgets):
        return ", ".join(f"{root} {widget}" for root in roots for widget in widgets)

    chevron = (Path(__file__).with_name("assets") / "settings_chevron.svg").as_posix()
    return f"""
{select('QPushButton')} {{
 background: #303238; color: #e4e5eb; border: 1px solid #4a4d54;
 border-radius: 6px; padding: 6px 10px; font-size: 14px;
}}
{select('QPushButton:hover')} {{ background: #3e4551; border-color: #707b8b; }}
{select('QPushButton:pressed')} {{ background: #242a33; }}
{select('QPushButton:focus')} {{ border-color: #91bfe0; }}
{select('QPushButton:disabled')} {{ background: #303238; color: #929baa; border-color: #454b55; }}
{select('QComboBox', 'QLineEdit', 'QSpinBox', 'QTextEdit', 'QListWidget')} {{
 background: #303238; color: #e4e5eb; border: 1px solid #4a4d54;
 border-radius: 4px; padding: 5px 8px; font-size: 14px;
 selection-background-color: #40556e; selection-color: #f4f6fb;
}}
{select('QComboBox')} {{ padding-right: 26px; }}
{select('QComboBox:hover', 'QComboBox:focus', 'QLineEdit:focus', 'QSpinBox:focus', 'QTextEdit:focus')} {{ border-color: #91bfe0; }}
{select('QComboBox:disabled')} {{ color: #929baa; border-color: #454b55; }}
{select('QComboBox::drop-down')} {{ width: 24px; border: none; background: transparent; }}
{select('QComboBox::down-arrow')} {{ image: url("{chevron}"); width: 9px; height: 6px; }}
{select('QComboBox QAbstractItemView')} {{
 background: #303238; color: #e4e5eb; border: 1px solid #626c7b;
 selection-background-color: #40556e; selection-color: #f4f6fb; outline: 0;
}}
{select('QListWidget')} {{ outline: 0; padding: 4px; }}
{select('QListWidget::item')} {{ padding: 7px 8px; border: 1px solid transparent; border-radius: 4px; }}
{select('QListWidget::item:hover')} {{ background: #394350; }}
{select('QListWidget::item:selected', 'QListWidget::item:selected:!active')} {{
 background: #40556e; color: #f4f6fb; border: 1px solid #6786a5;
}}
"""
