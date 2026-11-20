"""Moteur visuel HTML (section 7, version 3) : Claude écrit une page animée, Chrome la filme.

Contrat de la page : tout l'affichage est une fonction pure du temps, window.dessiner(t).
Le moteur appelle dessiner(k / 30) pour chaque image et capture l'écran : le rendu est
identique à chaque fois et calé sur la voix (les animations s'ancrent sur DATA.mots[i].d).
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from trendforge import llm
from trendforge.captions import Charte, Mot
from trendforge.models import Recipe

FPS = 30
LARGEUR, HAUTEUR = 1080, 1920
# Zone sûre : hors des boutons TikTok (colonne de droite) et de la légende (bas de l'écran).
ZONE_SURE = {"x_min": 60, "x_max": 940, "y_min": 200, "y_max": 1560}

SYSTEME_ANIMATEUR = f"""You are a senior motion designer who writes code. You write ONE self-contained HTML file that is rendered frame by frame into a {LARGEUR}x{HAUTEUR} vertical video (TikTok), with a voice-over.

Technical contract (the render fails if you break it):
- Before your scripts run, the page receives `window.DATA = {{duree: <seconds>, mots: [{{w: "word", d: <start s>, f: <end s>}}, ...]}}`: the voice-over words with their timestamps.
- Define `window.dessiner = function (t) {{...}}`. It must set the ENTIRE visual state for time t (seconds) from scratch: a pure function of t. It is called for t = 0, 1/30, 2/30, ... and also out of order, so it must never depend on a previous call.
- Forbidden: CSS animations and transitions, requestAnimationFrame, setTimeout/setInterval, Date, performance.now, Math.random (use a seeded hash like `fract(sin(i*127.1)*43758.5453)`), video and audio elements.
- No network at all: no external fonts, images, scripts or stylesheets. Fonts installed: "{{police}}" (weights 400 and 700) and "Noto Color Emoji" for emojis. Draw illustrations with emojis, inline SVG, CSS shapes or canvas.
- html and body are exactly {LARGEUR}x{HAUTEUR}px, overflow hidden, with an explicit background.
- Safe zone: every piece of text and every important element stays inside x {ZONE_SURE["x_min"]}-{ZONE_SURE["x_max"]} and y {ZONE_SURE["y_min"]}-{ZONE_SURE["y_max"]} (TikTok buttons on the right, caption at the bottom). Size text so it never overflows: long words wrap, lines fit the safe width.
- dessiner(t) must take under 25 ms: build the DOM once at load, then only change styles and text in dessiner.
- Synchronise with the voice: anchor every animation on word start times, `DATA.mots[i].d`, using the word indexes you are given. Something visible must change at least every {{changement}} seconds.
- Draw the word-by-word captions yourself, as specified in the visual recipe, in the lower part of the safe zone (around y 1250-1450), never overlapping the main illustration.
- Captions: put a visible gap between words (margin or a real space): two words must never touch.
- Layout: elements visible at the same time never overlap each other (badge, titles, illustration, captions each get their own band). The main area is never empty for more than 0.5 s: keep the previous scene until the next one appears.
- A counter or animated number must already show its final value when the voice says it.
- Output ONLY the HTML document, starting with <!doctype html>. No markdown fences, no explanation.

Design quality: bold, readable on a phone, high contrast, one strong idea per scene, generous motion (pop-ins, counters, things appearing exactly when they are said). Illustrate the actual content of each sentence, not generic decoration."""


@dataclass
class Controle:
    erreurs: list[str] = field(default_factory=list)       # cassent le rendu → page réécrite
    debordements: list[str] = field(default_factory=list)  # avertissements pour la validation humaine
    chevauchements: list[str] = field(default_factory=list)
    ms_par_image: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.erreurs and not self.debordements and not self.chevauchements


def prompt_animation(recette: Recipe, script: str, mots: list[Mot], charte: Charte) -> str:
    v = recette.visuel
    visuel = v.model_dump(mode="json", exclude={"voix", "audio", "moteur", "fond"})
    parties = [{"part": p.part, "seconds": list(p.seconds), "scene": v.scene_pour(p.part)}
               for p in recette.contenu.structure]
    liste_mots = "\n".join(f"{i} {m.texte} {m.debut:.2f}-{m.fin:.2f}" for i, m in enumerate(mots))
    return f"""Visual recipe (follow it):
{json.dumps(visuel, ensure_ascii=False, indent=2)}

