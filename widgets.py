"""
Reusable PyQt6 building blocks shared by gui.py and gui_wallpaper.py.

  Translatable      mixin: _tx(widget, key) keeps a widget's text in the current language.
  SignalQueue       thread-safe replacement of queue.Queue: put((kind, value)) can be
                    called from ANY thread and is delivered to the UI thread as a signal.
  CompareView       image canvas with a draggable before / after divider.
  SegmentedControl  "PNG | JPG | WebP" style button group.
  SliderRow         labelled slider with its value on the right.
  make_sidebar      right-hand panel (scrolling body + pinned bottom area).
  KeyCombo          drop-down whose items have an internal key (English, stable) and a
                    displayed label (translated); key() / set_key() / retranslate().
  ask_open_image / ask_save_path   file dialogs.
"""

from pathlib import Path

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF)
from PyQt6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from config import OUTPUT_FORMATS, SAVE_DIALOG_LABELS
from i18n import tr, tr_name


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

class SignalQueue(QObject):
    """Drop-in for queue.Queue on the producer side: put((kind, value)).

    Worker threads (engine, monitor...) call put(); Qt delivers the `message`
    signal in the thread that owns this object (the UI thread), so slots
    connected to it may touch widgets safely.
    """

    message = pyqtSignal(str, object)

    def put(self, item):
        kind, value = item
        self.message.emit(kind, value)


def pil_to_pixmap(img):
    """Convert a PIL image to a QPixmap (data is copied)."""
    img = img.convert("RGBA")
    w, h = img.size
    qimg = QImage(img.tobytes("raw", "RGBA"), w, h, 4 * w, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


class Translatable:
    """Mixin for tabs / windows whose texts follow the interface language.

    Register a widget once with `_tx(widget, key)`: it gets tr(key) now, and again every
    time retranslate_texts() is called after a language change. Typical use:

        body.addWidget(self._tx(field_label(""), "width"))

    `attr` is the name of the setter to call ("setText" by default, e.g. "setToolTip",
    "setPlaceholderText" or SliderRow's "set_label"); `upper=True` upper-cases the text
    (section titles); extra keyword arguments are passed to tr() as format values.
    """

    def _tx(self, widget, key, attr="setText", upper=False, **values):
        if not hasattr(self, "_tx_items"):
            self._tx_items = []
        item = (widget, attr, key, upper, values)
        self._tx_items.append(item)
        self._apply_tx(item)
        return widget

    @staticmethod
    def _apply_tx(item):
        widget, attr, key, upper, values = item
        text = tr(key, **values)
        getattr(widget, attr)(text.upper() if upper else text)

    def retranslate_texts(self):
        for item in getattr(self, "_tx_items", ()):
            self._apply_tx(item)


class NoWheelCombo(QComboBox):
    """Combo box that ignores the mouse wheel, so scrolling the sidebar never changes it."""

    def wheelEvent(self, event):
        event.ignore()


class NoWheelSlider(QSlider):
    def wheelEvent(self, event):
        event.ignore()


class KeyCombo(NoWheelCombo):
    """Combo box whose items are (key, label) pairs.

    The key is the stable internal value (the English name used in config.py, e.g. a
    MODELS or PRESETS key); the label is what the user sees and changes with the
    language. Read the selection with key(), never with currentText().
    """

    def __init__(self, keys=(), label=tr_name):
        super().__init__()
        self._label = label
        # Never size the box from its longest item: a long label (e.g. the GPU name) would
        # make the whole sidebar wider than its scroll area and cut the right side off.
        # Long texts are elided in the box; the full text is shown as a tooltip.
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)
        self.currentIndexChanged.connect(lambda _i: self._sync_tip())
        self.set_keys(keys)

    def _sync_tip(self):
        self.setToolTip(self.currentText())

    def set_keys(self, keys):
        """Replace all items (signals blocked, previous blocking state restored)."""
        was_blocked = self.blockSignals(True)
        self.clear()
        for k in keys:
            self.addItem(self._label(k), k)
        self.blockSignals(was_blocked)
        self._sync_tip()

    def key(self):
        return self.currentData()

    def set_key(self, key):
        i = self.findData(key)
        if i >= 0:
            self.setCurrentIndex(i)

    def retranslate(self):
        """Refresh the displayed labels after a language change (selection is kept)."""
        for i in range(self.count()):
            self.setItemText(i, self._label(self.itemData(i)))
        self._sync_tip()


def make_combo(items=()):
    """KeyCombo showing the translated name of each item (see i18n.tr_name)."""
    return KeyCombo(list(items))


def _label(text, name, wrap=False):
    lab = QLabel(text)
    lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def field_label(text):
    return _label(text, "fieldLabel")


def section_title(text):
    return _label(text.upper(), "sectionTitle")


