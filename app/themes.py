THEMES = {
    "Midnight": """
QWidget {
    background: #10131a;
    color: #e9edf7;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}
QMainWindow {
    background: #10131a;
}
QLabel {
    background: transparent;
}
QFrame#Sidebar, QFrame#HeaderBar, QFrame#ComposerFrame, QFrame#ChatSurface {
    background: #171b24;
    border: 1px solid #252b36;
    border-radius: 16px;
}
QLabel#TitleLabel {
    font-size: 16pt;
    font-weight: 700;
    color: #ffffff;
}
QLabel#SubtleLabel {
    color: #9ea8ba;
}
QPushButton {
    background: #2a3342;
    color: #f3f6fc;
    border: 1px solid #344054;
    border-radius: 12px;
    padding: 8px 12px;
}
QPushButton:hover {
    background: #334155;
}
QPushButton:pressed {
    background: #253042;
}
QPushButton#AccentButton {
    background: #5b8cff;
    border: 1px solid #6a98ff;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#AccentButton:hover {
    background: #6a98ff;
}
QPushButton#DangerButton {
    background: #4a2228;
    border: 1px solid #6a2e37;
}
QPushButton#DangerButton:hover {
    background: #5e2a31;
}
QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTextBrowser {
    background: #0f141c;
    color: #edf2ff;
    border: 1px solid #2d3748;
    border-radius: 12px;
    padding: 8px;
}
QListWidget::item {
    border-radius: 10px;
    padding: 8px;
    margin: 2px;
}
QListWidget::item:selected {
    background: #243247;
    border: 1px solid #436194;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: #151922;
    width: 12px;
    margin: 2px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #2f3949;
    min-height: 30px;
    border-radius: 6px;
}
QCheckBox {
    spacing: 8px;
}
QDialog {
    background: #10131a;
}
""",
    "Graphite": """
QWidget {
    background: #f3f5f8;
    color: #17202b;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 10pt;
}
QMainWindow {
    background: #eef2f7;
}
QLabel {
    background: transparent;
}
QFrame#Sidebar, QFrame#HeaderBar, QFrame#ComposerFrame, QFrame#ChatSurface {
    background: #ffffff;
    border: 1px solid #d8dee9;
    border-radius: 16px;
}
QLabel#TitleLabel {
    font-size: 16pt;
    font-weight: 700;
    color: #0f172a;
}
QLabel#SubtleLabel {
    color: #64748b;
}
QPushButton {
    background: #e2e8f0;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    padding: 8px 12px;
}
QPushButton:hover {
    background: #d9e2ec;
}
QPushButton:pressed {
    background: #ccd7e5;
}
QPushButton#AccentButton {
    background: #2563eb;
    border: 1px solid #2563eb;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#AccentButton:hover {
    background: #2d6ff5;
}
QPushButton#DangerButton {
    background: #fee2e2;
    border: 1px solid #fecaca;
}
QPushButton#DangerButton:hover {
    background: #fecaca;
}
QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTextBrowser {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #d1d9e6;
    border-radius: 12px;
    padding: 8px;
}
QListWidget::item {
    border-radius: 10px;
    padding: 8px;
    margin: 2px;
}
QListWidget::item:selected {
    background: #dbeafe;
    border: 1px solid #93c5fd;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: #f1f5f9;
    width: 12px;
    margin: 2px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 30px;
    border-radius: 6px;
}
QCheckBox {
    spacing: 8px;
}
QDialog {
    background: #f3f5f8;
}
""",
}