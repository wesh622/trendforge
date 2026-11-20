"""Vidéos de fond (section 7, étape 6) : bibliothèque locale `fonds/` puis Pexels (clé dans le trousseau)."""

from __future__ import annotations

import json
import os
import random
import subprocess
from pathlib import Path

import httpx

RACINE = Path(__file__).resolve().parents[2]
FONDS = RACINE / "fonds"
CACHE = RACINE / ".cache" / "pexels"
UA = {"User-Agent": "TrendForge/0.1"}

# Mots-clés de recherche Pexels par type de fond de recette.
REQUETES = {
    "satisfying_loop": ["satisfying", "kinetic sand", "slime", "paint mixing", "soap cutting"],
    "satisfying_gameplay": ["satisfying", "marble run", "kinetic sand"],
    "stock_illustratif": ["city timelapse", "nature aerial", "abstract light", "ocean waves"],
    "stock_sombre": ["dark forest", "foggy night", "abandoned building", "storm clouds"],
}


def cle_pexels() -> str | None:
    try:
        import keyring

        cle = keyring.get_password("trendforge", "pexels")
    except Exception:  # noqa: BLE001
        cle = None
    return cle or os.environ.get("PEXELS_API_KEY")


def duree(f: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def locaux(categorie: str) -> list[Path]:
    """fonds/<categorie>/*.mp4 en priorité, sinon fonds/*.mp4."""
    d = FONDS / categorie
    fichiers = sorted(d.glob("*.mp4")) if d.is_dir() else []
    return fichiers or sorted(FONDS.glob("*.mp4"))


def pexels(categorie: str, nombre: int = 4, rnd: random.Random | None = None) -> list[Path]:
    cle = cle_pexels()
    if not cle:
        return []
    rnd = rnd or random.Random()
    requete = rnd.choice(REQUETES.get(categorie, [categorie.replace("_", " ")]))
    CACHE.mkdir(parents=True, exist_ok=True)
    r = httpx.get("https://api.pexels.com/videos/search",
                  params={"query": requete, "orientation": "portrait", "per_page": 15},
                  headers={**UA, "Authorization": cle}, timeout=30)
    r.raise_for_status()
    videos = r.json().get("videos", [])
    rnd.shuffle(videos)
    sortie = []
    for v in videos:
        # fichier vertical le plus proche de 1080 px de large, sans dépasser 1440
        fichiers = [f for f in v.get("video_files", []) if f.get("width") and f.get("height")
                    and f["height"] > f["width"] and f["width"] <= 1440]
        if not fichiers or v.get("duration", 0) < 5:
            continue
        f = min(fichiers, key=lambda f: abs(f["width"] - 1080))
        dest = CACHE / f"pexels_{v['id']}_{f['width']}.mp4"
        if not dest.exists():
            with httpx.stream("GET", f["link"], headers=UA, timeout=120, follow_redirects=True) as s:
                s.raise_for_status()
                with dest.open("wb") as fh:
                    for bloc in s.iter_bytes():
                        fh.write(bloc)
            (dest.with_suffix(".json")).write_text(json.dumps(
                {"source": "pexels", "id": v["id"], "url": v.get("url"), "auteur": v.get("user", {}).get("name"),
                 "requete": requete}, ensure_ascii=False))
        sortie.append(dest)
        if len(sortie) >= nombre:
            break
    return sortie


def choisir_fonds(categorie: str, nombre: int = 4, rnd: random.Random | None = None) -> list[tuple[Path, float]]:
    rnd = rnd or random.Random()
    fichiers = locaux(categorie)
    if len(fichiers) < nombre:
        fichiers += pexels(categorie, nombre - len(fichiers), rnd)
    if not fichiers:
        raise RuntimeError(
            "Aucune vidéo de fond : mets des .mp4 dans fonds/ (ou fonds/<catégorie>/) "
            "ou enregistre une clé Pexels (uv run trendforge config cle-pexels)."
        )
    rnd.shuffle(fichiers)
    return [(f, duree(f)) for f in fichiers[:nombre]]
