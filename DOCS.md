# AI Upscale Studio — Code documentation

A short guide to how the code is organised. For installation, usage and troubleshooting, see `README.md`.

## What it does

A PyQt6 desktop app that enlarges images with **Real-ESRGAN** (the `realesrgan-ncnn-vulkan` command-line engine, which runs on the GPU through Vulkan). It has three tabs:

| Tab | Purpose |
|---|---|
| **Upscaler** | Enlarge any image to a target resolution. |
| **Wallpaper maker** | Same, plus a cleaning pipeline for low-quality sources (YouTube thumbnails, small JPEGs). |
| **Monitoring & Models** | Details of the selected model and live CPU / RAM / GPU / network usage. |

The interface is available in **English and French** (EN | FR switch in the top bar).

## Run it

```bash
pip install PyQt6 pillow psutil numpy opencv-python-headless
python app.py
```

Only `PyQt6` and `pillow` are required. The engine (~30 MB) is downloaded automatically on the first upscale into `./upscaler`.

## Project map

```
app.py            Entry point: creates the Qt app, applies the theme, opens the window.
config.py         Constants (platform, paths, URLs, models, presets) and config.json read/write.
i18n.py           Interface language: tr(), tr_name(), all UI texts in EN and FR.
control.py        Cancellation: the Cancelled exception and the Control handle.
devices.py        GPU/CPU choices for the dropdown and the order in which devices are tried.
engine.py         Real-ESRGAN engine: download + verify + install, run one pass, detect GPUs.
upscale.py        Planning the AI passes, final resize/crop, the full Upscaler pipeline.
wallpaper.py      The Wallpaper pipeline (also usable from the command line).
cleanup.py        Optional erasing of text / logos / sound bars (OCR + LaMa inpainting).
export.py         Saves the temporary PNG result in the format chosen at download time.
monitor.py        Background CPU / RAM / GPU / network sampling.
theme.py          Dark palette and the Qt stylesheet (QSS).
widgets.py        Reusable widgets: before/after view, segmented control, slider row, dialogs.
gui.py            Main window (App), Upscaler tab, Monitoring tab.
gui_wallpaper.py  Wallpaper maker tab.
config.json       Created automatically: engine SHA-256 per platform + chosen language.
```

Dependencies only go one way (no cycles):

```
config  <-  i18n, control, devices, monitor
engine  ->  config, control, devices, i18n
upscale ->  config, engine          wallpaper -> upscale, cleanup, engine
widgets ->  config, i18n            export -> config, i18n
gui_wallpaper, gui  ->  everything above        app -> gui, theme
```

The GUI modules are the only ones that import PyQt6, so `upscale.py`, `wallpaper.py`, `engine.py` etc. can be used and tested without a window.

## How a job runs

Both tabs follow the same two-step flow. **Nothing is written to the user's disk until they click Download.**

1. The user clicks **Upscaler** (or **Create wallpaper**). The tab validates the inputs and starts a **worker thread**.
2. The worker finds or installs the engine, runs the pipeline and writes the result to a **temporary PNG**.
3. It sends a small preview image to the UI. The user compares before / after with the draggable divider.
4. **Download** asks for a location and format, then `export.py` writes the final file (PNG is a plain copy; JPG and WebP use quality 95).

Any setting that would change the result (size, model, ratio, framing...) drops the preview, so the Download button is never offered for a stale result.

### Upscaler pipeline (`upscale.upscale_image`)

1. Load the image (EXIF rotation applied) and compute the needed enlargement factor (`needed_factor`: *fill* covers the target and crops, *fit* stays inside and adds black bars).
2. `plan_passes` picks a chain of AI scales (max 3 passes) allowed by the model, e.g. `x4 then x2`.
3. `engine.run_pass` runs each pass in the Real-ESRGAN subprocess.
4. `finalize` resizes with Lanczos and crops or letterboxes to the exact target size.
5. Save.

### Wallpaper pipeline (`wallpaper.make_wallpaper`)

Fetch thumbnail → remove black bars (`autocrop_bars`) → crop to the target ratio *before* upscaling → optional erase of text/logos (`cleanup`) → optional shrink → JPEG cleanup (`deblock`) → AI pass(es) (`choose_passes`) → exact size → sharpen → film grain → save.

