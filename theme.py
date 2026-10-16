"""
Dark "studio" theme for the PyQt6 interface (Fusion style + palette + one QSS).

Call apply_theme(app) once, right after creating the QApplication. The small
icons used by the stylesheet (combo arrow, check mark) are drawn at startup and
saved in the temp folder, because QSS can only reference images from files.
"""

import tempfile
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPixmap, QPolygonF

# Colors (also used by widgets.py for custom painting).
BG = "#0a0d15"        # window background
PANEL = "#10141f"     # sidebar
CARD = "#141927"      # cards
FIELD = "#171c2b"     # inputs, combos
BORDER = "#262e42"
TEXT = "#e6e9f2"
MUTED = "#8b93a7"
ACCENT = "#2f7bff"
ACCENT2 = "#9b5cf6"
DANGER = "#ff6b6b"
WARN = "#e0a050"


def _make_icons():
    """Draw the arrow / check icons and return their file paths (forward slashes)."""
    folder = Path(tempfile.gettempdir()) / "ai_upscale_studio_icons"
    folder.mkdir(exist_ok=True)

    def draw(name, color, points):
        pm = QPixmap(12, 12)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color))
        pen.setWidthF(1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))
        p.end()
        path = folder / name
        pm.save(str(path))
        return path.as_posix()

    arrow = draw("arrow_down.png", MUTED, [(2.5, 4.5), (6, 8), (9.5, 4.5)])
    check = draw("check.png", "#ffffff", [(2.8, 6.3), (5.2, 8.7), (9.2, 3.6)])
    return arrow, check


