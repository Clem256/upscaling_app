# AI Upscale Studio

**🇫🇷 [Français](#-français) · 🇬🇧 [English](#-english)**

---

# 🇫🇷 Français

Application de bureau (PyQt6) qui agrandit des images avec l'IA **Real-ESRGAN** (moteur `realesrgan-ncnn-vulkan`, exécuté sur le GPU via Vulkan). Elle permet d'obtenir des fonds d'écran PC, ultrawide ou téléphone à partir d'images de petite taille, et de transformer des miniatures YouTube en fonds d'écran propres.

## Sommaire

1. [Fonctionnalités](#fonctionnalités)
2. [Installation](#installation)
3. [Lancement](#lancement)
4. [Utilisation : onglet Upscaler](#utilisation--onglet-upscaler)
5. [Utilisation : onglet Wallpaper maker](#utilisation--onglet-wallpaper-maker)
6. [Onglet Monitoring & Modèles](#onglet-monitoring--modèles)
7. [Souris et raccourcis](#souris-et-raccourcis)
8. [Modèles d'IA](#modèles-dia)
9. [Résolutions prédéfinies](#résolutions-prédéfinies)
10. [Fonctionnement interne](#fonctionnement-interne)
11. [Ligne de commande (wallpaper.py)](#ligne-de-commande-wallpaperpy)
12. [Structure du projet](#structure-du-projet)
13. [Dépannage](#dépannage)
14. [Crédits](#crédits)

## Fonctionnalités

- **Upscaler** : agrandit n'importe quelle image vers une résolution cible (presets PC / ultrawide / 8K / téléphones, ou taille libre), avec choix du modèle, du GPU, du ratio et du format de sortie.
- **Wallpaper maker** : pipeline dédié aux sources de mauvaise qualité (miniatures YouTube, petits JPEG) : récupération de la meilleure miniature, suppression des bandes noires, recadrage, nettoyage JPEG, une passe IA, netteté et grain finaux, et effacement optionnel de texte / logos / barres de visualiseur audio.
- **Aperçu avant / après avant téléchargement** : à la fin d'un traitement, le résultat s'affiche avec une barre de séparation que tu déplaces de gauche à droite (original d'un côté, image upscalée de l'autre). Rien n'est enregistré tant que tu ne cliques pas sur **Télécharger**.
- **Monitoring** : CPU, RAM, GPU NVIDIA (si `nvidia-smi` est présent) et réseau en direct, plus le détail du modèle actif.
- **Interface bilingue** : bouton **EN | FR** en haut à droite, changement immédiat (anglais par défaut). Le choix est mémorisé dans `config.json`.
- **Multi-plateforme** : Windows, Linux, macOS.
- **Moteur téléchargé automatiquement** (~30 Mo) au premier usage, avec vérification d'empreinte SHA-256.

## Installation

### Prérequis

- **Python 3.9 ou plus récent**.
- Un **GPU compatible Vulkan** avec des pilotes à jour (fortement recommandé ; sans GPU, le mode CPU fonctionne mais est *très* lent).
- Une connexion internet au premier lancement (téléchargement du moteur) et pour récupérer des miniatures YouTube.

### Dépendances Python

```bash
pip install PyQt6 pillow psutil numpy opencv-python-headless
```

| Paquet | Obligatoire ? | Rôle |
|---|---|---|
| `PyQt6` | Oui | Interface graphique |
| `pillow` | Oui | Lecture / écriture / traitement des images |
| `psutil` | Recommandé | Onglet Monitoring |
| `numpy` + `opencv-python-headless` | Recommandé | Wallpaper maker : suppression des bandes noires, nettoyage JPEG, grain |

> Tkinter n'est plus nécessaire : l'interface est entièrement en PyQt6.

### Effacement de texte / logos (optionnel, lourd)

Nécessaire uniquement pour la section « Effacer texte / logos / barres son » du Wallpaper maker :

```bash
pip install torch torchvision easyocr
pip install --no-deps simple-lama-inpainting
```

- `--no-deps` est volontaire : `simple-lama-inpainting` impose de vieilles versions de numpy et Pillow qui casseraient le reste du projet. Son code fonctionne avec les versions récentes.
- PyTorch est un gros téléchargement (~2 Go sous Windows / Linux). Il utilise le GPU CUDA s'il le voit, sinon le CPU.
- Au premier usage, les modèles sont téléchargés (OCR ~100 Mo, LaMa ~200 Mo). L'OCR lit l'anglais et le japonais.

### Le moteur Real-ESRGAN

Rien à installer à la main. Au premier upscale, l'application télécharge le moteur officiel (`realesrgan-ncnn-vulkan`, version 20220424, depuis la release `v0.2.5.0` de `xinntao/Real-ESRGAN`) dans le dossier `./upscaler` à côté de `app.py`.

Sécurité : l'empreinte SHA-256 du zip est calculée puis enregistrée dans `config.json` (par plateforme). Si un téléchargement ultérieur donne un fichier différent, il est **refusé** et rien n'est installé. Si tu fais confiance au nouveau fichier, supprime l'entrée `"sha256"` de `config.json`.

## Lancement

```bash
python app.py
```

## Utilisation : onglet Upscaler

1. **Image importée** : clique sur *Choisir…* ou **glisse-dépose** une image sur la zone d'aperçu. Formats lus : PNG, JPG, WebP, BMP, TIFF. L'orientation EXIF est respectée.
2. **Taille voulue** : au choix
   - **Échelle rapide 2× / 4× / 8×** : la cible devient la taille de l'image × le facteur ;
   - **Résolution cible** : un preset (voir [la liste](#résolutions-prédéfinies)), ou « My screen resolution » pour la définition de ton écran, ou « Custom » ;
   - **Largeur / Hauteur** : saisie libre.
3. **Modèle d'IA, Appareil, Ratio, Format de sortie** (voir le tableau ci-dessous).
4. Le résumé en bas indique le passage de la taille source à la taille cible, le facteur d'agrandissement et les passes IA prévues.
5. Clique sur **Upscaler** : le traitement démarre et écrit le résultat dans un fichier **temporaire** (rien n'est enregistré chez toi). **Annuler** l'interrompt (le moteur est arrêté).
6. À la fin, le résultat s'affiche dans le comparateur : **déplace la barre blanche** de gauche à droite pour voir l'image d'origine d'un côté et l'image upscalée de l'autre.
7. Si le résultat te convient, clique sur **Télécharger** : choisis l'emplacement et le format (PNG / JPG / WebP) dans la fenêtre « Enregistrer sous ». Sinon, change un réglage et relance **Upscaler**.

> Le comparateur travaille sur un aperçu réduit (1600 px maximum de côté) pour rester fluide ; le fichier enregistré, lui, est à la résolution cible complète. Si tu modifies un réglage qui change le résultat (taille, modèle, ratio, image...), l'aperçu est retiré et **Télécharger** se désactive jusqu'au prochain upscale.

### Paramètres

| Paramètre | Valeurs | Effet |
|---|---|---|
| Échelle rapide | 2×, 4×, 8× | Remplit largeur / hauteur à partir de l'image. Se met en surbrillance si la cible correspond. |
| Résolution cible | presets, écran, Custom | Remplit largeur / hauteur. |
| Largeur / Hauteur | 16 à 16 384 px | Taille exacte du fichier final. |
| Modèle d'IA | voir [Modèles](#modèles-dia) | Détermine la qualité, la vitesse et les échelles possibles. |
| Appareil | Auto, GPU n, CPU | Où le moteur s'exécute. Le bouton ↻ relance la détection des GPU. |
| Ratio | *Fill* / *Fit* | **Fill** : l'image couvre toute la cible, l'excédent est recadré au centre. **Fit** : l'image entière est conservée, avec des barres noires si le ratio diffère. |
| Format de sortie | PNG, JPG, WebP | Appliqué au moment du **Télécharger**. PNG sans perte ; JPG et WebP en qualité 95 (JPG sans sous-échantillonnage de la chrominance, WebP avec la compression la plus poussée). |

## Utilisation : onglet Wallpaper maker

Pensé pour les sources de mauvaise qualité. Ordre du traitement : récupération → bandes noires → recadrage → effacement → réduction de la source → nettoyage JPEG → passe(s) IA → taille exacte → netteté → grain → aperçu. Comme dans l'Upscaler, le résultat est d'abord affiché dans le comparateur avant / après (clique sur **Créer le fond d'écran**, compare, puis **Télécharger** pour l'enregistrer).

### 1. Source

- Colle un **lien YouTube** (`watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/`) ou un **identifiant de 11 caractères**, puis *Récupérer la miniature* (ou touche **Entrée** dans le champ). L'appli essaie `maxresdefault`, `hq720`, `sddefault`, `hqdefault` et garde la plus grande.
- Ou *Choisir un fichier…* / glisser-déposer une image locale. Tu peux aussi coller un chemin de fichier dans le champ.
- Les bandes noires (letterbox / pillarbox) sont détectées et retirées automatiquement (nécessite numpy + opencv).

### 2. Résolution cible

Comme dans l'Upscaler. Par défaut : 4K (3840×2160).

### 3. Options

| Paramètre | Défaut | Effet |
|---|---|---|
| Modèle d'IA | *Anime - max quality* | Voir [Modèles](#modèles-dia). |
| Appareil | Auto | Comme dans l'Upscaler. |
| Ratio | Fill | Voir ci-dessus. En *Fill*, le recadrage se fait **avant** l'IA : aucun pixel n'est gaspillé sur ce qui sera coupé. |
| Format de sortie | PNG | PNG, JPG ou WebP. |
| Passes IA | Auto | Auto : une seule passe sauf si elle laisserait plus de 25 % à combler par simple interpolation (jamais plus de 2 passes, jamais au-delà de 16 384 px ou environ 70 mégapixels). 1, 2 ou 3 : maximum imposé. |

### 4. Nettoyage et cadrage

| Paramètre | Plage (défaut) | Effet |
|---|---|---|
| Nettoyage JPEG | 0 à 8 (0) | Débruitage léger avant l'IA pour atténuer les blocs JPEG. 2 à 4 = discret ; au-delà de 6, les lignes fines disparaissent. |
| Grain final | 0 à 6 (2) | Grain très fin ajouté à la fin pour atténuer l'aspect « plastique » de l'IA. |
| Netteté finale | 0 à 100 (40) | Double masque flou (fin + large) qui redonne du micro-contraste. |
| Réduire la source avant l'IA | Désactivé, ÷1,5, ÷2, ÷3 | À essayer quand une petite source paraît floue : annule l'agrandissement qu'applique YouTube à une très petite miniature, pour que l'IA travaille sur de vrais pixels. |
| Cadrage horizontal / vertical | 0 à 100 % (50) | Quelle partie de l'image garder quand le ratio diffère (en mode *Fill*). L'aperçu se met à jour en direct. |

### 5. Effacer texte / logos / barres son (option)

Retire titres, crédits, logos et visualiseurs audio **avant** l'agrandissement (l'IA accentuerait sinon les contours des lettres, plus difficiles à effacer ensuite). Principe : un masque est construit, élargi de quelques pixels, puis le fond est reconstruit par LaMa.

| Paramètre | Effet |
|---|---|
| Effacer le texte par OCR | Détecte et efface le texte (anglais + japonais). |
| Zone | Rectangle à effacer : preset (*Bottom third*, *Top-left corner (logo)*, etc.) ou *Custom*. |
| Sélectionner la zone sur l'image | Clique sur le bouton puis **trace un rectangle** directement sur l'aperçu : les coordonnées G / H / D / B se remplissent toutes seules et la zone passe en *Custom*. |
| G / H / D / B (%) | Coordonnées de la zone en pourcentage de l'image conservée : gauche, haut, droite, bas. Modifier une valeur à la main passe la zone en *Custom*. La zone s'affiche **en rouge** dans l'aperçu. |
| Effacer | *Whole zone* : toute la zone. *Bright pixels only* : seulement les pixels clairs (barres de visualiseur). |
| Luminosité à partir de | Seuil (100 à 255) du mode « pixels clairs ». |
| Sensibilité du texte | 0,05 à 0,80 (0,15). Bas = efface davantage (risque d'effacer aussi des motifs du dessin) ; haut = uniquement le texte très net. |

Si les paquets d'effacement ne sont pas installés, un avertissement s'affiche dans cette section et le traitement est refusé tant que l'effacement est activé.

## Onglet Monitoring & Modèles

- **Détails du modèle actif** : nom du moteur, échelles possibles et description du modèle choisi dans l'onglet Upscaler.
- **Utilisation système** (mise à jour toutes les 2 s) : CPU, RAM, carte NVIDIA (usage et VRAM, via `nvidia-smi`) et débit réseau **de toute la machine** (indicatif). Sans `psutil`, l'onglet affiche un message d'installation.

## Souris et raccourcis

Il n'y a **pas de raccourcis clavier** dédiés. Les interactions disponibles :

| Action | Effet |
|---|---|
| Glisser-déposer un fichier sur l'aperçu | Charge l'image (Upscaler et Wallpaper maker). |
| Clic sur l'aperçu vide | Ouvre la fenêtre de choix d'image. |
| Glisser la barre blanche du comparateur | Déplace la séparation avant / après (disponible une fois l'aperçu généré). |
| **Entrée** dans le champ du lien YouTube | Récupère la miniature. |
| Molette de la souris | Fait défiler le panneau de réglages (les listes et curseurs ignorent volontairement la molette, pour éviter de changer une valeur par erreur). |
| Bouton ↻ à côté de « Appareil » | Relance la détection des GPU. |

## Modèles d'IA

| Nom affiché | Modèle moteur | Échelles | Description |
|---|---|---|---|
| Anime - fast (recommended) | `realesr-animevideov3` | ×2, ×3, ×4 | Architecture compacte SRVGGNet (16 convolutions). Très rapide, idéal pour les séries animées et les dessins récents. |
| Anime - max quality | `realesrgan-x4plus-anime` | ×4 | RRDBNet léger (6 blocs). Restaure mieux les traits fins et les textures d'illustration. Plus lent. |
| Photo / realistic | `realesrgan-x4plus` | ×4 | RRDBNet complet (23 blocs). Pour les photos : réduit le flou et le bruit numérique. Le plus lent. |

## Résolutions prédéfinies

- **Écrans / TV** : Full HD 1920×1080, 2K/QHD 2560×1440, 4K/UHD 3840×2160, Ultrawide 2560×1080, Ultrawide QHD 3440×1440, Super ultrawide 5120×1440, 8K 7680×4320.
- **Téléphones (vertical)** : FHD+ 1080×2400, QHD+ 1440×3120, iPhone standard 1179×2556, iPhone Pro Max / Plus 1290×2796, Samsung Galaxy Ultra 1440×3088, 9:16 standard 1080×1920.
- **My screen resolution** (définition de ton écran) et **Custom**.

Pour ajouter un preset, modifie le dictionnaire `PRESETS` dans `config.py`.

## Fonctionnement interne

### Upscaler

1. L'image est relue avec Pillow (orientation EXIF, conversion RGB).
2. `needed_factor` calcule l'agrandissement nécessaire selon le mode (*fill* : l'image doit couvrir la cible ; *fit* : elle doit tenir dedans).
3. `plan_passes` choisit la chaîne de passes IA (3 au maximum) : à chaque étape, la plus petite échelle du modèle qui couvre le reste, ou la plus grande si aucune ne suffit. Exemple avec un modèle ×4 : un agrandissement de 6× donne ×4 puis ×4.
4. Chaque passe lance le moteur dans un sous-processus. La progression est lue dans sa sortie (`37.50%`).
5. `finalize` redimensionne (Lanczos) puis recadre ou ajoute des barres noires pour obtenir **exactement** la taille cible.
6. Le résultat est écrit en PNG temporaire (aperçu). Au clic sur **Télécharger**, `export.py` l'enregistre dans le format choisi (PNG : simple copie ; JPG / WebP : qualité 95).

Garde-fous : refus si une dimension intermédiaire dépasse 16 384 px ; WebP limité à 16 383 px par côté (vérifié au moment du téléchargement) ; si aucun agrandissement n'est nécessaire, simple redimensionnement.

### Choix du périphérique et repli automatique

- **Auto** : sous Linux avec `nvidia-smi`, le pilote NVIDIA est forcé en premier (utile sur un portable hybride), puis repli sur le GPU par défaut du système. Ailleurs, GPU par défaut du système.
- **GPU n** : essaie le GPU n, puis le GPU par défaut.
- **CPU** : très lent.
- Les GPU sont détectés en lançant le moteur sur une image de 16×16 px et en lisant la liste qu'il affiche.

### Fils d'exécution (threads)

Les widgets ne sont touchés que par le fil de l'interface. Les traitements (upscale, détection des GPU, monitoring, téléchargements) tournent dans des threads qui envoient des messages `(type, valeur)` via `app.q.put(...)`. La classe `SignalQueue` (dans `widgets.py`) les convertit en signaux Qt reçus dans le fil de l'interface. Un seul traitement à la fois est autorisé (upscale ou fond d'écran).

## Ligne de commande (wallpaper.py)

Le pipeline du Wallpaper maker s'utilise aussi sans interface :

```bash
python wallpaper.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"
python wallpaper.py cover.jpg -r 2560x1440 --model "Anime - max quality"
python wallpaper.py VIDEO_ID -r 1440x3120 --focus-x 0.3     # téléphone, sujet à gauche
```

| Option | Défaut | Description |
|---|---|---|
| `source` | — | Lien YouTube, identifiant ou chemin d'image. |
| `-o`, `--output` | `<nom>_<l>x<h>.png` | Fichier de sortie. |
| `-r`, `--resolution` | `3840x2160` | `LARGEURxHAUTEUR` ou nom (partiel) d'un preset. |
| `--model` | `Anime - max quality` | Un des modèles du tableau ci-dessus. |
| `--device` | `auto` | `auto`, `cpu` ou un index de GPU. |
| `--mode` | `fill` | `fill` ou `fit`. |
| `--denoise` | `0` | Nettoyage JPEG, 0 à 8. |
| `--grain` | `2` | Grain final, 0 à 6. |
| `--sharpen` | `40` | Netteté finale, 0 à 100. |
| `--passes` | `0` | 0 = auto, sinon 1 à 3. |
| `--shrink` | `1` | Réduit la source de ce facteur avant l'IA (ex. `2`). |
| `--focus-x`, `--focus-y` | `0.5` | Partie conservée au recadrage, de 0 à 1. |
| `--erase-text` | désactivé | Efface le texte (OCR + LaMa). |
| `--ocr-conf` | `0.15` | Confiance de détection du texte, 0,05 à 0,8. |
| `--zone` | — | `x0,y0,x1,y1` en pourcents (ex. `0,66,100,100`) ou nom d'un preset de zone. |
| `--zone-mode` | `whole` | `whole` ou `bright`. |
| `--zone-bright` | `200` | Seuil de luminosité du mode `bright`. |
| `--keep-source` | désactivé | Garde la miniature téléchargée à côté du résultat. |

## Structure du projet

```
app.py            Point d'entrée.
config.py         Constantes (plateforme, chemins, URLs, modèles, presets) et lecture / écriture de config.json.
i18n.py           Langue de l'interface (EN / FR) : tr(), tr_name() et tous les textes.
control.py        Annulation (Cancelled, Control).
devices.py        Libellés GPU / CPU et ordre de repli.
engine.py         Moteur Real-ESRGAN : installation (téléchargement + SHA-256 + extraction) et exécution.
upscale.py        Planification des passes, redimensionnement final, pipeline complet.
monitor.py        Surveillance CPU / RAM / GPU / réseau en arrière-plan.
wallpaper.py      Pipeline Wallpaper maker (aussi utilisable en ligne de commande).
cleanup.py        Effacement optionnel de texte / logos (OCR + LaMa).
theme.py          Palette sombre Fusion + feuille de style (QSS).
widgets.py        Widgets réutilisables : comparateur, contrôles segmentés, curseurs, dialogues, SignalQueue.
export.py         Enregistrement du résultat temporaire (PNG) dans le format choisi au téléchargement.
gui.py            Fenêtre principale (App), onglets Upscaler et Monitoring.
gui_wallpaper.py  Onglet Wallpaper maker.
config.json       Créé automatiquement : empreinte SHA-256 du moteur et langue choisie.
upscaler/         Créé automatiquement : moteur Real-ESRGAN.
```

Sens des dépendances (sans cycle) : `config` ← `i18n`, `control`, `devices`, `monitor` ; `i18n` ← tous les modules qui affichent du texte ; `engine` → `config`, `control`, `devices` ; `upscale` → `config`, `engine` ; `widgets` → `config` ; `export` → `config` ; `gui_wallpaper` → `widgets`, `export` et les modules précédents ; `gui` → `gui_wallpaper`, `export` et les modules précédents ; `app` → `gui`, `theme`.

## Dépannage

| Problème | Cause probable / solution |
|---|---|
| « The downloaded file differs from the one received during a previous installation » | L'empreinte du moteur a changé. Si tu fais confiance au nouveau fichier, supprime l'entrée `"sha256"` de `config.json` et relance. |
| Aucun GPU détecté | Installe ou mets à jour les pilotes Vulkan de ta carte, puis clique sur ↻. En attendant, utilise *Auto* ou *CPU*. |
| Le traitement est très lent | Tu es probablement en mode CPU ou sur un GPU logiciel (llvmpipe). Choisis le bon GPU dans « Appareil ». Le modèle *Photo / realistic* est aussi le plus lent. |
| « Upscaling failed on every device tried » | Le moteur a échoué sur tous les périphériques. Les dernières lignes de sa sortie sont affichées : souvent un pilote Vulkan manquant ou une VRAM insuffisante. Essaie une cible plus petite ou le mode CPU. |
| « Intermediate resolution too large » | La chaîne de passes dépasserait 16 384 px. Choisis une cible plus petite. |
| « WebP supports at most 16383 pixels per side » | Limite du format WebP, signalée au moment du **Télécharger** : réessaie en PNG ou JPG (le résultat affiché n'est pas perdu). |
| « Module psutil manquant » | `pip install psutil`. |
| Le Wallpaper maker n'enlève pas les bandes noires / ne met pas de grain | `pip install numpy opencv-python-headless`. |
| « Effacement non installé » | Voir [Effacement de texte / logos](#effacement-de-texte--logos-optionnel-lourd), ou décoche les options d'effacement. |
| Résultat « plastique » ou trop lissé | Baisse le nettoyage JPEG, augmente le grain (1 à 3) et la netteté, ou essaie une seule passe. |
| Texte résiduel après l'effacement | Baisse la *Sensibilité du texte* ou ajoute une zone en *Whole zone*. |

## Crédits

Moteur d'agrandissement : [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (xinntao), version NCNN / Vulkan. Effacement : [EasyOCR](https://github.com/JaidedAI/EasyOCR) et LaMa (via `simple-lama-inpainting`). Interface : PyQt6.

---

# 🇬🇧 English

Desktop application (PyQt6) that enlarges images with the **Real-ESRGAN** AI (the `realesrgan-ncnn-vulkan` engine, run on the GPU through Vulkan). Use it to produce PC, ultrawide or phone wallpapers from small images, and to turn YouTube thumbnails into clean wallpapers.

## Contents

1. [Features](#features)
2. [Installation](#installation)
3. [Running](#running)
4. [Usage: Upscaler tab](#usage-upscaler-tab)
5. [Usage: Wallpaper maker tab](#usage-wallpaper-maker-tab)
6. [Monitoring & Models tab](#monitoring--models-tab)
7. [Mouse and shortcuts](#mouse-and-shortcuts)
8. [AI models](#ai-models)
9. [Resolution presets](#resolution-presets)
10. [How it works](#how-it-works)
11. [Command line (wallpaper.py)](#command-line-wallpaperpy)
12. [Project layout](#project-layout)
13. [Troubleshooting](#troubleshooting)
14. [Credits](#credits)

## Features

- **Upscaler**: enlarges any image to a target resolution (PC / ultrawide / 8K / phone presets, or a custom size), with a choice of model, GPU, aspect handling and output format.
- **Wallpaper maker**: a pipeline built for low-quality sources (YouTube thumbnails, small JPEGs): fetches the best thumbnail, removes black bars, crops, cleans JPEG artifacts, runs one AI pass, applies final sharpness and grain, and can optionally erase text / logos / audio-visualizer bars.
- **Before / after preview before downloading**: when a job ends, the result is shown with a divider you drag left and right (original on one side, upscaled image on the other). Nothing is saved until you click **Download**.
- **Monitoring**: live CPU, RAM, NVIDIA GPU (when `nvidia-smi` is available) and network, plus details of the active model.
- **Bilingual interface**: an **EN | FR** switch in the top-right corner applies instantly (English by default); the choice is remembered in `config.json`.
- **Cross-platform**: Windows, Linux, macOS.
- **Engine downloaded automatically** (~30 MB) on first use, with SHA-256 verification.

## Installation

### Requirements

- **Python 3.9 or newer**.
- A **Vulkan-capable GPU** with up-to-date drivers (strongly recommended; without a GPU, CPU mode works but is *very* slow).
- An internet connection on first launch (engine download) and to fetch YouTube thumbnails.

### Python dependencies

```bash
pip install PyQt6 pillow psutil numpy opencv-python-headless
```

| Package | Required? | Purpose |
|---|---|---|
| `PyQt6` | Yes | Graphical interface |
| `pillow` | Yes | Reading / writing / processing images |
| `psutil` | Recommended | Monitoring tab |
| `numpy` + `opencv-python-headless` | Recommended | Wallpaper maker: black-bar removal, JPEG cleanup, grain |

> Tkinter is no longer needed: the interface is entirely PyQt6.

### Erasing text / logos (optional, heavy)

Only needed for the "Erase text / logos / sound bars" section of the Wallpaper maker:

```bash
pip install torch torchvision easyocr
pip install --no-deps simple-lama-inpainting
```

- `--no-deps` is deliberate: `simple-lama-inpainting` pins very old numpy and Pillow versions that would break the rest of the project. Its code works fine with recent ones.
- PyTorch is a large download (~2 GB on Windows / Linux). It uses the CUDA GPU when it can see one, otherwise the CPU.
- Models are downloaded on first use (OCR ~100 MB, LaMa ~200 MB). The OCR reads English and Japanese.

### The Real-ESRGAN engine

Nothing to install by hand. On the first upscale, the application downloads the official engine (`realesrgan-ncnn-vulkan`, build 20220424, from the `v0.2.5.0` release of `xinntao/Real-ESRGAN`) into the `./upscaler` folder next to `app.py`.

Security: the zip's SHA-256 is computed and stored in `config.json` (per platform). If a later download produces a different file, it is **rejected** and nothing is installed. If you trust the new file, delete the `"sha256"` entry from `config.json`.

## Running

```bash
python app.py
```

## Usage: Upscaler tab

1. **Imported image**: click *Choose…* or **drag and drop** an image onto the preview area. Supported formats: PNG, JPG, WebP, BMP, TIFF. EXIF orientation is honored.
2. **Wanted size**, either:
   - **Quick scale 2× / 4× / 8×**: the target becomes the image size × the factor;
   - **Target resolution**: a preset (see [the list](#resolution-presets)), "My screen resolution" for your display's size, or "Custom";
   - **Width / Height**: free entry.
3. **AI model, Device, Ratio, Output format** (see the table below).
4. The summary at the bottom shows the source → target sizes, the enlargement factor and the planned AI passes.
5. Click **Upscaler**: processing starts and writes the result to a **temporary** file (nothing is saved on your disk). **Cancel** stops it (the engine process is terminated).
6. When it finishes, the result appears in the comparison: **drag the white divider** left and right to see the original image on one side and the upscaled one on the other.
7. If you like the result, click **Download**: pick the location and the format (PNG / JPG / WebP) in the "Save as" dialog. Otherwise, change a setting and run **Upscaler** again.

> The comparison works on a reduced preview (1600 px max per side) to stay smooth; the saved file is at the full target resolution. If you change a setting that affects the result (size, model, ratio, image...), the preview is dropped and **Download** is disabled until the next upscale.

### Parameters

| Parameter | Values | Effect |
|---|---|---|
| Quick scale | 2×, 4×, 8× | Fills width / height from the image. Highlights itself when the target matches. |
| Target resolution | presets, screen, Custom | Fills width / height. |
| Width / Height | 16 to 16,384 px | Exact size of the final file. |
| AI model | see [Models](#ai-models) | Sets quality, speed and the possible scales. |
| Device | Auto, GPU n, CPU | Where the engine runs. The ↻ button re-runs GPU detection. |
| Ratio | *Fill* / *Fit* | **Fill**: the image covers the whole target and the overflow is center-cropped. **Fit**: the whole image is kept, with black bars if the ratio differs. |
| Output format | PNG, JPG, WebP | Applied when you click **Download**. PNG is lossless; JPG and WebP use quality 95 (JPG without chroma subsampling, WebP with the slowest / best compression). |

## Usage: Wallpaper maker tab

Built for low-quality sources. Processing order: fetch → black bars → crop → erase → shrink source → JPEG cleanup → AI pass(es) → exact size → sharpness → grain → preview. As in the Upscaler, the result is first shown in the before / after comparison (click **Create wallpaper**, compare, then **Download** to save it).

### 1. Source

- Paste a **YouTube link** (`watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/`) or an **11-character video id**, then *Fetch thumbnail*, or press **Enter** in the field. The app tries `maxresdefault`, `hq720`, `sddefault`, `hqdefault` and keeps the largest.
- Or *Choose a file…* / drag and drop a local image. You can also paste a file path into the field.
- Black bars (letterbox / pillarbox) are detected and removed automatically (needs numpy + opencv).

### 2. Target resolution

Same as the Upscaler. Default: 4K (3840×2160).

### 3. Options

| Parameter | Default | Effect |
|---|---|---|
| AI model | *Anime - max quality* | See [Models](#ai-models). |
| Device | Auto | Same as the Upscaler. |
| Ratio | Fill | See above. In *Fill*, cropping happens **before** the AI, so no pixels are wasted on what gets cut. |
| Output format | PNG | PNG, JPG or WebP. |
| AI passes | Auto | Auto: a single pass, unless it would leave more than 25% to be filled by plain interpolation (never more than 2 passes, never beyond 16,384 px or about 70 megapixels). 1, 2 or 3: enforced maximum. |

### 4. Cleaning and framing

| Parameter | Range (default) | Effect |
|---|---|---|
| JPEG cleanup | 0 to 8 (0) | Light denoise before the AI to soften JPEG blocks. 2–4 is subtle; above 6, fine lines start to disappear. |
| Final grain | 0 to 6 (2) | Very fine grain added at the end to hide the "plastic" look of AI output. |
| Final sharpness | 0 to 100 (40) | Double unsharp mask (fine + broad) that restores micro-contrast. |
| Shrink source first | Off, ÷1.5, ÷2, ÷3 | Try it when a small source looks fuzzy: it undoes the enlargement YouTube applies to a tiny thumbnail so the AI works on real pixels. |
| Crop horizontal / vertical | 0 to 100% (50) | Which part of the image to keep when the ratio differs (in *Fill* mode). The preview updates live. |

### 5. Erase text / logos / sound bars (optional)

Removes titles, credits, logos and audio visualizers **before** upscaling (otherwise the AI would sharpen the letter edges, making them harder to erase). How it works: a mask is built, grown by a few pixels, then LaMa rebuilds the background.

| Parameter | Effect |
|---|---|
| Erase text with OCR | Detects and erases text (English + Japanese). |
| Zone | Rectangle to erase: a preset (*Bottom third*, *Top-left corner (logo)*, etc.) or *Custom*. |
| Select zone on the image | Click the button, then **drag a rectangle** directly on the preview: the L / T / R / B fields fill in automatically and the zone switches to *Custom*. |
| G / H / D / B (%) | Zone coordinates as a percentage of the kept picture: left (L), top (T), right (R), bottom (B). Editing a value by hand switches the zone to *Custom*. The zone is shown **in red** in the preview. |
| Erase | *Whole zone*: the entire rectangle. *Bright pixels only*: only the bright pixels (visualizer bars). |
| Brightness from | Threshold (100 to 255) for the "bright pixels" mode. |
| Text sensitivity | 0.05 to 0.80 (0.15). Low = erases more (risk of also erasing art patterns); high = only clearly readable text. |

If the erase packages are not installed, a warning appears in this section and processing is refused while erasing is enabled.

## Monitoring & Models tab

- **Active model details**: engine name, possible scales and description of the model selected in the Upscaler tab.
- **Live system usage** (refreshed every 2 s): CPU, RAM, NVIDIA card (usage and VRAM, via `nvidia-smi`) and network throughput of the **whole machine** (indicative). Without `psutil`, the tab shows an install message.

## Mouse and shortcuts

There are **no dedicated keyboard shortcuts**. Available interactions:

| Action | Effect |
|---|---|
| Drag and drop a file onto the preview | Loads the image (Upscaler and Wallpaper maker). |
| Click the empty preview | Opens the image picker. |
| Drag the white divider of the comparison | Moves the before / after split (available once the preview is generated). |
| **Enter** in the YouTube link field | Fetches the thumbnail. |
| Mouse wheel | Scrolls the settings panel (dropdowns and sliders intentionally ignore the wheel, so a value never changes by accident). |
| ↻ button next to "Device" | Re-runs GPU detection. |

## AI models

| Displayed name | Engine model | Scales | Description |
|---|---|---|---|
| Anime - fast (recommended) | `realesr-animevideov3` | ×2, ×3, ×4 | Compact SRVGGNet architecture (16 convolutions). Very fast, ideal for anime series and recent drawings. |
| Anime - max quality | `realesrgan-x4plus-anime` | ×4 | Lightweight RRDBNet (6 blocks). Better restoration of fine lines and illustration textures. Slower. |
| Photo / realistic | `realesrgan-x4plus` | ×4 | Full RRDBNet (23 blocks). For photos: reduces blur and digital noise. The slowest. |

## Resolution presets

- **Screens / TVs**: Full HD 1920×1080, 2K/QHD 2560×1440, 4K/UHD 3840×2160, Ultrawide 2560×1080, Ultrawide QHD 3440×1440, Super ultrawide 5120×1440, 8K 7680×4320.
- **Phones (vertical)**: FHD+ 1080×2400, QHD+ 1440×3120, iPhone Standard 1179×2556, iPhone Pro Max / Plus 1290×2796, Samsung Galaxy Ultra 1440×3088, Standard 9:16 1080×1920.
- **My screen resolution** (your display's size) and **Custom**.

To add a preset, edit the `PRESETS` dictionary in `config.py`.

## How it works

### Upscaler

1. The image is re-read with Pillow (EXIF orientation, RGB conversion).
2. `needed_factor` computes the required enlargement for the mode (*fill*: the image must cover the target; *fit*: it must fit inside).
3. `plan_passes` picks the chain of AI passes (3 at most): at each step, the smallest scale of the model that covers what remains, or the largest if none is enough. Example with a ×4 model: a 6× enlargement gives ×4 then ×4.
4. Each pass runs the engine in a subprocess. Progress is read from its output (`37.50%`).
5. `finalize` resizes (Lanczos) then crops or adds black bars to reach **exactly** the target size.
6. The result is written as a temporary PNG (preview). When you click **Download**, `export.py` saves it in the chosen format (PNG: plain copy; JPG / WebP: quality 95).

Safeguards: refused if an intermediate dimension exceeds 16,384 px; WebP is limited to 16,383 px per side (checked when downloading); if no enlargement is needed, a plain resize is done.

### Device selection and automatic fallback

- **Auto**: on Linux with `nvidia-smi`, the NVIDIA driver is forced first (useful on hybrid laptops), then falls back to the system's default GPU. Elsewhere, the system's default GPU.
- **GPU n**: tries GPU n, then the default GPU.
- **CPU**: very slow.
- GPUs are detected by running the engine on a 16×16 px image and reading the list it prints.

### Threads

Widgets are only touched by the interface thread. Jobs (upscale, GPU detection, monitoring, downloads) run in threads that send `(kind, value)` messages through `app.q.put(...)`. The `SignalQueue` class (in `widgets.py`) turns them into Qt signals received in the interface thread. Only one job at a time is allowed (upscale or wallpaper).

## Command line (wallpaper.py)

The Wallpaper maker pipeline can also be used without the interface:

```bash
python wallpaper.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"
python wallpaper.py cover.jpg -r 2560x1440 --model "Anime - max quality"
python wallpaper.py VIDEO_ID -r 1440x3120 --focus-x 0.3     # phone, subject on the left
```

| Option | Default | Description |
|---|---|---|
| `source` | — | YouTube URL, video id or image path. |
| `-o`, `--output` | `<name>_<w>x<h>.png` | Output file. |
| `-r`, `--resolution` | `3840x2160` | `WIDTHxHEIGHT` or a (partial) preset name. |
| `--model` | `Anime - max quality` | One of the models in the table above. |
| `--device` | `auto` | `auto`, `cpu` or a GPU index. |
| `--mode` | `fill` | `fill` or `fit`. |
| `--denoise` | `0` | JPEG cleanup, 0 to 8. |
| `--grain` | `2` | Final grain, 0 to 6. |
| `--sharpen` | `40` | Final sharpening, 0 to 100. |
| `--passes` | `0` | 0 = auto, otherwise 1 to 3. |
| `--shrink` | `1` | Shrinks the source by this factor before the AI (e.g. `2`). |
| `--focus-x`, `--focus-y` | `0.5` | Which part to keep when cropping, 0 to 1. |
| `--erase-text` | off | Erases text (OCR + LaMa). |
| `--ocr-conf` | `0.15` | Text detection confidence, 0.05 to 0.8. |
| `--zone` | — | `x0,y0,x1,y1` in percent (e.g. `0,66,100,100`) or a zone preset name. |
| `--zone-mode` | `whole` | `whole` or `bright`. |
| `--zone-bright` | `200` | Brightness threshold for `bright` mode. |
| `--keep-source` | off | Keeps the downloaded thumbnail next to the output. |

## Project layout

```
app.py            Entry point.
config.py         Constants (platform, paths, URLs, models, presets) and config.json read / write.
i18n.py           Interface language (EN / FR): tr(), tr_name() and all the texts.
control.py        Cancellation (Cancelled, Control).
devices.py        GPU / CPU labels and the fallback order.
engine.py         Real-ESRGAN engine: install (download + SHA-256 + extract) and run.
upscale.py        Pass planning, final resize, full pipeline.
monitor.py        Background CPU / RAM / GPU / network monitoring.
wallpaper.py      Wallpaper maker pipeline (also usable from the command line).
cleanup.py        Optional text / logo erasing (OCR + LaMa).
theme.py          Dark Fusion palette + stylesheet (QSS).
widgets.py        Reusable widgets: comparison view, segmented controls, sliders, dialogs, SignalQueue.
export.py         Saves the temporary (PNG) result in the format chosen at download time.
gui.py            Main window (App), Upscaler and Monitoring tabs.
gui_wallpaper.py  Wallpaper maker tab.
config.json       Created automatically: the engine's SHA-256 and the chosen language.
upscaler/         Created automatically: the Real-ESRGAN engine.
```

Dependency direction (no cycles): `config` ← `i18n`, `control`, `devices`, `monitor`; `i18n` ← every module that shows text; `engine` → `config`, `control`, `devices`; `upscale` → `config`, `engine`; `widgets` → `config`; `export` → `config`; `gui_wallpaper` → `widgets`, `export` and the modules above; `gui` → `gui_wallpaper`, `export` and the modules above; `app` → `gui`, `theme`.

## Troubleshooting

| Problem | Likely cause / fix |
|---|---|
| "The downloaded file differs from the one received during a previous installation" | The engine's hash changed. If you trust the new file, delete the `"sha256"` entry from `config.json` and relaunch. |
| No GPU detected | Install or update your card's Vulkan drivers, then click ↻. Meanwhile, use *Auto* or *CPU*. |
| Processing is very slow | You are probably on CPU or on a software GPU (llvmpipe). Pick the right GPU in "Device". The *Photo / realistic* model is also the slowest. |
| "Upscaling failed on every device tried" | The engine failed on every device. The last lines of its output are shown: often a missing Vulkan driver or not enough VRAM. Try a smaller target or CPU mode. |
| "Intermediate resolution too large" | The chain of passes would exceed 16,384 px. Choose a smaller target. |
| "WebP supports at most 16383 pixels per side" | WebP format limit, reported when you click **Download**: retry as PNG or JPG (the displayed result is not lost). |
| "Module psutil manquant" (psutil missing) | `pip install psutil`. |
| Wallpaper maker removes no black bars / adds no grain | `pip install numpy opencv-python-headless`. |
| "Effacement non installé" (erase not installed) | See [Erasing text / logos](#erasing-text--logos-optional-heavy), or untick the erase options. |
| Result looks "plastic" or too smooth | Lower the JPEG cleanup, raise the grain (1 to 3) and sharpness, or try a single pass. |
| Leftover text after erasing | Lower the *Text sensitivity* or add a *Whole zone* area. |

## Credits

Upscaling engine: [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (xinntao), NCNN / Vulkan build. Erasing: [EasyOCR](https://github.com/JaidedAI/EasyOCR) and LaMa (through `simple-lama-inpainting`). Interface: PyQt6.
