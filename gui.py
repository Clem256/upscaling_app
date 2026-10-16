"""
PyQt6 interface: the main window (class App), the Upscaler tab and the Monitoring tab.

Threading model: widgets are only touched from the UI thread. Worker threads (upscale,
GPU probe, monitoring) call App.q.put((kind, value)); SignalQueue turns every call into
a Qt signal that is delivered in the UI thread to App._on_message().

Upscaler flow: "Upscaler" writes a temporary PNG and shows it in the before / after view;
"Download" then saves it in the chosen format. Nothing is written to the user's disk
until that second click.

Language: every visible text goes through i18n.tr() / tr_name(). Widgets whose text never
changes by itself are registered with Translatable._tx(); the few texts that depend on
state (status line, summary, file card...) are re-rendered in retranslate(). App.set_language()
(the EN | FR switch in the top bar) calls retranslate() on every tab, no restart needed.

Message kinds: "progress", "status", "result", "done", "cancelled", "error", "saved",
"save_error" (Upscaler tab),
"metrics", "gpus", and everything starting with "w_" (Wallpaper maker tab).
"""

import shutil
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageOps
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QProgressBar, QPushButton, QStackedWidget,
                             QVBoxLayout, QWidget)

from config import (CUSTOM_PRESET, FIT_MODES, MAX_SIDE, MODELS, OUTPUT_FORMATS, PRESETS,
                    SCREEN_PRESET)
from i18n import LANGS, get_lang, set_lang, tr, tr_name
from control import Cancelled, Control
from devices import build_devices, nvidia_smi_name
from engine import detect_gpus, download_engine, find_engine
from export import export_image
from gui_wallpaper import WallpaperTab
from upscale import needed_factor, plan_passes, upscale_image
from widgets import (CompareView, SegmentedControl, SignalQueue, Translatable, ask_open_image,
                     ask_save_path, field_label, hint_label, make_card, make_combo, make_sidebar,
                     pil_to_pixmap, section_title)

try:
    from monitor import HAS_PSUTIL, monitor_loop
except ImportError:  # psutil not installed: monitor.py imports it unconditionally
    HAS_PSUTIL, monitor_loop = False, None

# Output format key (see config.OUTPUT_FORMATS) -> label of the button.
FORMAT_LABELS = {"PNG": "PNG", "JPG": "JPG", "WEBP": "WebP"}


def result_preview(path):
    """Read a finished image and return (small PIL thumbnail, real (w, h)).

    Runs in a worker thread: opening a very large PNG can take a second or two.
    """
    with Image.open(path) as im:
        size = im.size
        thumb = im.convert("RGB")
    thumb.thumbnail((1600, 1600))
    return thumb, size


# --------------------------------------------------------------------------- #
# Upscaler tab
# --------------------------------------------------------------------------- #

