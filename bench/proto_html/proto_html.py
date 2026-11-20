"""Prototype « vidéo en HTML » : voix Kokoro + page HTML animée filmée image par image.

    uv run --group bench python bench/proto_html/proto_html.py

Étapes : voix (Kokoro) → horodatage des mots (faster-whisper) → découpage en scènes
→ capture de scene.html à 30 i/s avec Chrome sans fenêtre (Playwright) → MP4 (FFmpeg).
Les temps de chaque étape sont écrits dans bench/resultats/proto_html.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ICI = Path(__file__).resolve().parent
RACINE = ICI.parents[1]
sys.path.insert(0, str(RACINE / "src"))

from trendforge import voix  # noqa: E402

FPS = 30
SORTIE = RACINE / "bench" / "resultats"

# Script tenu par Claude dans la version finale ; ici écrit à la main pour le prototype.
PHRASES = [
    ("hook", "Three facts that sound fake, but are true."),
    ("fait1", "An octopus has three hearts."),
    ("fait2", "Bananas are berries, but strawberries are not."),
    ("fait3", "Honey found in Egyptian tombs is still edible."),
    ("cta", "Which one did you know?"),
]


def scenes_depuis_mots(mots) -> list[dict]:
    """Chaque phrase devient une scène qui commence à son premier mot prononcé."""
    scenes, i = [], 0
    for type_, phrase in PHRASES:
        n = len(phrase.split())
        bloc = mots[i:i + n]
        scenes.append({"type": type_, "debut": bloc[0].debut})
        i += n
    for s, suivante in zip(scenes, scenes[1:]):
        s["fin"] = suivante["debut"]
    return scenes


def main() -> None:
    from playwright.sync_api import sync_playwright

    travail = SORTIE / "proto_html"
    travail.mkdir(parents=True, exist_ok=True)
    temps = {}
    texte = " ".join(p for _, p in PHRASES)

    t0 = time.perf_counter()
    wav = travail / "voix.wav"
    duree = voix.synthetiser(texte, wav, voix="am_michael", vitesse=voix.vitesse_pour_debit(180))
    temps["voix_s"] = round(time.perf_counter() - t0, 1)

    t0 = time.perf_counter()
    mots = voix.horodater(wav, texte)
    temps["horodatage_s"] = round(time.perf_counter() - t0, 1)
    if len(mots) != len(texte.split()):
        print(f"attention : {len(mots)} mots reconnus pour {len(texte.split())} attendus")

    duree = duree + 0.6  # petite respiration après le CTA
    scenes = scenes_depuis_mots(mots)
    scenes[-1]["fin"] = duree
    data = {"duree": duree, "scenes": scenes,
            "mots": [{"w": m.texte, "d": m.debut, "f": m.fin} for m in mots]}

    video = travail / "proto.mp4"
    n_images = int(duree * FPS)
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
         "-i", str(wav),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(video)],
        stdin=subprocess.PIPE)

    t0 = time.perf_counter()
    with sync_playwright() as p:
        nav = p.chromium.launch(channel="chrome", args=["--force-color-profile=srgb"])
        page = nav.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        page.add_init_script(f"window.DATA = {json.dumps(data)};")
        page.goto((ICI / "scene.html").as_uri())
        page.evaluate("document.fonts.ready")
        for k in range(n_images):
            page.evaluate(f"dessiner({k / FPS})")
            ffmpeg.stdin.write(page.screenshot(type="jpeg", quality=92))
        nav.close()
    ffmpeg.stdin.close()
    ffmpeg.wait()
    temps["capture_et_encodage_s"] = round(time.perf_counter() - t0, 1)

    temps.update(duree_video_s=round(duree, 2), images=n_images,
                 images_par_s=round(n_images / temps["capture_et_encodage_s"], 1))
    (SORTIE / "proto_html.json").write_text(json.dumps(temps, indent=2))
    print(json.dumps(temps, indent=2))
    print(video)


if __name__ == "__main__":
    main()