Planned structure (approximate timing; map each sentence of the script to its part):
{json.dumps(parties, ensure_ascii=False, indent=2)}

Channel charter: font "{charte.police}", text color {charte.couleur}, accent color {charte.accent}.

Voice-over script:
{script}

Voice-over words (index word start-end, seconds). Total duration: {mots[-1].fin + 0.6:.2f} s.
{liste_mots}

Write the HTML file."""


def nettoyer_html(texte: str) -> str:
    """Retire d'éventuelles balises de code markdown autour du document."""
    m = re.search(r"<!doctype html.*</html>", texte, re.IGNORECASE | re.DOTALL)
    return m.group(0) if m else texte.strip()


def ecrire_page(recette: Recipe, script: str, mots: list[Mot], charte: Charte,
                retour: str | None = None, consignes: str | None = None) -> tuple[str, llm.Appel]:
    systeme = (SYSTEME_ANIMATEUR.replace("{police}", charte.police)
               .replace("{changement}", f"{recette.visuel.rythme.changement_s:g}"))
    message = prompt_animation(recette, script, mots, charte)
    if consignes:
        message += f"\n\nExtra instructions from the channel owner (the technical contract still wins):\n{consignes}"
    if retour:
        message += f"\n\nA previous version failed these automatic checks; fix them:\n{retour}"
    texte, appel = llm.generer_texte("animation_html", systeme, message)
    return nettoyer_html(texte), appel


# --------------------------------------------------------------------------- navigateur

_SCRIPT_DEBORDEMENTS = """(zone) => {
  // Lignes de texte réellement dessinées (Range sur les nœuds texte, emojis compris), pas les
  // boîtes des blocs : un bloc pleine largeur au texte centré ne déborde pas.
  const lignes = [];
  const marche = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = marche.nextNode(); n; n = marche.nextNode()) {
    if (!n.textContent.trim()) continue;
    let o = 1, p = n.parentElement, cache = false;
    while (p && p !== document.documentElement) {
      const s = getComputedStyle(p);
      if (s.display === 'none' || s.visibility === 'hidden') { cache = true; break; }
      o *= parseFloat(s.opacity);
      p = p.parentElement;
    }
    if (cache || o < 0.5) continue;
    const r = document.createRange();
    r.selectNodeContents(n);
    for (const b of r.getClientRects())
      if (b.width >= 2 && b.height >= 2) lignes.push({n, txt: n.textContent.trim().slice(0, 30), b});
  }
  const hors = [], chev = [];
  const fmt = b => `[${Math.round(b.left)},${Math.round(b.top)} → ${Math.round(b.right)},${Math.round(b.bottom)}]`;
  for (const {txt, b} of lignes)
    if (b.left < zone.x_min - 20 || b.right > zone.x_max + 20 || b.top < zone.y_min - 20 || b.bottom > zone.y_max + 20)
      hors.push(`${txt} ${fmt(b)}`);
  for (let i = 0; i < lignes.length; i++) for (let k = i + 1; k < lignes.length; k++) {
    const A = lignes[i], B = lignes[k];
    if (A.n === B.n) continue;
    const w = Math.min(A.b.right, B.b.right) - Math.max(A.b.left, B.b.left);
    const h = Math.min(A.b.bottom, B.b.bottom) - Math.max(A.b.top, B.b.top);
    if (w <= 0 || h <= 0) continue;
    const petite = Math.min(A.b.width * A.b.height, B.b.width * B.b.height);
    if (w * h > 0.25 * petite) chev.push(`« ${A.txt} » / « ${B.txt} »`);
  }
  return {hors, chev};
}"""


