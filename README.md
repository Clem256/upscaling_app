# AI Upscale Studio

Desktop application (**PyQt6**) to upscale and enhance image quality using **Real-ESRGAN** AI (via Vulkan). Ideal for creating high-definition wallpapers (PC, Ultrawide, 8K, phone) or turning YouTube thumbnails into clean wallpapers.

## Key Features

* **Classic Upscaler:** Enlarges any image (2×, 4×, 8×, or custom resolution) with selectable AI models and export formats (PNG, JPG, WebP).
* **Wallpaper Maker:** Complete pipeline designed for low-quality sources (YouTube thumbnails, small JPEGs). Fetches the highest available quality, removes black bars, crops, cleans JPEG compression artifacts, and enhances sharpness.
* **AI Magic Eraser (Optional):** Automatically detects and erases text, logos, or audio visualizer bars before upscaling.
* **Before / After Preview:** Compare the result using an interactive slider before deciding to download the image.
* **System Monitoring:** Real-time tracking of CPU, RAM, NVIDIA GPU, and network usage.
* **Bilingual & Cross-Platform:** Interface available in English and French (Windows, Linux, macOS).

## Installation

### Requirements

* **Python 3.9+**
* A **Vulkan-capable GPU** with up-to-date drivers (CPU mode works, but is very slow).
* An internet connection on first launch (automatic AI engine download, ~30 MB).

### 1. Basic Installation

```bash
pip install PyQt6 pillow psutil numpy opencv-python-headless
```

### 2. Optional: Text & Logo Removal (heavy ~2 GB)

Only required for the eraser feature in the Wallpaper Maker tab:

```bash
pip install torch torchvision easyocr
pip install --no-deps simple-lama-inpainting
```

*(Note: `--no-deps` prevents version conflicts with Pillow and NumPy).*

### Running the App

```bash
python app.py
```

## Usage

### Tab 1: Upscaler

1. Drag and drop an image (PNG, JPG, WebP, BMP, TIFF).
2. Choose an upscale factor (2×, 4×, 8×) or a target resolution (Full HD, 4K, phone...).
3. Select the AI model and aspect mode (*Fill* to cover/crop, *Fit* to keep the whole image).
4. Click **Upscaler**, compare the result with the slider, then click **Download**.

### Tab 2: Wallpaper Maker

1. Paste a **YouTube link** (or video ID) or import a local image.
2. Adjust cleanup options if needed:
   * **JPEG cleanup:** Reduces compression blocks (recommended: 2 to 4).
   * **Final grain / sharpness:** Adds subtle grain and sharpness to avoid the AI's "smooth/plastic" look.
   * **Erase zone:** Drag a rectangle on the preview to remove logos or text via AI.
3. Click **Create wallpaper**, check the preview, and download.

### Available AI Models

* **Anime - fast (recommended):** Very fast, ideal for anime and modern illustrations (×2, ×3, ×4).
* **Anime - max quality:** Slower, better restoration of fine lines and drawn textures (×4).
* **Photo / realistic:** Designed for real-life photos, reduces blur and digital noise (×4, slowest).

## Command Line Usage (CLI)

You can generate wallpapers directly from the terminal without opening the GUI:

```bash
# From a YouTube link (4K by default)
python wallpaper.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"

# From a local image in 2K with a specific model
python wallpaper.py image.jpg -r 2560x1440 --model "Anime - max quality"

# Phone format with focus shifted to the left
python wallpaper.py VIDEO_ID -r 1440x3120 --focus-x 0.3
```

## Quick Troubleshooting

* **Very slow processing:** Check the *Device* option to make sure your GPU is selected (and not the CPU).
* **SHA-256 verification error:** If the engine download is blocked after an update, delete the `"sha256"` entry in `config.json` and restart the app.
* **Result looks too smooth ("plastic"):** Lower *JPEG cleanup* and slightly increase *Final grain* (between 1 and 3).
* **Text not fully erased:** Lower *Text sensitivity* or manually draw an erase zone rectangle on the image.

## Credits

AI Engine: [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) • Eraser: EasyOCR & LaMa • Interface: PyQt6.
