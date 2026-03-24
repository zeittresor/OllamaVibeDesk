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
    width: 16px;
    margin: 2px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #2f3949;
    min-height: 36px;
    border-radius: 7px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #151922; height: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:horizontal { background: #2f3949; min-width: 36px; border-radius: 7px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QCheckBox {
    spacing: 8px;
}
QDialog {
    background: #10131a;
}
QProgressBar {
    border: 1px solid #344054;
    border-radius: 10px;
    background: #111827;
    text-align: center;
    min-height: 18px;
}
QProgressBar::chunk {
    background: #5b8cff;
    border-radius: 8px;
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
    width: 16px;
    margin: 2px;
    border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 36px;
    border-radius: 7px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #f1f5f9; height: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:horizontal { background: #cbd5e1; min-width: 36px; border-radius: 7px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QCheckBox {
    spacing: 8px;
}
QDialog {
    background: #f3f5f8;
}
QProgressBar {
    border: 1px solid #cbd5e1;
    border-radius: 10px;
    background: #ffffff;
    text-align: center;
    min-height: 18px;
}
QProgressBar::chunk {
    background: #2563eb;
    border-radius: 8px;
}
""",
    "Matrix": """
QWidget { background: #050b05; color: #b7ffb7; font-family: "Consolas", "Segoe UI", sans-serif; font-size: 10pt; }
QMainWindow { background: #050b05; }
QLabel { background: transparent; }
QFrame#Sidebar, QFrame#HeaderBar, QFrame#ComposerFrame, QFrame#ChatSurface { background: #081108; border: 1px solid #1d5c1d; border-radius: 16px; }
QLabel#TitleLabel { font-size: 16pt; font-weight: 700; color: #d9ffd9; }
QLabel#SubtleLabel { color: #7ae67a; }
QPushButton { background: #0d1a0d; color: #c7ffc7; border: 1px solid #2b7a2b; border-radius: 12px; padding: 8px 12px; }
QPushButton:hover { background: #123012; }
QPushButton:pressed { background: #0c240c; }
QPushButton#AccentButton { background: #1f9d3a; border: 1px solid #34d058; color: #f3fff3; font-weight: 700; }
QPushButton#DangerButton { background: #302010; border: 1px solid #7f4f24; color: #ffe6bf; }
QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTextBrowser { background: #061006; color: #d8ffd8; border: 1px solid #1f5c1f; border-radius: 12px; padding: 8px; }
QListWidget::item:selected { background: #0f2a0f; border: 1px solid #34d058; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #081108; width: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:vertical { background: #1f5c1f; min-height: 36px; border-radius: 7px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #081108; height: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:horizontal { background: #1f5c1f; min-width: 36px; border-radius: 7px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QDialog { background: #050b05; }
QProgressBar { border: 1px solid #1f5c1f; border-radius: 10px; background: #061006; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #34d058; border-radius: 8px; }
""",
    "Devil": """
QWidget { background: #16090a; color: #ffe7e7; font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; }
QMainWindow { background: #16090a; }
QLabel { background: transparent; }
QFrame#Sidebar, QFrame#HeaderBar, QFrame#ComposerFrame, QFrame#ChatSurface { background: #231012; border: 1px solid #5e2028; border-radius: 16px; }
QLabel#TitleLabel { font-size: 16pt; font-weight: 700; color: #fff5f5; }
QLabel#SubtleLabel { color: #ff9ea7; }
QPushButton { background: #3b1820; color: #fff1f1; border: 1px solid #7e2230; border-radius: 12px; padding: 8px 12px; }
QPushButton:hover { background: #52202a; }
QPushButton#AccentButton { background: #c62839; border: 1px solid #e23d52; color: #ffffff; font-weight: 700; }
QPushButton#DangerButton { background: #4c1419; border: 1px solid #9f2b35; }
QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTextBrowser { background: #1b0d10; color: #fff1f1; border: 1px solid #60202b; border-radius: 12px; padding: 8px; }
QListWidget::item:selected { background: #3a1620; border: 1px solid #e23d52; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #1b0d10; width: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:vertical { background: #7e2230; min-height: 36px; border-radius: 7px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #1b0d10; height: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:horizontal { background: #7e2230; min-width: 36px; border-radius: 7px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QDialog { background: #16090a; }
QProgressBar { border: 1px solid #60202b; border-radius: 10px; background: #1b0d10; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #e23d52; border-radius: 8px; }
""",
    "Steampunk": """
QWidget { background: #221a12; color: #f2e6d0; font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; }
QMainWindow { background: #221a12; }
QLabel { background: transparent; }
QFrame#Sidebar, QFrame#HeaderBar, QFrame#ComposerFrame, QFrame#ChatSurface { background: #2f2419; border: 1px solid #70543a; border-radius: 16px; }
QLabel#TitleLabel { font-size: 16pt; font-weight: 700; color: #fff6e8; }
QLabel#SubtleLabel { color: #d0b38c; }
QPushButton { background: #4a3826; color: #fff6e8; border: 1px solid #8a6a46; border-radius: 12px; padding: 8px 12px; }
QPushButton:hover { background: #5b452d; }
QPushButton#AccentButton { background: #b9772b; border: 1px solid #d79342; color: #fff8ef; font-weight: 700; }
QPushButton#DangerButton { background: #5f2f23; border: 1px solid #9e4a35; }
QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTextBrowser { background: #261d14; color: #fff2df; border: 1px solid #7a5d3f; border-radius: 12px; padding: 8px; }
QListWidget::item:selected { background: #483522; border: 1px solid #d79342; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #261d14; width: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:vertical { background: #8a6a46; min-height: 36px; border-radius: 7px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #2f2419; height: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:horizontal { background: #8a6a46; min-width: 36px; border-radius: 7px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QDialog { background: #221a12; }
QProgressBar { border: 1px solid #7a5d3f; border-radius: 10px; background: #261d14; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #d79342; border-radius: 8px; }
""",
    "Fantasy": """
QWidget { background: #11111c; color: #efe7ff; font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; }
QMainWindow { background: #11111c; }
QLabel { background: transparent; }
QFrame#Sidebar, QFrame#HeaderBar, QFrame#ComposerFrame, QFrame#ChatSurface { background: #1a1a2a; border: 1px solid #4b3d72; border-radius: 16px; }
QLabel#TitleLabel { font-size: 16pt; font-weight: 700; color: #ffffff; }
QLabel#SubtleLabel { color: #c4b5fd; }
QPushButton { background: #2d2544; color: #f5efff; border: 1px solid #6f5db7; border-radius: 12px; padding: 8px 12px; }
QPushButton:hover { background: #3a2f5a; }
QPushButton#AccentButton { background: #8b5cf6; border: 1px solid #a78bfa; color: #ffffff; font-weight: 700; }
QPushButton#DangerButton { background: #4e1f47; border: 1px solid #8d3b7d; }
QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTextBrowser { background: #141424; color: #f8f3ff; border: 1px solid #5a4c89; border-radius: 12px; padding: 8px; }
QListWidget::item:selected { background: #352a52; border: 1px solid #a78bfa; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #141424; width: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:vertical { background: #6f5db7; min-height: 30px; border-radius: 6px; }
QDialog { background: #11111c; }
QProgressBar { border: 1px solid #5a4c89; border-radius: 10px; background: #141424; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #a78bfa; border-radius: 8px; }
""",
    "Arctic": """
QWidget { background: #eef7fb; color: #18303c; font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; }
QMainWindow { background: #eef7fb; }
QLabel { background: transparent; }
QFrame#Sidebar, QFrame#HeaderBar, QFrame#ComposerFrame, QFrame#ChatSurface { background: #ffffff; border: 1px solid #cfe3ee; border-radius: 16px; }
QLabel#TitleLabel { font-size: 16pt; font-weight: 700; color: #102a43; }
QLabel#SubtleLabel { color: #557a95; }
QPushButton { background: #deeff7; color: #12344d; border: 1px solid #b6d7e7; border-radius: 12px; padding: 8px 12px; }
QPushButton:hover { background: #d2e8f4; }
QPushButton#AccentButton { background: #3b82f6; border: 1px solid #60a5fa; color: #ffffff; font-weight: 700; }
QPushButton#DangerButton { background: #ffe5e5; border: 1px solid #ffc8c8; }
QComboBox, QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTextBrowser { background: #ffffff; color: #0f2940; border: 1px solid #c7dcea; border-radius: 12px; padding: 8px; }
QListWidget::item:selected { background: #dff3ff; border: 1px solid #7dd3fc; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #edf7fc; width: 16px; margin: 2px; border-radius: 6px; }
QScrollBar::handle:vertical { background: #b6d7e7; min-height: 30px; border-radius: 6px; }
QDialog { background: #eef7fb; }
QProgressBar { border: 1px solid #c7dcea; border-radius: 10px; background: #ffffff; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #60a5fa; border-radius: 8px; }
""",
}
