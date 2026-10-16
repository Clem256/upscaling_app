"""
Interface language (English / French).

  tr(key, **values)   Text of a UI message in the current language.
  tr_name(name)       Display name of a built-in choice (model, preset, zone...).
  get_lang() / set_lang(code)   Current language; set_lang() also remembers it in config.json.

How it works
------------
* Messages live in STRINGS: {key: (english, french)}. Placeholders use str.format
  syntax, e.g. tr("saved_status", path="/tmp/x.png").
* Built-in choices (model names, resolution presets, zones...) keep their English
  text as their internal key everywhere in the code, so the logic never depends on
  the language. NAMES_FR only changes what is *displayed* in French; any name
  without an entry is shown unchanged.
* English is the default. The choice is stored in config.json under "language".

To add a message, add a line to STRINGS. To add a language, add a third element to
every tuple, add its code to LANGS, and add a column to NAMES_FR (renamed accordingly).

This module only depends on config.py, so every other module may import it.
"""

from config import load_config, save_config

LANGS = ("en", "fr")
DEFAULT_LANG = "en"

_lang = DEFAULT_LANG


def get_lang():
    return _lang


def init_lang():
    """Load the saved language from config.json (called once at startup)."""
    global _lang
    saved = load_config().get("language")
    _lang = saved if saved in LANGS else DEFAULT_LANG


def set_lang(code):
    """Switch language and remember the choice in config.json."""
    global _lang
    if code not in LANGS:
        return
    _lang = code
    try:
        cfg = load_config()
        cfg["language"] = code
        save_config(cfg)
    except OSError:
        pass  # read-only folder: the language still changes for this session


def tr(key, **values):
    """Return message `key` in the current language, formatted with `values`."""
    entry = STRINGS.get(key)
    if entry is None:
        return key  # unknown key: show it as-is rather than crash
    text = entry[LANGS.index(_lang)]
    return text.format(**values) if values else text


def tr_name(name):
    """Display name of a built-in choice; English keys are returned as-is in English."""
    if _lang == "fr":
        return NAMES_FR.get(name, name)
    return name


# --------------------------------------------------------------------------- #
# Messages: key -> (English, French)
# --------------------------------------------------------------------------- #

