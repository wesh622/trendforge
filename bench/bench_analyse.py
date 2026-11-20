"""V0, points 3 et 4 : durée et pic de mémoire de chaque étape d'analyse du module Recette.

Usage : uv run python bench/bench_analyse.py [--passes 2] [--sans-tiktok]
Chaque étape tourne dans un processus séparé (spawn), pour mesurer son propre pic de mémoire.
L'appel à Claude (étape 6, synthèse) n'est pas mesuré : seules ses images clés sont extraites.
Avec plusieurs passes, on garde la valeur la plus basse de chaque mesure (CPU partagé).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CACHE = RACINE / ".cache" / "bench"
ANALYSE = RACINE / ".cache" / "analyse"
AGENT = "trendforge-bench/0.1 (mesures V0)"

# TikTok bloque yt-dlp sur cette machine (voir tentative_tiktok dans les résultats) : vidéos
# verticales du domaine public (NASA SVS) de remplacement, au format « faits » des comptes faceless.
VIDEOS = [
    {"cle": "nicer_qpe", "type": "faits, narration anglaise, vertical", "langue": "en",
     "url": "https://svs.gsfc.nasa.gov/vis/a010000/a014700/a014799/14819_NICER_QPE_Vertical.mp4"},
    {"cle": "m87_texte", "type": "faits, texte à l'écran + musique, vertical", "langue": None,
     "url": "https://svs.gsfc.nasa.gov/vis/a010000/a014700/a014793/M87_zoom_final_text_Vertical_Trim_Reel.mp4"},
    {"cle": "eclipse_es", "type": "explication, narration espagnole, horizontal", "langue": None,
     "url": "https://svs.gsfc.nasa.gov/vis/a010000/a013600/a013668/EclipseSafetyVideo_Spanish.mp4"},
]
TIKTOK = "https://www.tiktok.com/@factsdaily/video/7282871287368699141"
ETAPES = ["telecharger", "transcrire", "plans", "ocr", "audio", "images_cles"]


def _executer(etape: str, args: dict) -> tuple[dict, dict]:
    """Lance une étape (dans le processus enfant) ; rend (résumé, résultat complet)."""
    from trendforge import analyse as a
    from trendforge.mesure import mesurer_fonction

    v, d = args.get("video"), Path(args["dossier"])
    if etape == "telecharger":
        r, m = mesurer_fonction(a.telecharger, args["url"], d, user_agent=args.get("agent"))
        res = a.dico(r)
        resume = {"duree_s": round(r.duree_s, 1), "taille_mo": round(Path(r.fichier).stat().st_size / 2**20, 1)}
    elif etape == "transcrire":
        note = None
        try:
            r, m = mesurer_fonction(a.transcrire, v, d, langue=args["langue"])
        except a.ModeleManquant as e:
            note = f"{e} : mesure faite avec small.en (même taille, même coût de calcul)"
            r, m = mesurer_fonction(a.transcrire, v, d, langue="en")
        res = a.dico(r) | {"note_bench": note}
        resume = {"mots": len(r.mots), "langue": r.langue, "modele": r.modele, "format": r.format,
                  "parole_s": r.duree_parlee_s, "note": note or r.message}
    elif etape == "plans":
        r, m = mesurer_fonction(a.plans, v)
        res = a.dico(r)
        resume = {"plans": r.nombre, "duree_moy_s": r.duree_moyenne_s, "coupes_min": r.coupes_par_minute}
    elif etape == "ocr":
        r, m = mesurer_fonction(a.ocr, v, args["debuts"], args["duree"])
        res = a.dico(r)
        resume = {"images": r.images_analysees, "avec_texte": r.images_avec_texte,
                  "mots_img": r.mots_par_image_moyen, "position": r.position_dominante,
                  "couleur": r.couleur_dominante}
    elif etape == "audio":
        r, m = mesurer_fonction(a.audio, v, d, args["mots"])
        res = a.dico(r)
        resume = {"tempo": r.tempo_bpm, "musique_db": r.musique_db,
                  "musique_sous_voix_db": r.musique_sous_voix_db, "pics": r.pics_transitoires}
    elif etape == "images_cles":
        r, m = mesurer_fonction(a.images_cles, v, d / "images_cles", args["debuts"], args["fins"],
                                args["duree"])
        res = {"images": r}
        resume = {"images": len(r)}
    else:
        raise ValueError(etape)
    return {"secondes": round(m.secondes, 2), "pic_mo": round(m.pic_mo)} | resume, res


def _enfant(q: mp.Queue, etape: str, args: dict) -> None:
    try:
        q.put(_executer(etape, args))
    except Exception as e:  # noqa: BLE001 - remonté au parent
        q.put(({"erreur": f"{type(e).__name__}: {e}"}, {}))


def lancer(etape: str, args: dict) -> tuple[dict, dict]:
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=_enfant, args=(q, etape, args))
    p.start()
    try:
        r = q.get(timeout=1800)
    except Exception:  # noqa: BLE001
        r = ({"erreur": "aucun résultat"}, {})
    p.join()
    if p.exitcode not in (0, None) and "erreur" not in r[0]:
        r[0]["erreur"] = f"code {p.exitcode}"
    return r


def tentative_tiktok(url: str) -> dict:
    def _essai():
        from trendforge.analyse import ErreurAnalyse, telecharger
        tmp = ANALYSE / "_tiktok_essai"
        try:
            telecharger(url, tmp)
            return "réussi"
        except ErreurAnalyse as e:
            return f"{type(e).__name__}: {e}"
        finally:
            for f in tmp.glob("*"):
                f.unlink()
            if tmp.exists():
                tmp.rmdir()

    from trendforge.mesure import mesurer_fonction
    res, m = mesurer_fonction(_essai)
    return {"url": url, "resultat": res, "secondes": round(m.secondes, 1)}


def analyser_video(v: dict) -> dict:
    d = ANALYSE / v["cle"]
    d.mkdir(parents=True, exist_ok=True)
    sorties: dict[str, dict] = {}
    complet: dict[str, dict] = {}

    def etape(nom: str, **extra) -> None:
        r, c = lancer(nom, {"dossier": str(d), **extra})
        sorties[nom], complet[nom] = r, c
        (d / f"{nom}.json").write_text(json.dumps(c, indent=2, ensure_ascii=False))
        print(f"  {v['cle']:<11} {nom:<12} {json.dumps(r, ensure_ascii=False)}", flush=True)

    etape("telecharger", url=v["url"], agent=AGENT)
    if "erreur" in sorties["telecharger"]:
        return sorties
    t = complet["telecharger"]
    video, duree = t["fichier"], t["duree_s"]
    etape("transcrire", video=video, langue=v["langue"])
    etape("plans", video=video)
    p = complet.get("plans") or {"debuts_s": [0.0], "fins_s": [duree]}
    etape("ocr", video=video, debuts=p["debuts_s"], duree=duree)
    etape("audio", video=video, mots=(complet.get("transcrire") or {}).get("mots", []))
    etape("images_cles", video=video, debuts=p["debuts_s"], fins=p["fins_s"], duree=duree)
    return sorties


def minimum(passes: list[dict]) -> dict:
    """Pour chaque vidéo et étape, la plus basse des mesures (secondes, pic) sur les passes."""
    res: dict = {}
    for cle in passes[0]:
        res[cle] = {}
        for e in ETAPES:
            vals = [p[cle].get(e, {}) for p in passes if "erreur" not in p[cle].get(e, {"erreur": 1})]
            if not vals:
                res[cle][e] = passes[-1][cle].get(e, {"erreur": "non lancé"})
                continue
            res[cle][e] = vals[-1] | {"secondes": min(x["secondes"] for x in vals),
                                      "pic_mo": min(x["pic_mo"] for x in vals)}
    return res


def tableau(res: dict) -> str:
    cles = list(res)
    lignes = ["| Étape | " + " | ".join(f"{c} (s / pic Mo)" for c in cles) + " |",
              "| --- |" + " --- |" * len(cles)]
    for e in ETAPES:
        cell = []
        for c in cles:
            r = res[c].get(e, {})
            cell.append(r["erreur"][:40] if "erreur" in r else f"{r['secondes']:.1f} s / {r['pic_mo']} Mo")
        lignes.append(f"| {e} | " + " | ".join(cell) + " |")
    tot = []
    for c in cles:
        ok = [r for r in res[c].values() if "erreur" not in r]
        tot.append(f"{sum(r['secondes'] for r in ok):.1f} s / max {max((r['pic_mo'] for r in ok), default=0)} Mo")
    lignes.append("| **total** | " + " | ".join(tot) + " |")
    sans_dl = []
    for c in cles:
        ok = [r for e, r in res[c].items() if e != "telecharger" and "erreur" not in r]
        sans_dl.append(f"{sum(r['secondes'] for r in ok):.1f} s")
    lignes.append("| total hors téléchargement | " + " | ".join(sans_dl) + " |")
    return "\n".join(lignes)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("--sans-tiktok", action="store_true")
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    ANALYSE.mkdir(parents=True, exist_ok=True)
    sortie: dict = {"date": time.strftime("%Y-%m-%d %H:%M"), "videos": VIDEOS}
    if not a.sans_tiktok:
        sortie["tentative_tiktok"] = tentative_tiktok(TIKTOK)
        print("TikTok :", json.dumps(sortie["tentative_tiktok"], ensure_ascii=False), flush=True)
    passes = []
    for i in range(a.passes):
        print(f"passe {i + 1}/{a.passes}", flush=True)
        passes.append({v["cle"]: analyser_video(v) for v in VIDEOS})
    sortie["passes"] = passes
    sortie["minimum"] = minimum(passes)
    (CACHE / "resultats_analyse.json").write_text(json.dumps(sortie, indent=2, ensure_ascii=False))
    print()
    print(tableau(sortie["minimum"]))


if __name__ == "__main__":
    main()