def hint_label(text="", wrap=True):
    return _label(text, "hint", wrap)


def make_card(layout_cls=QVBoxLayout, margins=(12, 10, 12, 10), spacing=8):
    """Rounded card; returns (frame, its layout)."""
    frame = QFrame()
    frame.setObjectName("card")
    lay = layout_cls(frame)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    return frame, lay


def make_sidebar(title, width=372):
    """Build the right-hand panel.

    Returns (frame, body_layout, bottom_layout): add the settings to body_layout
    (it scrolls) and the action buttons / progress / status to bottom_layout
    (always visible).
    """
    frame = QFrame()
    frame.setObjectName("sidebar")
    frame.setFixedWidth(width)
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    outer.addWidget(_label(title, "sidebarTitle"))

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    inner = QWidget()
    inner.setObjectName("sidebarBody")
    body = QVBoxLayout(inner)
    body.setContentsMargins(16, 8, 16, 16)
    body.setSpacing(6)
    scroll.setWidget(inner)
    outer.addWidget(scroll, 1)

    bottom_frame = QFrame()
    bottom_frame.setObjectName("sidebarBottom")
    bottom = QVBoxLayout(bottom_frame)
    bottom.setContentsMargins(16, 12, 16, 14)
    bottom.setSpacing(8)
    outer.addWidget(bottom_frame)
    return frame, body, bottom


# --------------------------------------------------------------------------- #
# Segmented control
# --------------------------------------------------------------------------- #