STRINGS = {
    # ---- common ----
    "error_title": ("Error", "Erreur"),
    "done_title": ("Done", "Terminé"),
    "busy_title": ("Busy", "Occupé"),
    "busy_msg": ("Another task is running. Wait for it to finish.",
                 "Une autre tâche est en cours. Attends qu'elle se termine."),
    "ready": ("Ready.", "Prêt."),
    "cancel": ("Cancel", "Annuler"),
    "download": ("Download", "Télécharger"),
    "width": ("Width", "Largeur"),
    "height": ("Height", "Hauteur"),
    "ai_model": ("AI model", "Modèle d'IA"),
    "device": ("Device", "Appareil"),
    "refresh_gpu": ("Detect GPUs again", "Détecter à nouveau les GPU"),
    "aspect_ratio": ("Aspect ratio", "Ratio"),
    "out_format": ("Output format", "Format de sortie"),
    "target_res": ("Target resolution", "Résolution cible"),
    "no_image": ("No image", "Aucune image"),
    "cant_open": ("Unable to open the image:\n{e}", "Impossible d'ouvrir l'image :\n{e}"),
    "missing_image_title": ("Missing image", "Image manquante"),
    "invalid_res_title": ("Invalid resolution", "Résolution invalide"),
    "invalid_res_msg": ("Enter a width and a height between 16 and {max}.",
                        "Saisis une largeur et une hauteur entre 16 et {max}."),
    "size_range": ("Width and height: between 16 and {max} px.",
                   "Largeur et hauteur : entre 16 et {max} px."),
    "enlarge": ("{sw}×{sh}  →  {tw}×{th}   (enlargement ×{f:.2f})",
                "{sw}×{sh}  →  {tw}×{th}   (agrandissement ×{f:.2f})"),
    "no_ai_needed": ("No AI upscaling needed: simple resize.",
                     "Pas d'upscaling IA nécessaire : simple redimensionnement."),
    "ai_passes": ("AI passes: ", "Passes IA : "),
    "then": (" then ", " puis "),
    "cancelling": ("Cancelling…", "Annulation…"),
    "saving": ("Saving…", "Enregistrement…"),
    "engine_installed": ("Engine installed (SHA-256 {digest}...)",
                         "Moteur installé (SHA-256 {digest}...)"),
    "preview_ready": ("Preview ready: drag the bar to compare, then click Download.",
                      "Aperçu prêt : déplace la barre pour comparer, puis clique sur Télécharger."),
    "saved_status": ("Saved: {path}", "Enregistré : {path}"),
    "save_failed": ("Saving failed.", "Échec de l'enregistrement."),
    "cancelled": ("Cancelled.", "Annulé."),
    "error_status": ("Error.", "Erreur."),

    # ---- window / navigation ----
    "nav_upscaler": ("Upscaler", "Upscaler"),
    "nav_wallpaper": ("Wallpaper maker", "Wallpaper maker"),
    "nav_monitor": ("Monitoring && Models", "Monitoring && Modèles"),  # && = literal & in Qt
    "language": ("Language", "Langue"),
    "detecting_gpus": ("Detecting GPUs…", "Détection des GPU…"),
    "engine_missing_title": ("Engine missing", "Moteur manquant"),
    "engine_missing_msg": ("The engine will be downloaded on the first upscale; "
                           "GPUs will be detected afterwards.",
                           "Le moteur sera téléchargé au premier upscale ; "
                           "les GPU seront détectés ensuite."),
    "ready_gpus": ("Ready. {n} GPU(s) detected.", "Prêt. {n} GPU détecté(s)."),
    "ready_nogpu": ("Ready. No GPU detected: Auto or CPU mode only.",
                    "Prêt. Aucun GPU détecté : mode Auto ou CPU uniquement."),

    # ---- Upscaler tab ----
    "imported_image": ("Imported image", "Image importée"),
    "choose": ("Choose…", "Choisir…"),
    "replace": ("Replace", "Remplacer"),
    "quick_scale": ("Quick scale", "Échelle rapide"),
    "custom": ("Custom", "Personnalisé"),
    "save_tip_up": ("Saves the result shown (available after upscaling)",
                    "Enregistre le résultat affiché (disponible après l'upscale)"),
    "pick_image_first": ("Choose an image first.", "Choisis d'abord une image."),
    "upscaling": ("Upscaling…", "Upscale en cours…"),
    "image_saved": ("Image saved:\n{path}", "Image enregistrée :\n{path}"),

    # ---- Monitoring tab ----
    "active_model": ("Active model details", "Détails du modèle actif"),
    "engine_line": ("Engine: Vulkan NCNN (C++)", "Moteur : Vulkan NCNN (C++)"),
    "model_line": ("Model: {name}  (scales: {scales})", "Modèle : {name}  (échelles : {scales})"),
    "live_usage": ("Live system usage", "Utilisation système en direct"),
    "no_psutil": ("psutil module missing: pip install psutil",
                  "Module psutil manquant : pip install psutil"),
    "cpu": ("Processor (CPU)", "Processeur (CPU)"),
    "ram": ("Memory (RAM)", "Mémoire (RAM)"),
    "gpu_label": ("Graphics card", "Carte graphique"),
    "detecting": ("Detecting…", "Détection…"),
    "net_label": ("Network throughput of the WHOLE machine (indicative)",
                  "Débit réseau de TOUTE la machine (indicatif)"),
    "mon_no_nvidia": ("NVIDIA not detected (the GPU is used through Vulkan, without statistics)",
                      "NVIDIA non détecté (le GPU est utilisé via Vulkan, sans statistiques)"),
    "mon_nv_unavail": ("NVIDIA detected, statistics unavailable",
                       "NVIDIA détecté, statistiques indisponibles"),
    "mon_gpu_line": ("{name}: {util} % active | VRAM: {used} / {tot} MB",
                     "{name} : {util} % actif | VRAM : {used} / {tot} Mo"),

    # ---- Wallpaper maker tab ----
    "wp_placeholder": ("Fetch a YouTube thumbnail\nor choose / drop an image",
                       "Récupère une miniature YouTube\nou choisis / dépose une image"),
    "sec_source": ("1. Source", "1. Source"),
    "sec_target": ("2. Target resolution", "2. Résolution cible"),
    "sec_options": ("3. Options", "3. Options"),
    "sec_clean": ("4. Cleaning and framing", "4. Nettoyage et cadrage"),
    "sec_erase": ("5. Erase text / logos / sound bars (optional)",
                  "5. Effacer texte / logos / barres son (option)"),
    "url_placeholder": ("YouTube link or video ID", "Lien YouTube ou identifiant de vidéo"),
    "fetch_thumb": ("Fetch thumbnail", "Récupérer la miniature"),
    "choose_file": ("Choose a file…", "Choisir un fichier…"),
    "passes_field": ("AI passes", "Passes IA"),
    "jpeg_clean": ("JPEG cleanup", "Nettoyage JPEG"),
    "final_grain": ("Final grain", "Grain final"),
    "final_sharp": ("Final sharpness", "Netteté finale"),
    "shrink_first": ("Shrink source before AI", "Réduire la source avant l'IA"),
    "framing_h": ("Framing: horizontal", "Cadrage : horizontal"),
    "framing_v": ("Framing: vertical", "Cadrage : vertical"),
    "warn_numpy": ("numpy / opencv missing: black-bar removal, cleanup and grain are disabled.  "
                   "pip install numpy opencv-python-headless",
                   "numpy / opencv manquants : suppression des bandes noires, nettoyage "
                   "et grain désactivés.  pip install numpy opencv-python-headless"),
    "create_wp": ("Create wallpaper", "Créer le fond d'écran"),
    "save_tip_wp": ("Saves the result shown (available after creation)",
                    "Enregistre le résultat affiché (disponible après la création)"),
    "erase_text": ("Erase text (titles, credits) with OCR",
                   "Effacer le texte (titres, crédits) par OCR"),
    "zone": ("Zone", "Zone"),
    "zone_pick": ("Select zone on the image", "Sélectionner la zone sur l'image"),
    "zone_pick_active": ("Drag a rectangle on the image…  (click to cancel)",
                         "Trace un rectangle sur l'image…  (clique pour annuler)"),
    "zone_l": ("L", "G"),
    "zone_t": ("T", "H"),
    "zone_r": ("R", "D"),
    "zone_b": ("B", "B"),
    "zone_hint": ("L = left, T = top, R = right, B = bottom",
                  "G = gauche, H = haut, D = droite, B = bas"),
    "erase": ("Erase", "Effacer"),
    "bright_from": ("Brightness from", "Luminosité à partir de"),
    "text_sens": ("Text sensitivity", "Sensibilité du texte"),
    "sens_hint": ("Low = erases more (risk: also erases parts of the drawing); "
                  "high = only clearly legible text.",
                  "Bas = efface davantage (risque : efface aussi des motifs du dessin) ; "
                  "haut = uniquement le texte bien net."),
    "warn_cleanup": ("Not installed yet. For this part: {hint}  "
                     "(large download: PyTorch; uses the GPU when possible).",
                     "Pas encore installé. Pour cette partie : {hint}  "
                     "(gros téléchargement : PyTorch ; utilise le GPU si possible)."),
    "youtube_title": ("YouTube link", "Lien YouTube"),
    "youtube_msg": ("Paste a YouTube link or an 11-character video ID.",
                    "Colle un lien YouTube ou un identifiant de vidéo de 11 caractères."),
    "fetching": ("Looking for the best thumbnail…", "Recherche de la meilleure miniature…"),
    "loaded_note": ("  →  {w}×{h} without black bars", "  →  {w}×{h} sans les bandes noires"),
    "kept_area": ("Kept area {w}×{h}  →  {tw}×{th}   (enlargement ×{f:.2f})",
                  "Zone conservée {w}×{h}  →  {tw}×{th}   (agrandissement ×{f:.2f})"),
    "then_resize": (", then simple resize ×{f:.2f}", ", puis redimensionnement simple ×{f:.2f}"),
    "big_gap": ("  (big gap: try 2 passes)", "  (grand écart : essaie 2 passes)"),
    "missing_wp_image": ("Fetch a thumbnail or choose an image first.",
                         "Récupère une miniature ou choisis d'abord une image."),
    "erase_not_inst_title": ("Erasing not installed", "Effacement non installé"),
    "erase_not_inst_msg": ("Erasing text / logos needs two extra packages:\n\n{hint}\n\n"
                           "Install them and restart the app, or uncheck the erase options.",
                           "L'effacement de texte / logos nécessite deux paquets "
                           "supplémentaires :\n\n{hint}\n\nInstalle-les et relance "
                           "l'application, ou décoche les options d'effacement."),
    "creating": ("Creating…", "Création en cours…"),
    "thumb_ready": ("Thumbnail ready.", "Miniature prête."),
    "dl_failed": ("Download failed.", "Échec du téléchargement."),
    "wp_saved": ("Wallpaper saved:\n{path}", "Fond d'écran enregistré :\n{path}"),

    # ---- widgets / dialogs ----
    "badge_original": ("Original", "Original"),
    "badge_after": ("AI Upscaled", "Upscalé par IA"),
    "drop_placeholder": ("Drop an image here\nor click to choose one",
                         "Dépose une image ici\nou clique pour en choisir une"),
    "dlg_choose_image": ("Choose an image", "Choisir une image"),
    "filter_images": ("Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff);;All files (*)",
                      "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tiff);;Tous les fichiers (*)"),
    "filter_all_supported": ("All supported formats ({exts})",
                             "Tous les formats supportés ({exts})"),
    "dlg_save_as": ("Save as", "Enregistrer sous"),
    "replace_title": ("Replace the file?", "Remplacer le fichier ?"),
    "replace_msg": ("{name} already exists. Replace it?", "{name} existe déjà. Le remplacer ?"),

    # ---- devices ----
    "dev_auto_named": ("Auto: {name} (automatic fallback)", "Auto : {name} (repli automatique)"),
    "dev_auto": ("Auto (system default GPU)", "Auto (GPU par défaut du système)"),
    "dev_cpu": ("CPU (very slow)", "CPU (très lent)"),
    "dev_default_gpu": ("default GPU", "GPU par défaut"),

    # ---- engine / pipelines (status lines and errors) ----
    "unsupported_system": ("Unsupported system: {system}", "Système non pris en charge : {system}"),
    "dl_engine": ("Downloading the AI engine (one time only)...",
                  "Téléchargement du moteur IA (une seule fois)..."),
    "hash_mismatch": ("The downloaded file differs from the one received during a previous "
                      "installation.\nPrevious: {old}\nReceived: {new}\nAs a precaution, nothing "
                      "was installed. If you trust this new file, delete the \"sha256\" entry "
                      "from config.json.",
                      "Le fichier téléchargé diffère de celui reçu lors d'une installation "
                      "précédente.\nPrécédent : {old}\nReçu : {new}\nPar précaution, rien n'a "
                      "été installé. Si tu fais confiance à ce nouveau fichier, supprime "
                      "l'entrée \"sha256\" de config.json."),
    "extracting": ("Extracting the engine...", "Extraction du moteur..."),
    "engine_not_found": ("Engine not found after extraction.",
                         "Moteur introuvable après l'extraction."),
    "ai_pass": ("AI pass {i}/{n} (x{s})", "Passe IA {i}/{n} (x{s})"),
    "pass_on": ("{tag} on {label}...", "{tag} sur {label}..."),
    "dev_unavailable": ("{label} unavailable, trying the next one...",
                        "{label} indisponible, essai du suivant..."),
    "all_failed": ("Upscaling failed on every device tried.\n\nLast lines from the engine:\n{tail}",
                   "L'upscale a échoué sur tous les appareils essayés.\n\n"
                   "Dernières lignes du moteur :\n{tail}"),
    "webp_limit_target": ("WebP supports at most {n} pixels per side. "
                          "Choose a smaller target or another format.",
                          "WebP accepte au plus {n} pixels par côté. "
                          "Choisis une cible plus petite ou un autre format."),
    "webp_limit_export": ("WebP supports at most {n} pixels per side. "
                          "Choose PNG or JPG for this size.",
                          "WebP accepte au plus {n} pixels par côté. "
                          "Choisis PNG ou JPG pour cette taille."),
    "inter_too_large": ("Intermediate resolution too large, choose a smaller target.",
                        "Résolution intermédiaire trop grande, choisis une cible plus petite."),
    "adjusting": ("Adjusting the resolution...", "Ajustement de la résolution..."),
    "thumb_found": ("Thumbnail found: {name} ({w}x{h})", "Miniature trouvée : {name} ({w}x{h})"),
    "no_thumb": ("No thumbnail could be downloaded for video {vid}.",
                 "Aucune miniature n'a pu être téléchargée pour la vidéo {vid}."),
    "wp_source": ("Source: {w}x{h}", "Source : {w}x{h}"),
    "wp_prepared": ("Prepared: {w}x{h}", "Préparée : {w}x{h}"),
    "wp_small_source": ("Small source ({w}x{h}): expect a soft result, "
                        "a better source image will always win.",
                        "Petite source ({w}x{h}) : attends-toi à un résultat doux, "
                        "une meilleure image source gagnera toujours."),
    "wp_saved_status": ("Saved: {dst} ({w}x{h})", "Enregistré : {dst} ({w}x{h})"),
    "need_easyocr": ("Text detection needs EasyOCR:  {hint}",
                     "La détection de texte nécessite EasyOCR :  {hint}"),
    "loading_detector": ("Loading the text detector (first time: downloads the models)...",
                         "Chargement du détecteur de texte (la première fois : "
                         "téléchargement des modèles)..."),
    "detecting_text": ("Detecting text...", "Détection du texte..."),
    "text_found": ("{n} text area(s) found.", "{n} zone(s) de texte trouvée(s)."),
    "need_lama": ("Erasing needs LaMa:  {hint}", "L'effacement nécessite LaMa :  {hint}"),
    "loading_erase": ("Loading the erase model (first time: downloads it)...",
                      "Chargement du modèle d'effacement (la première fois : téléchargement)..."),
    "erasing": ("Erasing...", "Effacement..."),
    "need_np_cv": ("Erasing needs numpy and opencv:  pip install numpy opencv-python-headless",
                   "L'effacement nécessite numpy et opencv :  "
                   "pip install numpy opencv-python-headless"),
    "nothing_erase": ("Nothing to erase.", "Rien à effacer."),
    "mask_warn": ("Warning: the mask covers {pct} of the picture, the result may look blurry.",
                  "Attention : le masque couvre {pct} de l'image, le résultat peut être flou."),
}


