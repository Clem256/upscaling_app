"""
"Wallpaper maker" tab (PyQt6): turns low-quality sources (YouTube thumbnails, small JPEGs)
into clean wallpapers. See wallpaper.py for the pipeline itself.

Same threading model as gui.py: the worker threads never touch widgets, they post
("w_...", value) messages on app.q, and App._on_message() forwards them to
WallpaperTab.handle().

Same two-step flow as the Upscaler tab: "Create wallpaper" writes a temporary PNG
shown in the before / after view; "Download" saves it in the chosen format.

The device list is shared with the Upscaler tab (same GPU detection, same
"GPU first" fallback order through engine.run_pass / devices.device_attempts).

Language: same mechanism as gui.py (i18n.tr / tr_name, Translatable._tx, retranslate()).
Choice lists (models, presets, zones, shrink factors...) use their English text as the
internal key and are read with KeyCombo.key(), so the logic never depends on the language.
"""

import shutil
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageOps
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QProgressBar, QPushButton, QVBoxLayout, QWidget)

import cleanup
from cleanup import CleanOptions, ZONE_MODES, ZONE_PRESETS
from config import (FIT_MODES, MAX_SIDE, MODELS, OUTPUT_FORMATS, PRESETS, SCREEN_PRESET)
from control import Cancelled, Control
from engine import download_engine, find_engine
from export import export_image
from i18n import tr, tr_name
from upscale import needed_factor
from wallpaper import (autocrop_bars, choose_passes, cv2, crop_to_ratio, fetch_thumbnail,
                       make_wallpaper, np, video_id)
from widgets import (CompareView, SegmentedControl, SliderRow, Translatable, ask_open_image,
                     ask_save_path, field_label, hint_label, make_combo, make_sidebar,
                     pil_to_pixmap, section_title)

# "Shrink source first": undoes an enlargement YouTube applied to a tiny thumbnail, so the AI
# works on real pixels instead of interpolated blur. Try it when a small source looks fuzzy.
# English text = internal key; the displayed (translated) names are in i18n.NAMES_FR.
SHRINK_CHOICES = {
    "Off": 1.0,
    "Divide by 1.5": 1.5,
    "Divide by 2 (enlarged thumbnail)": 2.0,
    "Divide by 3": 3.0,
}

FORMAT_LABELS = {"PNG": "PNG", "JPG": "JPG", "WEBP": "WebP"}


def _result_preview(path):
    """Small PIL thumbnail of the finished wallpaper + its real size (worker thread)."""
    with Image.open(path) as im:
        size = im.size
        thumb = im.convert("RGB")
    thumb.thumbnail((1600, 1600))
    return thumb, size