class SegmentedControl(QFrame):
    """Exclusive button group. `items` is a list of (key, label); value() returns the key.

    valueChanged(key) is emitted on user clicks only (not on setValue / clear).
    """

    valueChanged = pyqtSignal(str)

    def __init__(self, items, value=None, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        for key, label in items:
            btn = QPushButton(label)
            btn.setObjectName("segBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, k=key: self.valueChanged.emit(k))
            self._group.addButton(btn)
            self._buttons[key] = btn
            lay.addWidget(btn, 1)
        if value is not None:
            self.setValue(value)

    def value(self):
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return None

    def setValue(self, key):
        btn = self._buttons.get(key)
        if btn is not None:
            btn.setChecked(True)

    def clear(self):
        """Uncheck everything (an exclusive group refuses it unless we lift the rule)."""
        self._group.setExclusive(False)
        for btn in self._buttons.values():
            btn.setChecked(False)
        self._group.setExclusive(True)


# --------------------------------------------------------------------------- #
# Slider row
# --------------------------------------------------------------------------- #

class SliderRow(QWidget):
    """Label + current value on one line, slider below. Works with float steps."""

    valueChanged = pyqtSignal(float)

    def __init__(self, text, lo, hi, value, step=1.0, fmt="{:.0f}", parent=None):
        super().__init__(parent)
        self._step, self._fmt = step, fmt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self._lab = field_label(text)
        top.addWidget(self._lab)
        top.addStretch(1)
        self._val = _label(fmt.format(value), "valueLabel")
        top.addWidget(self._val)
        lay.addLayout(top)
        self._slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(round(lo / step), round(hi / step))
        self._slider.setValue(round(value / step))
        self._slider.valueChanged.connect(self._changed)
        lay.addWidget(self._slider)

    def _changed(self, i):
        v = i * self._step
        self._val.setText(self._fmt.format(v))
        self.valueChanged.emit(v)

    def set_label(self, text):
        self._lab.setText(text)

    def value(self):
        return self._slider.value() * self._step

    def setValue(self, v):
        self._slider.setValue(round(v / self._step))


# --------------------------------------------------------------------------- #
# Before / after canvas
# --------------------------------------------------------------------------- #

def _fit_rect(w, h, area):
    """Largest rectangle of ratio w:h centered in `area`."""
    s = min(area.width() / w, area.height() / h)
    nw, nh = w * s, h * s
    return QRectF(area.center().x() - nw / 2, area.center().y() - nh / 2, nw, nh)


def _draw_cover(p, pix, rect):
    """Draw `pix` so it covers `rect` (center-cropped, like the "fill" mode)."""
    pw, ph = pix.width(), pix.height()
    s = max(rect.width() / pw, rect.height() / ph)
    sw, sh = rect.width() / s, rect.height() / s
    p.drawPixmap(rect, pix, QRectF((pw - sw) / 2, (ph - sh) / 2, sw, sh))


def _draw_contain(p, pix, rect):
    """Draw `pix` inside `rect` on black (like the "fit" mode)."""
    p.fillRect(rect, QColor(0, 0, 0))
    p.drawPixmap(_fit_rect(pix.width(), pix.height(), rect), pix, QRectF(pix.rect()))


class CompareView(QWidget):
    """Image canvas. With only a "before" image it is a plain preview; once a result is
    set it becomes a before / after view with a draggable divider.

    Also accepts a file dropped on it (fileDropped) and a click on the empty canvas
    (emptyClicked).
    """

    fileDropped = pyqtSignal(str)
    emptyClicked = pyqtSignal()
    # Rectangle drawn in "select" mode, in percent of the displayed image: x0, y0, x1, y1.
    zoneSelected = pyqtSignal(float, float, float, float)

    def __init__(self, placeholder=None, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setMinimumSize(460, 340)
        self._placeholder = placeholder  # None = the default "drop an image" text
        self._before = self._after = None
        self._before_label = self._after_label = ""
        self._mode = "fill"
        self._split = 0.5
        self._dragging = False
        self._select_mode = False   # True: dragging draws a rectangle instead of moving the divider
        self._sel_start = self._sel_cur = None  # corners of the rectangle being drawn

    # ---- content ----
    def set_placeholder(self, text):
        """Change the text shown while the canvas is empty (None = default)."""
        self._placeholder = text
        self.update()

    def set_select_mode(self, on):
        """Turn the rectangle selection on/off (the zone is reported through zoneSelected)."""
        self._select_mode = on
        self._sel_start = self._sel_cur = None
        if on:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()
        self.update()

    def set_before(self, pix, label=""):
        self._before, self._before_label = pix, label
        self.update()

    def set_after(self, pix, label="", mode="fill"):
        self._after, self._after_label, self._mode = pix, label, mode
        self._split = 0.5
        self.update()

    def clear_after(self):
        if self._after is not None:
            self._after = None
            self.update()

    def clear(self):
        self._before = self._after = None
        self.update()

    def has_after(self):
        return self._after is not None

    # ---- geometry ----
    def _image_rect(self):
        area = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        ref = self._after or self._before
        if ref is None:
            return area
        return _fit_rect(ref.width(), ref.height(), area)

    # ---- painting ----
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        panel = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#1c2232")))
        p.setBrush(QColor("#0d111b"))
        p.drawRoundedRect(panel, 14, 14)

        if self._before is None:
            p.setPen(QColor("#5f6880"))
            f = QFont(self.font())
            f.setPointSizeF(12)
            p.setFont(f)
            p.drawText(panel, Qt.AlignmentFlag.AlignCenter,
                       self._placeholder or tr("drop_placeholder"))
            return

        rect = self._image_rect()
        clip = QPainterPath()
        clip.addRoundedRect(rect, 10, 10)
        p.setClipPath(clip)

        if self._after is None:
            p.drawPixmap(rect, self._before, QRectF(self._before.rect()))
            p.setClipping(False)
            self._badge(p, rect.left() + 12, rect.top() + 12, tr("badge_original"),
                        self._before_label)
            self._draw_selection(p)
            return

        p.drawPixmap(rect, self._after, QRectF(self._after.rect()))
        split_x = rect.left() + self._split * rect.width()
        p.save()
        p.setClipRect(QRectF(rect.left(), rect.top(), split_x - rect.left(), rect.height()),
                      Qt.ClipOperation.IntersectClip)
        if self._mode == "fit":
            _draw_contain(p, self._before, rect)
        else:
            _draw_cover(p, self._before, rect)
        p.restore()
        p.setClipping(False)

        # Divider line and its round handle with two arrows.
        p.setPen(QPen(QColor(255, 255, 255, 235), 2))
        p.drawLine(QPointF(split_x, rect.top()), QPointF(split_x, rect.bottom()))
        cy = rect.center().y()
        p.setPen(QPen(QColor(255, 255, 255, 235), 2))
        p.setBrush(QColor(15, 20, 32, 240))
        p.drawEllipse(QPointF(split_x, cy), 19, 19)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(QPolygonF([QPointF(split_x - 10, cy), QPointF(split_x - 4, cy - 5),
                                 QPointF(split_x - 4, cy + 5)]))
        p.drawPolygon(QPolygonF([QPointF(split_x + 10, cy), QPointF(split_x + 4, cy - 5),
                                 QPointF(split_x + 4, cy + 5)]))

        self._badge(p, rect.left() + 12, rect.top() + 12, tr("badge_original"),
                    self._before_label)
        self._badge(p, rect.right() - 12, rect.top() + 12, tr("badge_after"), self._after_label,
                    right=True)

    def _draw_selection(self, p):
        """Dashed rectangle of the zone being drawn (select mode)."""
        if self._sel_start is None:
            return
        rect = QRectF(self._sel_start, self._sel_cur).normalized()
        p.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine))
        p.setBrush(QColor(255, 0, 0, 70))
        p.drawRect(rect)

    def _clamp_to_image(self, pos):
        """`pos` moved inside the image rectangle (the zone cannot leave the picture)."""
        r = self._image_rect()
        return QPointF(min(max(pos.x(), r.left()), r.right()),
                       min(max(pos.y(), r.top()), r.bottom()))

    def _badge(self, p, x, y, title, sub, right=False):
        """Small translucent label (two lines) anchored at (x, y)."""
        f1 = QFont(self.font())
        f1.setBold(True)
        f1.setPointSizeF(9.5)
        f2 = QFont(self.font())
        f2.setPointSizeF(9)
        m1, m2 = QFontMetrics(f1), QFontMetrics(f2)
        w = max(m1.horizontalAdvance(title), m2.horizontalAdvance(sub)) + 24
        h = m1.height() + m2.height() + 16
        rect = QRectF(x - w if right else x, y, w, h)
        p.setPen(QPen(QColor(255, 255, 255, 40)))
        p.setBrush(QColor(10, 13, 21, 205))
        p.drawRoundedRect(rect, 9, 9)
        align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        p.setFont(f1)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(rect.x() + 12, rect.y() + 7, w - 24, m1.height()), align, title)
        p.setFont(f2)
        p.setPen(QColor("#aab2c5"))
        p.drawText(QRectF(rect.x() + 12, rect.y() + 7 + m1.height(), w - 24, m2.height()), align, sub)

    # ---- interaction ----
    def _set_split_from(self, x):
        rect = self._image_rect()
        self._split = min(1.0, max(0.0, (x - rect.left()) / rect.width()))
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._select_mode and self._before is not None:
            if self._image_rect().contains(event.position()):
                self._sel_start = self._sel_cur = event.position()
                self.update()
            return
        if self._before is None:
            self.emptyClicked.emit()
        elif self._after is not None and self._image_rect().contains(event.position()):
            self._dragging = True
            self._set_split_from(event.position().x())

    def mouseMoveEvent(self, event):
        if self._sel_start is not None:
            self._sel_cur = self._clamp_to_image(event.position())
            self.update()
        elif self._select_mode and self._before is not None:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self._dragging:
            self._set_split_from(event.position().x())
        elif self._after is not None and self._image_rect().contains(event.position()):
            self.setCursor(Qt.CursorShape.SplitHCursor)
        elif self._before is None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, _event):
        if self._sel_start is not None:
            r = self._image_rect()
            a, b = self._sel_start, self._clamp_to_image(self._sel_cur)
            self._sel_start = self._sel_cur = None
            x0, x1 = sorted(((v - r.left()) / r.width() * 100) for v in (a.x(), b.x()))
            y0, y1 = sorted(((v - r.top()) / r.height() * 100) for v in (a.y(), b.y()))
            if x1 - x0 >= 1 and y1 - y0 >= 1:  # ignore a simple click
                self.zoneSelected.emit(round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))
            self.update()
            return
        self._dragging = False

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.fileDropped.emit(urls[0].toLocalFile())