It can also be run without the GUI: `python wallpaper.py <youtube link or file> -r 3840x2160`.

### Engine and devices

- `engine.download_engine` downloads the official release zip, computes its **SHA-256** and stores it in `config.json`. A later download with a different hash is refused.
- `devices.device_attempts` returns an ordered list of devices to try (on Linux with NVIDIA, the NVIDIA GPU first, then the system default). `engine.run_pass` falls back to the next one if a device fails.
- `control.Control` is shared between the UI and the worker: `cancel()` sets a flag and terminates the engine process.

## Threading and messages

Widgets are only touched from the UI thread. Worker threads never use widgets: they call `app.q.put((kind, value))`. `widgets.SignalQueue` turns every call into a Qt signal delivered to `App._on_message`, which forwards it to the right tab's `handle(kind, value)`.

| Message kind | Sent by | Meaning |
|---|---|---|
| `progress`, `status` | Upscaler worker | Progress bar (0–100) and status line. |
| `result` | Upscaler worker | Preview thumbnail and real size. |
| `done`, `cancelled`, `error` | Upscaler worker | End of the job (any outcome). |
| `saved`, `save_error` | Download thread | Result of saving the file. |
| `w_*` (`w_progress`, `w_status`, `w_fetched`, `w_done`...) | Wallpaper tab | Same kinds, prefixed with `w_`. |
| `metrics` | `monitor.monitor_loop` | CPU / RAM / GPU / network sample every 2 s. |
| `gpus` | GPU probe thread | Detected GPUs, used to rebuild the device dropdowns. |

## Translations (`i18n.py`)

- **Every visible text** goes through `tr("key", **values)`. Messages live in the `STRINGS` dict as `key: (english, french)`, with `str.format` placeholders (`{path}`, `{n}`...).
- **Built-in choices** (model names, resolution presets, fit modes, erase zones...) keep their **English text as internal key** everywhere in the code, so the logic never depends on the language. Their French display names are in `NAMES_FR`; `tr_name(name)` returns the displayed name.
- Drop-downs are `widgets.KeyCombo`: read the selection with `combo.key()` (never `currentText()`), set it with `combo.set_key(...)`.
- Widgets whose text is fixed are registered with `self._tx(widget, "key")` (mixin `Translatable`). Texts that depend on state (status line, summary, file card) are re-rendered in each tab's `retranslate()`.
- The language switch in `App.set_language()` saves the choice in `config.json` and calls `retranslate()` on every tab: no restart needed. English is the default.
- Status messages sent by worker threads are translated when they are produced, so a message already on screen keeps its language until the next one.

**Add or change a text:** edit its line in `STRINGS` (both languages), use `tr("key")` in the code.
**Add a language:** add its code to `LANGS`, add a third element to every tuple in `STRINGS`, and a translation table like `NAMES_FR` (then extend `tr_name`).

## Common changes

| I want to... | Edit |
|---|---|
| Add an AI model | `MODELS` in `config.py` (display name → engine model name, supported scales, description) + the French name/description in `NAMES_FR`. The model files must exist in the engine's `models/` folder. |
| Add a resolution preset | `PRESETS` in `config.py` (+ `NAMES_FR` if the name has words to translate). |
| Add an erase zone | `ZONE_PRESETS` in `cleanup.py` (+ `NAMES_FR`). |
| Change the colours | `theme.py` (palette and QSS). |
| Change the maximum size | `MAX_SIDE` / `WEBP_MAX_SIDE` in `config.py`. |
| Change how the erase zone is drawn | `CompareView` in `widgets.py` (`set_select_mode`, `zoneSelected` signal) and `WallpaperTab._on_zone_selected` in `gui_wallpaper.py`. |
| Add a setting to a tab | Build the widget in the tab's `_build()`, read it in `start()`, pass it to the worker, and call `_invalidate()` when it changes. |

## Dependencies

| Package | Required | Used for |
|---|---|---|
| `PyQt6` | Yes | The interface. |
| `pillow` | Yes | Reading, writing and resizing images. |
| `psutil` | Recommended | Monitoring tab. |
| `numpy`, `opencv-python-headless` | Recommended | Wallpaper maker: black bars, JPEG cleanup, grain. |
| `torch`, `torchvision`, `easyocr`, `simple-lama-inpainting` | Optional (heavy) | Erasing text / logos. |