_QSS = """
/* ---------- top bar ---------- */
QFrame#topbar { background: #0d111b; border-bottom: 1px solid #1c2232; }
QLabel#appTitle { font-size: 14px; font-weight: 700; color: @TEXT@; }
QLabel#logo { border-radius: 7px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 @ACCENT@, stop:1 @ACCENT2@); }
QPushButton#navBtn { background: transparent; border: none; border-bottom: 2px solid transparent;
    border-radius: 0; padding: 14px 16px; color: @MUTED@; font-weight: 600; }
QPushButton#navBtn:hover { color: @TEXT@; }
QPushButton#navBtn:checked { color: #ffffff; border-bottom: 2px solid @ACCENT@; }

/* ---------- sidebar ---------- */
QFrame#sidebar { background: @PANEL@; border-left: 1px solid #1c2232; }
QLabel#sidebarTitle { padding: 14px 16px; font-weight: 700; font-size: 13px;
    border-bottom: 1px solid #1c2232; background: transparent; }
QFrame#sidebarBottom { background: @PANEL@; border-top: 1px solid #1c2232; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QWidget#sidebarBody { background: transparent; }

QLabel { background: transparent; }
QLabel#fieldLabel { color: @MUTED@; font-size: 12px; padding-top: 6px; }
QLabel#sectionTitle { color: #aab2c5; font-size: 11px; font-weight: 700; padding-top: 12px; }
QLabel#hint { color: #6c748a; font-size: 11px; }
QLabel#warn { color: @WARN@; font-size: 11px; }
QLabel#error { color: @DANGER@; font-size: 12px; }
QLabel#valueLabel { color: #cfd5e4; font-size: 12px; }
QLabel#fileName { font-weight: 600; }
QLabel#info { color: #aab2c5; font-size: 12px; }
QLabel#status { color: @MUTED@; font-size: 12px; }
QLabel#thumb { background: #0d111b; border: 1px solid @BORDER@; border-radius: 8px; color: #4b5266; }
QLabel#bold { font-weight: 700; }

QFrame#card { background: @CARD@; border: 1px solid #1f2637; border-radius: 10px; }
QFrame#pill { background: @FIELD@; border: 1px solid @BORDER@; border-radius: 8px; }

/* ---------- inputs ---------- */
QComboBox, QLineEdit { background: @FIELD@; border: 1px solid @BORDER@; border-radius: 8px;
    padding: 7px 10px; color: @TEXT@; selection-background-color: @ACCENT@; }
QComboBox:hover, QLineEdit:hover { border-color: #34405c; }
QComboBox:focus, QLineEdit:focus { border-color: @ACCENT@; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow { image: url(@ARROW@); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: @FIELD@; border: 1px solid @BORDER@; outline: 0;
    padding: 4px; selection-background-color: #22304f; selection-color: #ffffff; }

QPushButton { background: #1a2030; border: 1px solid @BORDER@; border-radius: 8px;
    padding: 8px 14px; color: @TEXT@; }
QPushButton:hover { background: #20283b; border-color: #34405c; }
QPushButton:pressed { background: #161c2b; }
QPushButton:disabled { color: #566079; background: #141927; border-color: #1f2637; }
QPushButton#iconBtn { padding: 7px 0; min-width: 36px; max-width: 36px; }
QPushButton#primary { border: none; color: #ffffff; font-weight: 700; padding: 12px 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f80ff, stop:1 @ACCENT2@); }
QPushButton#primary:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 #4a92ff, stop:1 #ab75f8); }
QPushButton#primary:disabled { background: #232a3b; color: #6c748a; }

QFrame#segmented { background: @FIELD@; border: 1px solid @BORDER@; border-radius: 8px; }
QPushButton#segBtn { background: transparent; border: none; border-radius: 6px;
    padding: 7px 10px; color: #aab2c5; }
QPushButton#segBtn:hover:!checked { background: #1e2536; }
QPushButton#segBtn:checked { background: #1f6bff; color: #ffffff; font-weight: 700; }

QSlider::groove:horizontal { height: 4px; background: @BORDER@; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #3b82f6; border-radius: 2px; }
QSlider::handle:horizontal { background: #3b82f6; border: 2px solid #8fb6ff;
    width: 10px; height: 10px; margin: -6px 0; border-radius: 7px; }
QSlider::handle:horizontal:hover { background: #5b9bff; }

QProgressBar { background: #1a2030; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }
QProgressBar::chunk { border-radius: 3px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f80ff, stop:1 @ACCENT2@); }

QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #34405c;
    border-radius: 4px; background: @FIELD@; }
QCheckBox::indicator:checked { background: @ACCENT@; border-color: @ACCENT@; image: url(@CHECK@); }

QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #2a3247; border-radius: 3px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3a4565; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QToolTip { background: #1a2030; color: @TEXT@; border: 1px solid @BORDER@; padding: 4px; }
"""


def apply_theme(app):
    """Apply the dark Fusion palette, the default font and the stylesheet to `app`."""
    app.setStyle("Fusion")

    font = QFont()
    font.setFamilies(["Inter", "Segoe UI", "Noto Sans", "Helvetica Neue", "Arial"])
    font.setPointSize(10)
    app.setFont(font)

    pal = QPalette()
    roles = {
        QPalette.ColorRole.Window: BG,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: FIELD,
        QPalette.ColorRole.AlternateBase: CARD,
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: "#1a2030",
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.ToolTipBase: "#1a2030",
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#5f6880",
        QPalette.ColorRole.Link: "#6ea4ff",
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor("#566079"))
    app.setPalette(pal)

    arrow, check = _make_icons()
    qss = _QSS
    for token, value in {"@TEXT@": TEXT, "@MUTED@": MUTED, "@ACCENT@": ACCENT,
                         "@ACCENT2@": ACCENT2, "@PANEL@": PANEL, "@CARD@": CARD,
                         "@FIELD@": FIELD, "@BORDER@": BORDER, "@DANGER@": DANGER,
                         "@WARN@": WARN, "@ARROW@": arrow, "@CHECK@": check}.items():
        qss = qss.replace(token, value)
    app.setStyleSheet(qss)
