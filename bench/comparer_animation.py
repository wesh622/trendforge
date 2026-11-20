"""Réécrit seulement la page HTML d'une vidéo déjà générée avec un autre modèle / effort, puis la filme.

    uv run --group bench python bench/comparer_animation.py sorties/<dossier> claude-sonnet-5-5 medium

Ne refait ni le script ni la voix (aucun quota ElevenLabs consommé). Résultat : page_<modele>_<effort>.html
et video_<modele>_<effort>.mp4 dans le même dossier, coût et contrôles affichés.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from trendforge import animation, llm
from trendforge.captions import Charte, Mot
from trendforge.models import charger_recette_dict


def main(dossier: Path, modele: str, effort: str) -> None:
    j = json.loads((dossier / "journal.json").read_text())
    recette = charger_recette_dict(j["recette"])
    texte = (dossier / "script.txt").read_text(encoding="utf-8")
    mots = [Mot(m["texte"], m["debut"], m["fin"]) for m in json.loads((dossier / "mots.json").read_text())]
    data = {"duree": round(mots[-1].fin + 0.6 if not j.get("voix") else j["voix"]["duree_s"] + 0.6, 3),
            "mots": [{"w": m.texte, "d": m.debut, "f": m.fin} for m in mots]}
    llm.TACHES["animation_html"] = {"modele": modele, "effort": effort}
    nom = f"{modele.replace('claude-', '')}_{effort}"
    page = dossier / f"page_{nom}.html"
    if page.exists():  # reprise : page déjà payée, on ne la regénère pas
        html = page.read_text(encoding="utf-8")
        print(f"{nom} : page existante reprise ({len(html)} car.)")
    else:
        html, appel = animation.ecrire_page(recette, texte, mots, Charte())
        page.write_text(html, encoding="utf-8")
        print(f"{nom} : {appel.jetons_entree} + {appel.jetons_sortie} jetons, {appel.cout_usd:.3f} $, page {len(html)} car.")
    ctl = animation.controler(page, data)
    print(f"contrôle ok={ctl.ok} {ctl.ms_par_image} ms/image {ctl.erreurs[:3]} {ctl.debordements[:3]}")
    if not ctl.erreurs:
        s = animation.capturer(page, data, dossier / "voix.wav", dossier / f"video_{nom}.mp4")
        print(f"capture {s:.0f} s → {dossier / f'video_{nom}.mp4'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