def _ouvrir(p, html_path: Path, data: dict):
    nav = p.chromium.launch(channel="chrome", args=["--force-color-profile=srgb"])
    page = nav.new_page(viewport={"width": LARGEUR, "height": HAUTEUR}, device_scale_factor=1)
    erreurs: list[str] = []
    page.on("pageerror", lambda e: erreurs.append(f"exception: {e}"))
    page.on("console", lambda m: erreurs.append(f"console.error: {m.text}") if m.type == "error" else None)
    page.on("request", lambda r: erreurs.append(f"network request forbidden: {r.url[:80]}")
            if not r.url.startswith(("file:", "data:", "blob:", "about:")) else None)
    page.add_init_script(f"window.DATA = {json.dumps(data)};")
    page.goto(html_path.resolve().as_uri())
    page.evaluate("document.fonts.ready")
    return nav, page, erreurs


def controler(html_path: Path, data: dict, n_instants: int = 24) -> Controle:
    """Vérifie la page avant la capture : erreurs JS, dessiner(t) présent, texte hors zone sûre."""
    from playwright.sync_api import sync_playwright

    c = Controle()
    with sync_playwright() as p:
        nav, page, erreurs = _ouvrir(p, html_path, data)
        try:
            if page.evaluate("typeof window.dessiner") != "function":
                c.erreurs.append("window.dessiner is not defined")
                return c
            vus: set[str] = set()
            t0 = time.perf_counter()

            def mesure(t: float):
                page.evaluate(f"dessiner({t:.3f})")
                return page.evaluate(_SCRIPT_DEBORDEMENTS, ZONE_SURE)

            for k in range(n_instants):
                t = data["duree"] * (k + 0.5) / n_instants
                try:
                    m = mesure(t)
                    # Un défaut ne compte que s'il est encore là 0,35 s plus tard (pas une apparition).
                    m2 = mesure(min(t + 0.35, data["duree"])) if (m["hors"] or m["chev"]) else m
                except Exception as e:  # noqa: BLE001 — erreur JS remontée par Playwright
                    c.erreurs.append(f"dessiner({t:.2f}) threw: {str(e).splitlines()[0]}")
                    continue
                cles2 = {d.split(" [")[0] for d in m2["hors"]}
                for d in m["hors"]:
                    cle = d.split(" [")[0]
                    if cle in cles2 and cle not in vus:
                        vus.add(cle)
                        c.debordements.append(f"t={t:.1f}s: text outside the safe zone: {d}")
                for d in m["chev"]:
                    if d in m2["chev"] and d not in vus:
                        vus.add(d)
                        c.chevauchements.append(f"t={t:.1f}s: overlapping texts {d}")
            c.ms_par_image = round((time.perf_counter() - t0) * 1000 / n_instants, 1)
            c.erreurs += list(dict.fromkeys(erreurs))
        finally:
            nav.close()
    return c


def capturer(html_path: Path, data: dict, voix: Path, sortie: Path, musique: Path | None = None,
             musique_db: float = -22) -> float:
    """Filme la page à 30 i/s et encode le MP4 avec la voix. Renvoie la durée de capture en s."""
    from playwright.sync_api import sync_playwright

    n_images = int(data["duree"] * FPS)
    entrees = ["-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-", "-i", str(voix)]
    norme = "loudnorm=I=-14:TP=-1.5:LRA=11"  # volume global à -14 LUFS (section 7, étape 8)
    if musique:
        entrees += ["-stream_loop", "-1", "-i", str(musique)]
        graphe = f"[2:a]volume={musique_db}dB[m];[1:a][m]amix=inputs=2:duration=first,{norme}[a]"
    else:
        graphe = f"[1:a]{norme}[a]"
    audio = ["-filter_complex", graphe, "-map", "0:v", "-map", "[a]"]
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", *entrees, *audio,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
         "-shortest", "-movflags", "+faststart", str(sortie)],
        stdin=subprocess.PIPE)
    t0 = time.perf_counter()
    with sync_playwright() as p:
        nav, page, _ = _ouvrir(p, html_path, data)
        try:
            for k in range(n_images):
                page.evaluate(f"dessiner({k / FPS})")
                ffmpeg.stdin.write(page.screenshot(type="jpeg", quality=92))
        finally:
            nav.close()
            ffmpeg.stdin.close()
            ffmpeg.wait()
    if ffmpeg.returncode != 0:
        raise RuntimeError("encodage FFmpeg en échec")
    return time.perf_counter() - t0