class WallpaperTab(QWidget, Translatable):
    """The second tab of the main window."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.ctl = Control()
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="wallpaper_thumbs_"))
        self.src_path = None      # image file used as source (local file or downloaded thumbnail)
        self.stem = "wallpaper"   # base name for the suggested output file
        self.src_size = None      # size of the source as read from disk
        self.base_img = None      # source after black-bar removal (full size, RGB)
        self.fetching = False
        self.job_mode = "fill"
        self.job_target = None    # (width, height) of the running / last job
        self.result_path = None   # temporary PNG of the last finished job (None = nothing to save)
        self._loaded = None       # (file name, source size, size without bars) for the file label
        self._picking = False     # True while the user draws the erase zone on the image
        self._status_src = None   # (key, values) of the status line, None if it is a raw text
        self._build()

    # ---- construction ----
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QVBoxLayout()
        left.setContentsMargins(16, 16, 16, 16)
        self.view = CompareView(tr("wp_placeholder"))
        self.view.fileDropped.connect(lambda p: self._load(Path(p), Path(p).stem))
        self.view.emptyClicked.connect(self.choose_file)
        self.view.zoneSelected.connect(self._on_zone_selected)
        left.addWidget(self.view)
        root.addLayout(left, 1)

        side, body, bottom = make_sidebar("")
        self._tx(side.findChild(QLabel, "sidebarTitle"), "nav_wallpaper")
        root.addWidget(side)

        # 1. Source
        body.addWidget(self._tx(section_title(""), "sec_source", upper=True))
        self.url_edit = QLineEdit()
        self._tx(self.url_edit, "url_placeholder", attr="setPlaceholderText")
        self.url_edit.returnPressed.connect(self.fetch)
        body.addWidget(self.url_edit)
        row = QHBoxLayout()
        self.fetch_btn = self._tx(QPushButton(), "fetch_thumb")
        self.fetch_btn.clicked.connect(self.fetch)
        row.addWidget(self.fetch_btn, 1)
        pick = self._tx(QPushButton(), "choose_file")
        pick.clicked.connect(self.choose_file)
        row.addWidget(pick, 1)
        body.addLayout(row)
        self.file_label = hint_label("")
        body.addWidget(self.file_label)
        self._render_file_label()

        # 2. Target resolution
        body.addWidget(self._tx(section_title(""), "sec_target", upper=True))
        self.preset_box = make_combo([SCREEN_PRESET] + list(PRESETS))
        self.preset_box.set_key("4K / UHD - 3840x2160")
        self.preset_box.activated.connect(lambda _i: self._on_preset())
        body.addWidget(self.preset_box)
        size_row = QHBoxLayout()
        size_row.addWidget(self._tx(field_label(""), "width"))
        self.w_edit = QLineEdit("3840")
        self.w_edit.setMaximumWidth(80)
        size_row.addWidget(self.w_edit)
        size_row.addSpacing(8)
        size_row.addWidget(self._tx(field_label(""), "height"))
        self.h_edit = QLineEdit("2160")
        self.h_edit.setMaximumWidth(80)
        size_row.addWidget(self.h_edit)
        size_row.addStretch(1)
        body.addLayout(size_row)

        # 3. Options (same as the Upscaler tab, plus the number of passes)
        body.addWidget(self._tx(section_title(""), "sec_options", upper=True))
        body.addWidget(self._tx(field_label(""), "ai_model"))
        self.model_box = make_combo(MODELS)
        self.model_box.set_key("Anime - max quality")
        self.model_box.activated.connect(lambda _i: self._update_info())
        body.addWidget(self.model_box)

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

        body.addWidget(self._tx(field_label(""), "aspect_ratio"))
        self.fit_box = make_combo(FIT_MODES)
        self.fit_box.activated.connect(lambda _i: self._on_fit_change())
        body.addWidget(self.fit_box)

        body.addWidget(self._tx(field_label(""), "out_format"))
        self.fmt_seg = SegmentedControl([(k, FORMAT_LABELS[k]) for k in OUTPUT_FORMATS], "PNG")
        body.addWidget(self.fmt_seg)

        body.addWidget(self._tx(field_label(""), "passes_field"))
        self.passes_seg = SegmentedControl([("0", "Auto"), ("1", "1"), ("2", "2"), ("3", "3")], "0")
        self.passes_seg.valueChanged.connect(lambda _k: self._update_info())
        body.addWidget(self.passes_seg)

        # 4. Cleaning and framing
        body.addWidget(self._tx(section_title(""), "sec_clean", upper=True))
        self.denoise = self._tx(SliderRow("", 0, 8, 0.0, 0.5, "{:.1f}"), "jpeg_clean", attr="set_label")
        self.grain = self._tx(SliderRow("", 0, 6, 2.0, 0.5, "{:.1f}"), "final_grain", attr="set_label")
        self.sharp = self._tx(SliderRow("", 0, 100, 40, 1, "{:.0f}"), "final_sharp", attr="set_label")
        body.addWidget(self.denoise)
        body.addWidget(self.grain)
        body.addWidget(self.sharp)
        body.addWidget(self._tx(field_label(""), "shrink_first"))
        self.shrink_box = make_combo(SHRINK_CHOICES)
        self.shrink_box.activated.connect(lambda _i: self._update_info())
        body.addWidget(self.shrink_box)
        self.fx = self._tx(SliderRow("", 0, 100, 50, 1, "{:.0f} %"), "framing_h", attr="set_label")
        self.fy = self._tx(SliderRow("", 0, 100, 50, 1, "{:.0f} %"), "framing_v", attr="set_label")
        self.fx.valueChanged.connect(lambda _v: self._on_framing())
        self.fy.valueChanged.connect(lambda _v: self._on_framing())
        body.addWidget(self.fx)
        body.addWidget(self.fy)
        if np is None or cv2 is None:
            warn = self._tx(hint_label(""), "warn_numpy")
            warn.setObjectName("error")
            body.addWidget(warn)

        self._build_erase(body)
        body.addStretch(1)

        # Pinned bottom area
        self.info_label = QLabel("")
        self.info_label.setObjectName("info")
        self.info_label.setWordWrap(True)
        bottom.addWidget(self.info_label)
        btns = QHBoxLayout()
        self.go_btn = self._tx(QPushButton(), "create_wp")
        self.go_btn.setObjectName("primary")
        self.go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.go_btn.clicked.connect(self.start)
        btns.addWidget(self.go_btn, 1)
        self.save_btn = self._tx(QPushButton(), "download")
        self.save_btn.setEnabled(False)
        self._tx(self.save_btn, "save_tip_wp", attr="setToolTip")
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
        # These options change the result without changing the preview: drop a stale result.
        for slider in (self.denoise, self.grain, self.sharp, self.conf, self.bright):
            slider.valueChanged.connect(lambda _v: self._invalidate())
        self.erase_text.toggled.connect(lambda _c: self._invalidate())
        self.zone_mode_box.activated.connect(lambda _i: self._invalidate())

    def _build_erase(self, body):
        """Section 5: optional erasing of text, logos and sound bars (OCR + LaMa)."""
        body.addWidget(self._tx(section_title(""), "sec_erase", upper=True))
        self.erase_text = self._tx(QCheckBox(), "erase_text")
        body.addWidget(self.erase_text)

        body.addWidget(self._tx(field_label(""), "zone"))
        self.zone_box = make_combo(ZONE_PRESETS)
        self.zone_box.set_key("No zone")
        self.zone_box.activated.connect(lambda _i: self._on_zone_preset())
        body.addWidget(self.zone_box)

        # Draw the zone directly on the image (fills the L / T / R / B fields below).
        self.zone_pick_btn = QPushButton()
        self.zone_pick_btn.setCheckable(True)
        self.zone_pick_btn.toggled.connect(self._on_zone_pick)
        body.addWidget(self.zone_pick_btn)
        self._render_pick_btn()

        # Zone rectangle in percent of the kept picture (shown in red on the preview).
        coords = QHBoxLayout()
        coords.setSpacing(4)
        self.zone_edits = []
        for key in ("zone_l", "zone_t", "zone_r", "zone_b"):  # left, top, right, bottom
            coords.addWidget(self._tx(field_label(""), key))
            edit = QLineEdit("0")
            edit.setMaximumWidth(52)
            edit.textChanged.connect(lambda _t: self._on_zone_edit())
            coords.addWidget(edit)
            self.zone_edits.append(edit)
        coords.addWidget(field_label("(%)"))
        coords.addStretch(1)
        body.addLayout(coords)
        body.addWidget(self._tx(hint_label(""), "zone_hint"))

        body.addWidget(self._tx(field_label(""), "erase"))
        self.zone_mode_box = make_combo(ZONE_MODES)
        self.zone_mode_box.activated.connect(lambda _i: self._refresh_preview())
        body.addWidget(self.zone_mode_box)

        self.bright = self._tx(SliderRow("", 100, 255, 200, 1, "{:.0f}"), "bright_from", attr="set_label")
        self.bright.valueChanged.connect(lambda _v: self._refresh_preview())
        body.addWidget(self.bright)

        self.conf = self._tx(SliderRow("", 0.05, 0.8, 0.15, 0.05, "{:.2f}"), "text_sens", attr="set_label")
        body.addWidget(self.conf)
        body.addWidget(self._tx(hint_label(""), "sens_hint"))

        if not cleanup.available():
            warn = self._tx(hint_label(""), "warn_cleanup", hint=cleanup.INSTALL_HINT)
            warn.setObjectName("warn")
            body.addWidget(warn)

    # ---- language ----
    def retranslate(self):
        """Re-render every text after a language change (devices are refilled by App)."""
        self.retranslate_texts()
        for box in (self.preset_box, self.model_box, self.fit_box, self.shrink_box,
                    self.zone_box, self.zone_mode_box):
            box.retranslate()
        self.view.set_placeholder(tr("wp_placeholder"))
        self._render_file_label()
        self._render_pick_btn()
        self._render_info()
        if self._status_src is not None:
            self.say(self._status_src[0], **self._status_src[1])

    def say(self, key, **values):
        """Show a translated status message (it is re-translated on language change)."""
        self._status_src = (key, values)
        self.status.setText(tr(key, **values))

    def set_status(self, text):
        """Show a raw text (already translated by whoever produced it)."""
        self._status_src = None
        self.status.setText(text)

    def _render_file_label(self):
        if self._loaded is None:
            self.file_label.setText(tr("no_image"))
            return
        name, size, base = self._loaded
        note = tr("loaded_note", w=base[0], h=base[1]) if base != size else ""
        self.file_label.setText(f"{name}  ({size[0]}×{size[1]}){note}")

    # ---- zone handling ----
    def _render_pick_btn(self):
        self.zone_pick_btn.setText(tr("zone_pick_active" if self._picking else "zone_pick"))

    def _on_zone_pick(self, checked):
        """The "Select zone on the image" button was toggled."""
        if checked and self.base_img is None:  # nothing to draw on yet
            self.zone_pick_btn.setChecked(False)
            self.say("missing_wp_image")
            return
        self._picking = checked
        self.view.set_select_mode(checked)
        if checked:
            self._invalidate()  # a zone change makes any shown result stale: show the source
        self._render_pick_btn()

    def _on_zone_selected(self, x0, y0, x1, y1):
        """A rectangle was drawn on the image (percent of the kept picture)."""
        for edit, v in zip(self.zone_edits, (x0, y0, x1, y1)):
            edit.blockSignals(True)
            edit.setText(f"{v:g}")
            edit.blockSignals(False)
        self.zone_box.set_key("Custom")
        self.zone_pick_btn.setChecked(False)  # one rectangle per click
        self._on_zone_pick(False)             # idempotent; does not rely on the toggled signal
        self._refresh_preview()  # the zone is drawn in red

    def _on_zone_preset(self):
        zone = ZONE_PRESETS.get(self.zone_box.key())
        if zone is not None:
            for edit, v in zip(self.zone_edits, zone):
                edit.blockSignals(True)
                edit.setText(str(v))
                edit.blockSignals(False)
        self._refresh_preview()

    def _on_zone_edit(self):
        # Editing a coordinate by hand switches the preset to "Custom".
        self.zone_box.blockSignals(True)
        self.zone_box.set_key("Custom")
        self.zone_box.blockSignals(False)
        self._refresh_preview()

    def _zone(self):
        """Zone as (x0, y0, x1, y1) in percent, or None when empty or invalid."""
        try:
            x0, y0, x1, y1 = (min(100.0, max(0.0, float(e.text()))) for e in self.zone_edits)
        except ValueError:
            return None
        return (x0, y0, x1, y1) if (x1 > x0 and y1 > y0) else None

    def _passes(self):
        """Max AI passes chosen in the selector (0 = Auto)."""
        return int(self.passes_seg.value() or 0)

    def _clean_options(self):
        return CleanOptions(text=self.erase_text.isChecked(), ocr_conf=self.conf.value(),
                            zone=self._zone(),
                            zone_mode=ZONE_MODES[self.zone_mode_box.key()],
                            bright=int(self.bright.value()))

    # ---- devices (shared with the Upscaler tab) ----
    def device(self):
        """Identifier ("auto", "cpu" or a GPU index) of the selected device."""
        return self.app.devices.get(self.dev_box.currentText(), "auto")

    def set_devices(self, keep):
        """Refill the dropdown from app.devices (already rebuilt), selecting identifier `keep`.

        Falls back to the first entry (Auto) if that device no longer exists.
        """
        self.dev_box.blockSignals(True)
        self.dev_box.set_keys(list(self.app.devices))
        for i, ident in enumerate(self.app.devices.values()):
            if ident == keep:
                self.dev_box.setCurrentIndex(i)
                break
        else:
            self.dev_box.setCurrentIndex(0)
        self.dev_box.blockSignals(False)

    # ---- source ----
    def choose_file(self):
        path = ask_open_image(self)
        if path:
            self._load(Path(path), Path(path).stem)

    def fetch(self):
        """Download the best thumbnail for the YouTube link / id in the entry box."""
        if self.fetching:
            return
        text = self.url_edit.text().strip()
        if text and Path(text).exists():  # a path pasted in the box
            self._load(Path(text), Path(text).stem)
            return
        vid = video_id(text)
        if not vid:
            QMessageBox.warning(self, tr("youtube_title"), tr("youtube_msg"))
            return
        self.fetching = True
        self.fetch_btn.setEnabled(False)
        self.say("fetching")
        put = self.app.q.put

        def run():
            try:
                path = fetch_thumbnail(vid, self.tmp_dir, status=lambda s: put(("w_status", s)))
                put(("w_fetched", (path, vid)))
            except Exception as e:
                put(("w_fetch_error", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _load(self, path, stem):
        try:
            with Image.open(path) as im:
                img = ImageOps.exif_transpose(im).convert("RGB")
        except Exception as e:
            QMessageBox.critical(self, tr("error_title"), tr("cant_open", e=e))
            return
        self.src_path, self.stem, self.src_size = Path(path), stem, img.size
        self.base_img = autocrop_bars(img)
        self._loaded = (Path(path).name, img.size, self.base_img.size)
        self._render_file_label()
        self._refresh_preview()
        self._update_info()

    # ---- derived display ----
    def _target(self):
        try:
            tw, th = int(self.w_edit.text()), int(self.h_edit.text())
        except ValueError:
            return None
        return (tw, th) if (16 <= tw <= MAX_SIDE and 16 <= th <= MAX_SIDE) else None

    def _on_preset(self):
        name = self.preset_box.key()
        size = None
        if name == SCREEN_PRESET:
            screen = self.screen()
            px = screen.size() * screen.devicePixelRatio()
            size = (round(px.width()), round(px.height()))
        elif PRESETS.get(name):
            size = PRESETS[name]
        if size:
            for edit, v in zip((self.w_edit, self.h_edit), size):
                edit.blockSignals(True)
                edit.setText(str(v))
                edit.blockSignals(False)
            self._on_size_edit()

    def _on_size_edit(self):
        self._refresh_preview()
        self._update_info()

    def _on_fit_change(self):
        self._refresh_preview()
        self._update_info()

    def _on_framing(self):
        self._refresh_preview()
        self._update_info()

    def _crop_preview(self, img):
        """Crop `img` the way the pipeline will (fill mode only)."""
        t = self._target()
        if t and FIT_MODES[self.fit_box.key()] == "fill":
            return crop_to_ratio(img, *t, self.fx.value() / 100, self.fy.value() / 100)
        return img

    def _refresh_preview(self):
        """Redraw the canvas with what will really be kept (bars removed, cropped), zone in red.

        Any change of framing or zone invalidates a previous result, so it is dropped.
        """
        if self.base_img is None:
            return
        small = self.base_img.copy()
        small.thumbnail((1100, 1100))  # cheap, and good enough to judge the framing
        small = self._crop_preview(small)
        zone = self._zone()
        if zone:  # show what the zone will erase, in red
            mask = cleanup.zone_mask(small, zone, ZONE_MODES[self.zone_mode_box.key()],
                                     int(self.bright.value()))
            red = Image.blend(small, Image.new("RGB", small.size, (255, 0, 0)), 0.55)
            small = Image.composite(red, small, mask)
        w, h = self._crop_preview(self.base_img).size
        self._invalidate()
        self.view.set_before(pil_to_pixmap(small), f"{w}×{h} px")

    def _invalidate(self):
        """Forget the previewed result: any setting that changes it makes it stale."""
        self.result_path = None
        self.view.clear_after()
        self.save_btn.setEnabled(False)

    def _update_info(self):
        # Also reached when model / shrink / passes change, which stale the result too.
        self._invalidate()
        self._render_info()

    def _render_info(self):
        """Write the summary text (also called alone after a language change)."""
        t = self._target()
        if self.base_img is None or not t:
            self.info_label.setText("")
            return
        mode = FIT_MODES[self.fit_box.key()]
        w, h = self._crop_preview(self.base_img).size
        shrink = SHRINK_CHOICES[self.shrink_box.key()]
        if shrink > 1:
            w, h = max(16, round(w / shrink)), max(16, round(h / shrink))
        f = needed_factor(w, h, *t, mode)
        txt = tr("kept_area", w=w, h=h, tw=t[0], th=t[1], f=f)
        if f <= 1.0:
            txt += "\n" + tr("no_ai_needed")
        else:
            allowed = MODELS[self.model_box.key()][1]
            passes = choose_passes(f, allowed, self._passes(), w, h)
            prod = 1
            for s in passes:
                prod *= s
            txt += "\n" + tr("ai_passes") + tr("then").join(f"×{s}" for s in passes)
            if f / prod > 1.0001:
                txt += tr("then_resize", f=f / prod)
                if f / prod > 2:
                    txt += tr("big_gap")
        self.info_label.setText(txt)

    # ---- processing ----
    def start(self):
        if self.app.busy:
            QMessageBox.information(self, tr("busy_title"), tr("busy_msg"))
            return
        if self.src_path is None:
            QMessageBox.warning(self, tr("missing_image_title"), tr("missing_wp_image"))
            return
        target = self._target()
        if not target:
            QMessageBox.warning(self, tr("invalid_res_title"), tr("invalid_res_msg", max=MAX_SIDE))
            return

        clean = self._clean_options()
        if clean.active and not cleanup.available():
            QMessageBox.warning(self, tr("erase_not_inst_title"),
                                tr("erase_not_inst_msg", hint=cleanup.INSTALL_HINT))
            return

        # The result goes to a temporary PNG first: it is previewed, and only saved
        # when the user clicks "Download".
        dst = self.tmp_dir / "result.png"
        self.job_mode = FIT_MODES[self.fit_box.key()]
        self.job_target = target
        self._invalidate()
        self.ctl = Control()
        self.app.busy = True
        self.go_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.bar.setValue(0)
        self.say("creating")
        args = (self.src_path, dst, target, self.model_box.key(), self.device(),
                self.job_mode, self.denoise.value(), self.grain.value(),
                self._passes(), self.fx.value() / 100, self.fy.value() / 100,
                self.ctl, clean, self.sharp.value(), SHRINK_CHOICES[self.shrink_box.key()])
        threading.Thread(target=self._worker, args=args, daemon=True).start()

    def cancel(self):
        if self.app.busy:
            self.say("cancelling")
            self.ctl.cancel()

    def download(self):
        """Ask where to save, then write the previewed result there (in a worker thread)."""
        if self.result_path is None or not self.result_path.exists() or not self.job_target:
            return
        t = self.job_target
        # A downloaded thumbnail lives in a temp folder: propose the user's home instead.
        start_dir = Path.home() if self.src_path.parent == self.tmp_dir else self.src_path.parent
        dst = ask_save_path(self, self.fmt_seg.value() or "PNG", start_dir,
                            f"{self.stem}_{t[0]}x{t[1]}")
        if not dst:
            return
        self.save_btn.setEnabled(False)
        self.say("saving")
        put, src = self.app.q.put, self.result_path

        def run():
            try:
                export_image(src, dst)
                put(("w_saved", str(dst)))
            except Exception as e:
                put(("w_save_error", str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _worker(self, src, dst, target, model_key, device, mode, denoise, grain, passes, fx, fy,
                ctl, clean, sharp, shrink):
        put = self.app.q.put
        try:
            exe = find_engine()
            if exe is None:
                exe, digest = download_engine(ctl, lambda s: put(("w_status", s)),
                                              lambda p: put(("w_progress", p)))
                put(("w_status", tr("engine_installed", digest=digest[:16])))
                self.app._probe_async(exe)
            make_wallpaper(exe, src, dst, target[0], target[1], model_key, device, mode,
                           denoise, grain, passes, fx, fy,
                           status=lambda s: put(("w_status", s)), ctl=ctl,
                           progress=lambda p: put(("w_progress", p)), clean=clean,
                           sharp=sharp, shrink=shrink)
            try:
                put(("w_result", _result_preview(dst)))
            except Exception:
                pass  # the preview is a bonus: never fail the job because of it
            put(("w_done", str(dst)))
        except Cancelled:
            put(("w_cancelled", None))
        except Exception as e:
            put(("w_error", str(e)))

    # ---- messages from App._on_message ----
    def _finish(self):
        self.app.busy = False
        self.go_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def handle(self, kind, val):
        if kind == "w_progress":
            self.bar.setValue(int(val))
        elif kind == "w_status":
            self.set_status(val)
        elif kind == "w_fetched":
            self.fetching = False
            self.fetch_btn.setEnabled(True)
            self._load(*val)
            self.say("thumb_ready")
        elif kind == "w_fetch_error":
            self.fetching = False
            self.fetch_btn.setEnabled(True)
            self.say("dl_failed")
            QMessageBox.critical(self, tr("error_title"), val)
        elif kind == "w_result":
            thumb, (w, h) = val
            self.view.set_after(pil_to_pixmap(thumb), f"{w}×{h} px", self.job_mode)
        elif kind == "w_done":
            self._finish()
            self.result_path = Path(val)
            self.save_btn.setEnabled(True)
            self.say("preview_ready")
        elif kind == "w_saved":
            self.save_btn.setEnabled(self.result_path is not None)
            self.say("saved_status", path=val)
            QMessageBox.information(self, tr("done_title"), tr("wp_saved", path=val))
        elif kind == "w_save_error":
            self.save_btn.setEnabled(self.result_path is not None)
            self.say("save_failed")
            QMessageBox.critical(self, tr("error_title"), val)
        elif kind == "w_cancelled":
            self._finish()
            self.bar.setValue(0)
            self.say("cancelled")
        elif kind == "w_error":
            self._finish()
            self.say("error_status")
            QMessageBox.critical(self, tr("error_title"), val)

    def shutdown(self):
        """Called when the window closes: stop the job and delete downloaded thumbnails."""
        self.ctl.cancel()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