# --------------------------------------------------------------------------- #
# File dialogs
# --------------------------------------------------------------------------- #

def ask_open_image(parent):
    """Return the chosen image path, or "" if the dialog was cancelled."""
    path, _ = QFileDialog.getOpenFileName(parent, tr("dlg_choose_image"), "", tr("filter_images"))
    return path


def ask_save_path(parent, fmt, initial_dir, stem):
    """"Save as" dialog preselecting the output format `fmt` (key of OUTPUT_FORMATS).

    Returns the chosen path (extension added if the user typed none), or None.
    """
    ext = OUTPUT_FORMATS[fmt]
    ordered = [fmt] + [f for f in OUTPUT_FORMATS if f != fmt]
    filters = [f"{SAVE_DIALOG_LABELS[f]} (*{OUTPUT_FORMATS[f]})" for f in ordered]
    filters.append(tr("filter_all_supported",
                      exts=" ".join(f"*{e}" for e in OUTPUT_FORMATS.values())))
    start = str(Path(initial_dir) / f"{stem}{ext}")
    path, chosen = QFileDialog.getSaveFileName(parent, tr("dlg_save_as"), start,
                                               ";;".join(filters), filters[0])
    if not path:
        return None
    p = Path(path)
    known = set(OUTPUT_FORMATS.values()) | {".jpeg"}
    if p.suffix.lower() not in known:
        # No usable extension typed: use the one of the selected filter (or the chosen format).
        sel = ext
        if chosen in filters[:len(ordered)]:
            sel = OUTPUT_FORMATS[ordered[filters.index(chosen)]]
        p = p.with_name(p.name + sel)
        if p.exists():
            answer = QMessageBox.question(parent, tr("replace_title"),
                                          tr("replace_msg", name=p.name))
            if answer != QMessageBox.StandardButton.Yes:
                return None
    return str(p)