# --------------------------------------------------------------------------- #
# French display names of the built-in choices (English text = internal key)
# --------------------------------------------------------------------------- #

NAMES_FR = {
    # config.SCREEN_PRESET / CUSTOM_PRESET
    "My screen resolution": "Résolution de mon écran",
    "Custom": "Personnalisé",
    # config.MODELS (names)
    "Anime - fast (recommended)": "Anime - rapide (recommandé)",
    "Anime - max quality": "Anime - qualité max",
    "Photo / realistic": "Photo / réaliste",
    # config.MODELS (descriptions)
    "Compact SRVGGNet architecture (16 convolutions), x2/x3/x4. Very fast, "
    "ideal for anime series and recent drawings.":
        "Architecture compacte SRVGGNet (16 convolutions), x2/x3/x4. Très rapide, "
        "idéale pour les séries d'anime et les dessins récents.",
    "Lightweight RRDBNet architecture (6 blocks), x4 only. Stronger restoration "
    "of fine lines and illustration textures. Slower.":
        "Architecture RRDBNet légère (6 blocs), x4 uniquement. Restauration plus forte "
        "des traits fins et des textures d'illustration. Plus lent.",
    "Full RRDBNet architecture (23 blocks), x4 only. For photos: reduces blur "
    "and digital noise. The slowest.":
        "Architecture RRDBNet complète (23 blocs), x4 uniquement. Pour les photos : réduit "
        "le flou et le bruit numérique. Le plus lent.",
    # config.PRESETS
    "Ultrawide - 2560x1080": "Ultra-large - 2560x1080",
    "Ultrawide QHD - 3440x1440": "Ultra-large QHD - 3440x1440",
    "Super ultrawide - 5120x1440": "Super ultra-large - 5120x1440",
    "Mobile: FHD+ (1080x2400)": "Mobile : FHD+ (1080x2400)",
    "Mobile: QHD+ (1440x3120)": "Mobile : QHD+ (1440x3120)",
    "Mobile: iPhone Standard (1179x2556)": "Mobile : iPhone Standard (1179x2556)",
    "Mobile: iPhone Pro Max / Plus (1290x2796)": "Mobile : iPhone Pro Max / Plus (1290x2796)",
    "Mobile: Samsung Galaxy Ultra (1440x3088)": "Mobile : Samsung Galaxy Ultra (1440x3088)",
    "Mobile: Standard 9:16 (1080x1920)": "Mobile : Standard 9:16 (1080x1920)",
    # config.FIT_MODES
    "Fill the screen (crops if the ratio differs)":
        "Remplir l'écran (recadre si le ratio diffère)",
    "Whole image (black bars if the ratio differs)":
        "Image entière (bandes noires si le ratio diffère)",
    # gui_wallpaper.SHRINK_CHOICES
    "Off": "Désactivé",
    "Divide by 1.5": "Diviser par 1,5",
    "Divide by 2 (enlarged thumbnail)": "Diviser par 2 (miniature agrandie)",
    "Divide by 3": "Diviser par 3",
    # cleanup.ZONE_PRESETS / ZONE_MODES
    "No zone": "Aucune zone",
    "Bottom third (visualizer)": "Tiers inférieur (visualiseur)",
    "Bottom half (visualizer)": "Moitié inférieure (visualiseur)",
    "Middle band (visualizer)": "Bande centrale (visualiseur)",
    "Top-left corner (logo)": "Coin haut gauche (logo)",
    "Top-right corner (logo)": "Coin haut droit (logo)",
    "Bottom-left corner (logo)": "Coin bas gauche (logo)",
    "Bottom-right corner (logo)": "Coin bas droit (logo)",
    "Whole zone": "Toute la zone",
    "Bright pixels only (sound bars)": "Pixels clairs seulement (barres son)",
}


init_lang()  # use the language saved in config.json as soon as the module is imported