class UpscalerTab(QWidget, Translatable):
    """Canvas on the left, settings on the right (source, scale, resolution, model...)."""

    modelChanged = pyqtSignal(str)   # key of MODELS, for the Monitoring tab

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.src_path = None     # Path of the chosen source image
        self.src_size = None     # (width, height) of the source after EXIF rotation
        self.job_mode = "fill"   # fit mode of the running / last job
        self.job_target = None   # (width, height) of the running / last job
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="upscale_preview_"))
        self.result_path = None  # temporary PNG of the last finished job (None = nothing to save)
        self._status_src = None  # (key, values) of the status line, None if it is a raw text
        self._build()

    # ---- UI construction ----
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QVBoxLayout()
        left.setContentsMargins(16, 16, 16, 16)
        self.view = CompareView()
        self.view.fileDropped.connect(self.load_file)
        self.view.emptyClicked.connect(self.choose_file)
        left.addWidget(self.view)
        root.addLayout(left, 1)

        side, body, bottom = make_sidebar("")
        self._tx(side.findChild(QLabel, "sidebarTitle"), "nav_upscaler")
        root.addWidget(side)

        # Source image
        body.addWidget(self._tx(field_label(""), "imported_image"))
        card, row = make_card(QHBoxLayout)
        self.thumb = QLabel("—")
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(56, 56)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.file_name = QLabel(tr("no_image"))
        self.file_name.setObjectName("fileName")
        self.file_meta = hint_label("")
        col.addWidget(self.file_name)
        col.addWidget(self.file_meta)
        row.addLayout(col, 1)
        self.pick_btn = QPushButton(tr("choose"))
        self.pick_btn.clicked.connect(self.choose_file)
        row.addWidget(self.pick_btn)
        body.addWidget(card)

        # Quick scale (sets the target to source size x factor)
        body.addWidget(self._tx(field_label(""), "quick_scale"))
        self.scale_seg = SegmentedControl([("2", "2×"), ("4", "4×"), ("8", "8×")])
        self.scale_seg.valueChanged.connect(self._on_scale)
        body.addWidget(self.scale_seg)
        pill = QFrame()
        pill.setObjectName("pill")
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(12, 8, 12, 8)
        pl.addWidget(self._tx(QLabel(), "custom"))
        pl.addStretch(1)
        self.custom_val = QLabel("—")
        self.custom_val.setObjectName("valueLabel")
        pl.addWidget(self.custom_val)
        body.addWidget(pill)

        # Target resolution
        body.addWidget(self._tx(field_label(""), "target_res"))
        self.preset_box = make_combo([SCREEN_PRESET] + list(PRESETS))
        self.preset_box.set_key("2K / QHD - 2560x1440")
        self.preset_box.activated.connect(lambda _i: self._on_preset())
        body.addWidget(self.preset_box)
        size_row = QHBoxLayout()
        size_row.addWidget(self._tx(field_label(""), "width"))
        self.w_edit = QLineEdit("2560")
        self.w_edit.setMaximumWidth(80)
        size_row.addWidget(self.w_edit)
        size_row.addSpacing(8)
        size_row.addWidget(self._tx(field_label(""), "height"))
        self.h_edit = QLineEdit("1440")
        self.h_edit.setMaximumWidth(80)
        size_row.addWidget(self.h_edit)
        size_row.addStretch(1)
        body.addLayout(size_row)

        # AI model
        body.addWidget(self._tx(field_label(""), "ai_model"))
        self.model_box = make_combo(MODELS)
        self.model_box.activated.connect(lambda _i: self._on_model_change())
        body.addWidget(self.model_box)
        self.model_hint = hint_label("")
        body.addWidget(self.model_hint)

        # Device
        body.addWidget(self._tx(field_label(""), "device"))
        dev_row = QHBoxLayout()
        self.dev_box = make_combo(self.app.devices)
        dev_row.addWidget(self.dev_box, 1)
        refresh = QPushButton("↻")
        refresh.setObjectName("iconBtn")
        self._tx(refresh, "refresh_gpu", attr="setToolTip")
        refresh.clicked.connect(self.app.refresh_gpus)
        dev_row.addWidget(refresh)
        body.addLayout(dev_row)

        # Ratio handling
        body.addWidget(self._tx(field_label(""), "aspect_ratio"))
        self.fit_box = make_combo(FIT_MODES)
        self.fit_box.activated.connect(lambda _i: self._update_info())
        body.addWidget(self.fit_box)

        # Output format
        body.addWidget(self._tx(field_label(""), "out_format"))
        self.fmt_seg = SegmentedControl([(k, FORMAT_LABELS[k]) for k in OUTPUT_FORMATS], "PNG")
        body.addWidget(self.fmt_seg)
        body.addStretch(1)

        # Pinned bottom area
        self.info_label = QLabel("")
        self.info_label.setObjectName("info")
        self.info_label.setWordWrap(True)
        bottom.addWidget(self.info_label)
        btns = QHBoxLayout()
        self.go_btn = self._tx(QPushButton(), "nav_upscaler")
        self.go_btn.setObjectName("primary")
        self.go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.go_btn.clicked.connect(self.start)
        btns.addWidget(self.go_btn, 1)
        self.save_btn = self._tx(QPushButton(), "download")
        self.save_btn.setEnabled(False)
        self._tx(self.save_btn, "save_tip_up", attr="setToolTip")
        self.save_btn.clicked.connect(self.download)
        btns.addWidget(self.save_btn, 1)
        self.cancel_btn = self._tx(QPushButton(), "cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        btns.addWidget(self.cancel_btn)
        bottom.addLayout(btns)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        bottom.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status)
        self.say("ready")

        self.w_edit.textChanged.connect(lambda _t: self._on_size_edit())
        self.h_edit.textChanged.connect(lambda _t: self._on_size_edit())
        self._on_model_change()

    # ---- language ----
    def retranslate(self):
        """Re-render every text after a language change (devices are refilled by App)."""
        self.retranslate_texts()
        for box in (self.preset_box, self.model_box, self.fit_box):
            box.retranslate()
        self.model_hint.setText(tr_name(MODELS[self.model_box.key()][2]))
        self._render_source_texts()
        self._render_info()
        self.view.update()  # badges and placeholder are painted with tr()
        if self._status_src is not None:
            self.say(self._status_src[0], **self._status_src[1])

    def _render_source_texts(self):
        """File card: name and "Choose…" / "Replace" button (they depend on the state)."""
        self.file_name.setText(self.src_path.name if self.src_path else tr("no_image"))
        self.pick_btn.setText(tr("replace") if self.src_path else tr("choose"))

    # ---- helpers used by App ----
    def say(self, key, **values):
        """Show a translated status message (it is re-translated on language change)."""
        self._status_src = (key, values)
        self.status.setText(tr(key, **values))

    def set_status(self, text):
        """Show a raw text (already translated by whoever produced it)."""
        self._status_src = None
        self.status.setText(text)

    def device(self):
        """Identifier ("auto", "cpu" or a GPU index) of the selected device."""
        return self.app.devices.get(self.dev_box.currentText(), "auto")

    def set_devices(self, keep):
        """Refill the device dropdown from app.devices, selecting identifier `keep` if it exists."""
        self.dev_box.blockSignals(True)
        self.dev_box.set_keys(list(self.app.devices))
        for i, ident in enumerate(self.app.devices.values()):
            if ident == keep:
                self.dev_box.setCurrentIndex(i)
                break
        else:
            self.dev_box.setCurrentIndex(0)
        self.dev_box.blockSignals(False)

    # ---- UI events ----
    def _on_model_change(self):
        key = self.model_box.key()
        self.model_hint.setText(tr_name(MODELS[key][2]))
        self.modelChanged.emit(key)
        self._update_info()

    def _set_target(self, w, h):
        """Write the width/height fields without triggering twice the refresh."""
        for edit, v in ((self.w_edit, w), (self.h_edit, h)):
            edit.blockSignals(True)
            edit.setText(str(v))
            edit.blockSignals(False)
        self._on_size_edit()

    def _on_preset(self):
        """Fill width/height from the selected preset (CUSTOM_PRESET leaves them untouched)."""
        name = self.preset_box.key()
        if name == SCREEN_PRESET:
            screen = self.screen()
            size = screen.size() * screen.devicePixelRatio()
            self._set_target(round(size.width()), round(size.height()))
        elif PRESETS.get(name):
            self._set_target(*PRESETS[name])

    def _on_scale(self, key):
        """Quick scale button: target = source size x factor."""
        if not self.src_size:
            self.scale_seg.clear()
            self.say("pick_image_first")
            return
        f = int(key)
        self.preset_box.set_key(CUSTOM_PRESET)
        self._set_target(self.src_size[0] * f, self.src_size[1] * f)

    def _on_size_edit(self):
        t = self._target()
        self.custom_val.setText(f"{t[0]} × {t[1]}" if t else "—")
        self.scale_seg.clear()
        if t and self.src_size:
            for f in (2, 4, 8):
                if t == (self.src_size[0] * f, self.src_size[1] * f):
                    self.scale_seg.setValue(str(f))
        self._update_info()

    def _target(self):
        """Return the target (width, height) from the fields, or None if invalid.

        Valid means two integers between 16 and MAX_SIDE.
        """
        try:
            tw, th = int(self.w_edit.text()), int(self.h_edit.text())
        except ValueError:
            return None
        if not (16 <= tw <= MAX_SIDE and 16 <= th <= MAX_SIDE):
            return None
        return tw, th

    def _invalidate(self):
        """Forget the previewed result: any setting that changes it makes it stale."""
        self.result_path = None
        self.view.clear_after()
        self.save_btn.setEnabled(False)

    def _update_info(self):
        """Refresh the summary: size change, enlargement factor, planned AI passes.

        Called whenever the source, size, model or ratio changes, so it also drops a
        result that no longer matches the settings.
        """
        self._invalidate()
        self._render_info()

    def _render_info(self):
        """Write the summary text (also called alone after a language change)."""
        if not self.src_size:
            self.info_label.setText("")
            return
        t = self._target()
        if not t:
            self.info_label.setText(tr("size_range", max=MAX_SIDE))
            return
        mode = FIT_MODES[self.fit_box.key()]
        f = needed_factor(*self.src_size, *t, mode)
        txt = tr("enlarge", sw=self.src_size[0], sh=self.src_size[1], tw=t[0], th=t[1], f=f)
        if f <= 1.0:
            txt += "\n" + tr("no_ai_needed")
        else:
            passes = plan_passes(f, MODELS[self.model_box.key()][1])
            txt += "\n" + tr("ai_passes") + tr("then").join(f"×{s}" for s in passes)
        self.info_label.setText(txt)

    # ---- source image ----
    def choose_file(self):
        path = ask_open_image(self)
        if path:
            self.load_file(path)

    def load_file(self, path):
        """Read the image, show it on the canvas and fill the source card."""
        try:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                size = im.size
                thumb = im.convert("RGB")
        except Exception as e:
            QMessageBox.critical(self, tr("error_title"), tr("cant_open", e=e))
            return
        self.src_path, self.src_size = Path(path), size
        thumb.thumbnail((1600, 1600))
        pix = pil_to_pixmap(thumb)
        self.view.set_before(pix, f"{size[0]}×{size[1]} px")
        self.view.clear_after()
        icon = pix.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)
        self.thumb.setPixmap(icon)
        self.file_meta.setText(f"{size[0]}×{size[1]} px")
        self._render_source_texts()
        self._on_size_edit()

    # ---- processing ----
    def start(self):
        """Validate inputs, ask where to save, then launch the worker thread."""
        if self.app.busy:
            QMessageBox.information(self, tr("busy_title"), tr("busy_msg"))
            return
        if not self.src_path:
            QMessageBox.warning(self, tr("missing_image_title"), tr("pick_image_first"))
            return
        target = self._target()
        if not target:
            QMessageBox.warning(self, tr("invalid_res_title"), tr("invalid_res_msg", max=MAX_SIDE))
            return

        # The result goes to a temporary PNG first: it is previewed, and only saved
        # when the user clicks "Download".
        dst = self.tmp_dir / "result.png"
        self.job_mode = FIT_MODES[self.fit_box.key()]
        self.job_target = target
        self._invalidate()
        self.app.ctl = ctl = Control()
        self.app.busy = True
        self.go_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.bar.setValue(0)
        self.say("upscaling")
        args = (self.src_path, dst, target, self.model_box.key(), self.device(),
                self.job_mode, ctl)
        threading.Thread(target=self._worker, args=args, daemon=True).start()

    def cancel(self):
        if self.app.busy:
            self.say("cancelling")
            self.app.ctl.cancel()

    def download(self):
        """Ask where to save, then write the previewed result there (in a worker thread)."""
        if self.result_path is None or not self.result_path.exists() or not self.job_target:
            return
        t = self.job_target
        dst = ask_save_path(self, self.fmt_seg.value() or "PNG", self.src_path.parent,
                            f"{self.src_path.stem}_{t[0]}x{t[1]}")
        if not dst:
            return
        self.save_btn.setEnabled(False)
        self.say("saving")
        put, src = self.app.q.put, self.result_path

        def run():
            try:
                export_image(src, dst)
                put(("saved", str(dst)))
            except Exception as e:
                put(("save_error", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def shutdown(self):
        """Called when the window closes: delete the temporary preview files."""
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _worker(self, src, dst, target, model_key, device, mode, ctl):
        """Thread body: install the engine if needed, upscale, report via the queue.

        Never touches widgets; it only posts messages.
        """
        put = self.app.q.put
        try:
            exe = find_engine()
            if exe is None:
                exe, digest = download_engine(ctl, lambda s: put(("status", s)),
                                              lambda p: put(("progress", p)))
                put(("status", tr("engine_installed", digest=digest[:16])))
                self.app._probe_async(exe)  # the engine is new: detect GPUs now
            upscale_image(exe, src, dst, target[0], target[1], model_key, device, mode, ctl,
                          lambda p: put(("progress", p)), lambda s: put(("status", s)))
            try:
                put(("result", result_preview(dst)))
            except Exception:
                pass  # the preview is a bonus: never fail the job because of it
            put(("done", str(dst)))
        except Cancelled:
            put(("cancelled", None))
        except Exception as e:
            put(("error", str(e)))

    def _finish(self):
        """Return the tab to its idle state after a job ends (any outcome)."""
        self.app.busy = False
        self.go_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def handle(self, kind, val):
        """Apply a message posted by the worker thread (called by App._on_message)."""
        if kind == "progress":
            self.bar.setValue(int(val))
        elif kind == "status":
            self.set_status(val)
        elif kind == "result":
            thumb, (w, h) = val
            self.view.set_after(pil_to_pixmap(thumb), f"{w}×{h} px", self.job_mode)
        elif kind == "done":
            self._finish()
            self.result_path = Path(val)
            self.save_btn.setEnabled(True)
            self.say("preview_ready")
        elif kind == "saved":
            self.save_btn.setEnabled(self.result_path is not None)
            self.say("saved_status", path=val)
            QMessageBox.information(self, tr("done_title"), tr("image_saved", path=val))
        elif kind == "save_error":
            self.save_btn.setEnabled(self.result_path is not None)
            self.say("save_failed")
            QMessageBox.critical(self, tr("error_title"), val)
        elif kind == "cancelled":
            self._finish()
            self.bar.setValue(0)
            self.say("cancelled")
        elif kind == "error":
            self._finish()
            self.say("error_status")
            QMessageBox.critical(self, tr("error_title"), val)


# --------------------------------------------------------------------------- #
# Monitoring tab
# --------------------------------------------------------------------------- #

class MonitorTab(QWidget, Translatable):
    """Active model details and live system usage."""

    def __init__(self):
        super().__init__()
        self._model_key = None      # last model shown, to re-render it after a language change
        self._has_metrics = False   # False until the first sample replaces "Detecting…"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(6)

        lay.addWidget(self._tx(section_title(""), "active_model", upper=True))
        card, cl = make_card()
        self.lbl_mod_name = QLabel("")
        self.lbl_mod_name.setObjectName("bold")
        cl.addWidget(self.lbl_mod_name)
        cl.addWidget(self._tx(QLabel(), "engine_line"))
        self.lbl_mod_desc = hint_label("")
        cl.addWidget(self.lbl_mod_desc)
        lay.addWidget(card)

        lay.addWidget(self._tx(section_title(""), "live_usage", upper=True))
        card, cl = make_card(spacing=6)
        self.cpu_bar = self.ram_bar = None
        if not HAS_PSUTIL:
            err = self._tx(QLabel(), "no_psutil")
            err.setObjectName("error")
            cl.addWidget(err)
        else:
            cl.addWidget(self._tx(field_label(""), "cpu"))
            self.cpu_bar, self.lbl_cpu = self._bar_row(cl)
            cl.addWidget(self._tx(field_label(""), "ram"))
            self.ram_bar, self.lbl_ram = self._bar_row(cl)
            cl.addWidget(self._tx(field_label(""), "gpu_label"))
            self.lbl_gpu = QLabel(tr("detecting"))
            self.lbl_gpu.setWordWrap(True)
            cl.addWidget(self.lbl_gpu)
            cl.addWidget(self._tx(field_label(""), "net_label"))
            self.lbl_net = QLabel("-")
            self.lbl_net.setObjectName("bold")
            cl.addWidget(self.lbl_net)
        lay.addWidget(card)
        lay.addStretch(1)

    @staticmethod
    def _bar_row(layout):
        """A progress bar with its text on the next line; returns (bar, label)."""
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        layout.addWidget(bar)
        lbl = QLabel("-")
        lbl.setObjectName("valueLabel")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(lbl)
        return bar, lbl

    def set_model(self, key):
        """Show the details of MODELS[key] (key = English model name)."""
        self._model_key = key
        name, scales, desc = MODELS[key]
        scales_txt = ", ".join(f"×{s}" for s in scales)
        self.lbl_mod_name.setText(tr("model_line", name=name, scales=scales_txt))
        self.lbl_mod_desc.setText(tr_name(desc))

    def retranslate(self):
        self.retranslate_texts()
        if self._model_key is not None:
            self.set_model(self._model_key)
        if self.cpu_bar is not None and not self._has_metrics:
            self.lbl_gpu.setText(tr("detecting"))

    def show_metrics(self, m):
        """Display a metrics dict (from monitor.monitor_loop)."""
        if self.cpu_bar is None:  # psutil missing: nothing to update
            return
        self._has_metrics = True
        self.cpu_bar.setValue(int(m["cpu"]))
        self.lbl_cpu.setText(f"{m['cpu']:.1f} %")
        self.ram_bar.setValue(int(m["ram_pct"]))
        self.lbl_ram.setText(m["ram_txt"])
        self.lbl_gpu.setText(m["gpu"])
        self.lbl_net.setText(m["net"])


# --------------------------------------------------------------------------- #
# Main window
# --------------------------------------------------------------------------- #

class App(QMainWindow):
    """Main window: top bar with the tabs, one page per tab.

    Attributes shared with the tabs: q (message queue), busy, ctl, devices,
    refresh_gpus(), _probe_async().
    """

    def __init__(self):
        """Create the window, start GPU detection and the monitoring thread."""
        super().__init__()
        self.setWindowTitle("AI Upscale Studio")
        self.resize(1320, 820)
        self.setMinimumSize(1020, 700)

        self.q = SignalQueue()            # worker threads -> UI thread
        self.busy = False                 # True while an upscale / wallpaper job is running
        self.ctl = Control()
        self.stop_monitor = threading.Event()
        self._gpus, self._nv_name = [], None  # last GPU detection, to rebuild labels on language change
        self.devices = build_devices([])  # {label: identifier}, refreshed after GPU detection

        self._build()
        self.q.message.connect(self._on_message)

        # If the engine is already installed, detect GPUs right away.
        exe = find_engine()
        if exe is not None:
            self.tab_up.say("detecting_gpus")
            self._probe_async(exe)

        if HAS_PSUTIL:
            threading.Thread(target=monitor_loop, args=(self.q, self.stop_monitor),
                             daemon=True).start()

    # ---- UI construction ----
    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        top = QFrame()
        top.setObjectName("topbar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(18, 0, 18, 0)
        tl.setSpacing(4)
        logo = QLabel()
        logo.setObjectName("logo")
        logo.setFixedSize(22, 22)
        tl.addWidget(logo)
        tl.addSpacing(6)
        title = QLabel("AI Upscale Studio")
        title.setObjectName("appTitle")
        tl.addWidget(title)
        tl.addSpacing(28)

        self.stack = QStackedWidget()
        self.tab_up = UpscalerTab(self)
        self.tab_wall = WallpaperTab(self)
        self.tab_mon = MonitorTab()
        self.tab_up.modelChanged.connect(self.tab_mon.set_model)
        self.tab_mon.set_model(self.tab_up.model_box.key())

        group = QButtonGroup(self)
        self._nav_btns = []
        names = ["nav_upscaler", "nav_wallpaper", "nav_monitor"]  # i18n keys
        for i, (name, page) in enumerate(zip(names, (self.tab_up, self.tab_wall, self.tab_mon))):
            btn = QPushButton(tr(name))
            self._nav_btns.append((btn, name))
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(btn, i)
            tl.addWidget(btn)
            self.stack.addWidget(page)
        group.button(0).setChecked(True)
        group.idClicked.connect(self.stack.setCurrentIndex)
        tl.addStretch(1)
        self._nav_group = group

        # Language switch: EN | FR (applies immediately and is remembered in config.json).
        self.lang_seg = SegmentedControl([(code, code.upper()) for code in LANGS], get_lang())
        self.lang_seg.setFixedWidth(96)
        self.lang_seg.valueChanged.connect(self.set_language)
        tl.addWidget(self.lang_seg)
        self._retranslate_window()

        lay.addWidget(top)
        lay.addWidget(self.stack, 1)

    # ---- language ----
    def set_language(self, code):
        """Switch the interface language live: save it, then re-render every tab."""
        if code == get_lang():
            return
        set_lang(code)
        self._retranslate_window()
        self._set_devices(self._gpus, self._nv_name)  # device labels are translated too
        self.tab_up.retranslate()
        self.tab_wall.retranslate()
        self.tab_mon.retranslate()

    def _retranslate_window(self):
        for btn, key in self._nav_btns:
            btn.setText(tr(key))
        self.lang_seg.setToolTip(tr("language"))

    # ---- GPUs ----
    def _probe_async(self, exe):
        """Detect GPUs in a background thread; the result arrives as a "gpus" message."""
        def run():
            try:
                gpus = detect_gpus(exe)
            except Exception:
                gpus = []
            self.q.put(("gpus", (gpus, nvidia_smi_name())))
        threading.Thread(target=run, daemon=True).start()

    def refresh_gpus(self):
        """Handler of the refresh buttons: re-run GPU detection if the engine is installed."""
        exe = find_engine()
        if exe is None:
            QMessageBox.information(self, tr("engine_missing_title"), tr("engine_missing_msg"))
            return
        if not self.busy:
            self.tab_up.say("detecting_gpus")
        self._probe_async(exe)

    def _set_devices(self, gpus, nv_name):
        """Rebuild both device dropdowns, keeping each current choice when it still exists."""
        keep_up, keep_wall = self.tab_up.device(), self.tab_wall.device()  # before the swap
        self.devices = build_devices(gpus, nv_name)
        self.tab_up.set_devices(keep_up)
        self.tab_wall.set_devices(keep_wall)

    # ---- messages from the worker threads ----
    def _on_message(self, kind, val):
        if kind.startswith("w_"):
            self.tab_wall.handle(kind, val)
        elif kind == "metrics":
            self.tab_mon.show_metrics(val)
        elif kind == "gpus":
            gpus, nv_name = val
            self._gpus, self._nv_name = gpus, nv_name
            self._set_devices(gpus, nv_name)
            if not self.busy:  # don't overwrite the status during a job
                if gpus:
                    self.tab_up.say("ready_gpus", n=len(gpus))
                else:
                    self.tab_up.say("ready_nogpu")
        else:
            self.tab_up.handle(kind, val)

    def closeEvent(self, event):
        """Stop the monitor thread, cancel any job, clean up, then close."""
        self.stop_monitor.set()
        self.ctl.cancel()
        self.tab_up.shutdown()
        self.tab_wall.shutdown()
        event.accept()
