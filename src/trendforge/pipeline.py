"""Enchaînement de la génération d'une vidéo (section 7, « Pipeline de génération »).

Chaque étape écrit son résultat dans le dossier de la vidéo : une regénération ne refait que
l'étape demandée (exigence « reprise après erreur », section 10).
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from typing import Callable
from datetime import datetime, timezone
from pathlib import Path

from trendforge import llm, scripts
from trendforge.captions import Charte, Mot, ecrire_ass
from trendforge.models import FicheSujet, Recipe
from trendforge.render import Rendu, construire_commande, decouper
from trendforge.mesure import mesurer_commande
from trendforge.visuels import choisir_fonds
from trendforge.voix import horodater, synthetiser, vitesse_pour_debit

RACINE = Path(__file__).resolve().parents[2]
SORTIES = RACINE / "sorties"
MUSIQUE = RACINE / "musique"
SEUIL_HOOK = 7
MAX_TENTATIVES_DUREE = 3
AJUSTEMENT_VITESSE_MAX = 0.08


class EchecDuree(RuntimeError):
    pass


def _journal(dossier: Path, cle: str, valeur) -> None:
    f = dossier / "journal.json"
    j = json.loads(f.read_text()) if f.exists() else {}
    j[cle] = valeur
    f.write_text(json.dumps(j, indent=2, ensure_ascii=False, default=str))


def _musique(rnd: random.Random) -> Path | None:
    pistes = sorted(MUSIQUE.glob("*.mp3")) + sorted(MUSIQUE.glob("*.wav")) if MUSIQUE.is_dir() else []
    return rnd.choice(pistes) if pistes else None


Progression = Callable[[str], None]


def _rien(_: str) -> None:
    pass


def generer(recette: Recipe, fiche: FicheSujet, charte: Charte | None = None,
            graine: int | None = None, script_impose: str | None = None,
            consignes: str | None = None, progression: Progression = _rien) -> Path:
    c, v = recette.contenu, recette.visuel
    if v.moteur == "html":
        return generer_html(recette, fiche, charte, graine, script_impose, consignes, progression)
    charte = charte or Charte()
    rnd = random.Random(graine)
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dossier = SORTIES / f"{horodatage}_{recette.recipe_id}"
    dossier.mkdir(parents=True, exist_ok=True)
    appels: list[llm.Appel] = []
    _journal(dossier, "recette", recette.model_dump(mode="json"))
    _journal(dossier, "fiche_sujet", fiche.model_dump(mode="json", exclude={"texte_source"}))

    # 2. Script
    if script_impose:
        texte, hook = script_impose, script_impose.split(".")[0]
        meta = {"titre": fiche.titre, "legende": "", "hashtags": c.posting.hashtags}
    else:
        final, a = scripts.ecrire_script(recette, fiche)
        appels += a
        texte, hook = final.script, final.hook
        meta = {"titre": final.titre, "legende": final.legende, "hashtags": final.hashtags}
        # 3. Contrôle qualité : hook (les contrôles de similarité seront branchés ici)
        note, detail, a = scripts.noter_hook(hook, texte, c.script_style.wpm)
        appels.append(a)
        _journal(dossier, "hook", {"note": note, **detail})
    (dossier / "script.txt").write_text(texte, encoding="utf-8")

    # 4-5. Voix + contrôle de durée (boucle bornée)
    lo, hi = c.target_duration_s
    vitesse = vitesse_pour_debit(c.script_style.wpm)
    voix_nom = (v.voix.engine_hint or "kokoro:af_heart").split(":")[-1]
    wav = dossier / "voix.wav"
    d = synthetiser(texte, wav, voix_nom, vitesse)
    if not lo <= d <= hi:
        cible = (lo + hi) / 2
        nouvelle = vitesse * d / cible
        if abs(nouvelle / vitesse - 1) <= AJUSTEMENT_VITESSE_MAX:
            vitesse = round(nouvelle, 3)
            d = synthetiser(texte, wav, voix_nom, vitesse)
    _journal(dossier, "voix", {"voix": voix_nom, "vitesse": vitesse, "duree_s": round(d, 2)})
    if not lo <= d <= hi:
        # La réécriture du script pour rallonger/resserrer (3 tentatives) se branche ici.
        _journal(dossier, "statut", "echec_duree")
        raise EchecDuree(f"voix de {d:.1f} s hors de la fourchette {lo:.0f}-{hi:.0f} s ; dossier {dossier}")

    mots = horodater(wav, texte)
    (dossier / "mots.json").write_text(json.dumps([asdict(m) for m in mots], ensure_ascii=False))

    # 6-7. Fonds et sous-titres
    fonds = choisir_fonds(v.fond, 4, rnd)
    plans = decouper(fonds, d, v.rythme.changement_s)
    ass = ecrire_ass(mots, dossier / "sous-titres.ass", charte,
                     v.sous_titres.words_on_screen, v.sous_titres.position)

    # 8-9. Musique + rendu (VAAPI, libx264 en secours)
    sortie = dossier / "video.mp4"
    rendu = Rendu(plans=plans, voix=wav, ass=ass, sortie=sortie, musique=_musique(rnd),
                  musique_db=v.audio.music_db)
    m = mesurer_commande(construire_commande(rendu))
    if m.code != 0:
        rendu.encodeur = "libx264"
        m = mesurer_commande(construire_commande(rendu))
    if m.code != 0:
        _journal(dossier, "statut", "echec_rendu")
        raise RuntimeError(f"rendu impossible : {m.erreur[-500:]}")
    _journal(dossier, "rendu", {"encodeur": rendu.encodeur, "secondes": round(m.secondes, 1),
                                "pic_mo": round(m.pic_mo), "fonds": [str(f) for f, _ in fonds]})

    # 11. Métadonnées (fichier légende livré au téléphone)
    legende = (f"⚠ AI-generated : à cocher dans TikTok\n\n{meta['titre']}\n\n{meta['legende']}\n\n"
               + " ".join(meta["hashtags"]))
    (dossier / "legende.txt").write_text(legende, encoding="utf-8")
    _journal(dossier, "appels_llm", [asdict(a) for a in appels])
    _journal(dossier, "cout_usd", round(sum(a.cout_usd for a in appels), 4))
    _journal(dossier, "statut", "a_valider")
    return dossier


# --------------------------------------------------------------------------- moteur HTML (v3)


def _script(recette: Recipe, fiche: FicheSujet, dossier: Path, appels: list,
            script_impose: str | None, consignes: str | None = None) -> tuple[str, dict]:
    c = recette.contenu
    if script_impose:
        texte = script_impose
        meta = {"titre": fiche.titre, "legende": "", "hashtags": c.posting.hashtags}
    else:
        final, a = scripts.ecrire_script(recette, fiche, consignes)
        appels += a
        texte = final.script
        meta = {"titre": final.titre, "legende": final.legende, "hashtags": final.hashtags}
        # Durée du hook au débit RÉEL de la voix (ElevenLabs ≈ 140 mots/min × vitesse), pas au débit visé.
        hint = recette.visuel.voix.engine_hint or ""
        debit = (scripts.DEBIT_ELEVENLABS_1X * recette.visuel.voix.speed if hint.startswith("elevenlabs:")
                 else c.script_style.wpm)
        note, detail, a = scripts.noter_hook(final.hook, texte, debit)
        appels.append(a)
        _journal(dossier, "hook", {"note": note, **detail})
    (dossier / "script.txt").write_text(texte, encoding="utf-8")
    return texte, meta


def _voix(recette: Recipe, texte: str, dossier: Path) -> tuple[Path, float, list[Mot], dict]:
    """Voix ElevenLabs (horodatage inclus), ou Kokoro + faster-whisper si la recette le demande."""
    from trendforge import voix_elevenlabs as el

    lo, hi = recette.contenu.target_duration_s
    v = recette.visuel.voix
    wav = dossier / "voix.wav"
    voice_id = el.voix_depuis_hint(v.engine_hint)
    if voice_id is None:
        nom = (v.engine_hint or "kokoro:af_heart").split(":")[-1]
        vitesse = vitesse_pour_debit(recette.contenu.script_style.wpm)
        d = synthetiser(texte, wav, nom, vitesse)
        return wav, d, horodater(wav, texte), {"moteur": "kokoro", "voix": nom, "vitesse": vitesse}

    vitesse, caracteres = v.speed, 0
    s = el.synthetiser(texte, wav, voice_id, vitesse)
    caracteres += s.caracteres
    if not lo <= s.duree_s <= hi:
        nouvelle = vitesse * s.duree_s / ((lo + hi) / 2)
        if abs(nouvelle / vitesse - 1) <= AJUSTEMENT_VITESSE_MAX:
            vitesse = round(nouvelle, 3)
            s = el.synthetiser(texte, wav, voice_id, vitesse)
            caracteres += s.caracteres
    info = {"moteur": "elevenlabs", "voix": voice_id, "vitesse": vitesse, "duree_s": round(s.duree_s, 2),
            "caracteres": caracteres, "request_id": s.request_id}
    return wav, s.duree_s, s.mots, info


def generer_html(recette: Recipe, fiche: FicheSujet, charte: Charte | None = None,
                 graine: int | None = None, script_impose: str | None = None,
                 consignes: str | None = None, progression: Progression = _rien) -> Path:
    """Script (Claude) → voix (ElevenLabs) → page HTML animée (Claude) → capture (Chrome) → MP4."""
    from trendforge import animation

    charte = charte or Charte()
    rnd = random.Random(graine)
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dossier = SORTIES / f"{horodatage}_{recette.recipe_id}"
    dossier.mkdir(parents=True, exist_ok=True)
    appels: list[llm.Appel] = []
    _journal(dossier, "recette", recette.model_dump(mode="json"))
    _journal(dossier, "fiche_sujet", fiche.model_dump(mode="json", exclude={"texte_source"}))
    if consignes:
        _journal(dossier, "consignes", consignes)
    try:
        progression("1/4 Écriture du script (Claude)…")
        texte, meta = _script(recette, fiche, dossier, appels, script_impose, consignes)
        progression("2/4 Voix (ElevenLabs)…")

        wav, d, mots, info_voix = _voix(recette, texte, dossier)
        _journal(dossier, "voix", info_voix)
        lo, hi = recette.contenu.target_duration_s
        if not lo <= d <= hi and not script_impose:
            # Une réécriture au plus (chaque nouvelle voix consomme du quota ElevenLabs).
            progression(f"Voix de {d:.0f} s hors de {lo:.0f}-{hi:.0f} s : script ajusté…")
            vises = round(len(texte.split()) * ((lo + hi) / 2) / d)
            texte, a = scripts.ajuster_longueur(recette, texte, d, vises)
            appels.append(a)
            (dossier / "script.txt").write_text(texte, encoding="utf-8")
            wav, d, mots, info2 = _voix(recette, texte, dossier)
            info2["caracteres"] = info2.get("caracteres", 0) + info_voix.get("caracteres", 0)
            _journal(dossier, "voix", {**info2, "reecriture_longueur": True})
        if not lo <= d <= hi:
            _journal(dossier, "statut", "echec_duree")
            raise EchecDuree(f"voix de {d:.1f} s hors de la fourchette {lo:.0f}-{hi:.0f} s ; dossier {dossier}")
        (dossier / "mots.json").write_text(json.dumps([asdict(m) for m in mots], ensure_ascii=False))
        data = {"duree": round(d + 0.6, 3), "mots": [{"w": m.texte, "d": m.debut, "f": m.fin} for m in mots]}

        # Page HTML écrite par Claude, contrôlée, réécrite une fois si besoin.
        page = dossier / "page.html"
        retour, controles = None, []
        for tentative in range(2):
            progression("3/4 Page animée (Claude Opus, 2 à 4 min)…" if tentative == 0
                        else "Page invalide : réécriture…")
            html, a = animation.ecrire_page(recette, texte, mots, charte, retour, consignes)
            appels.append(a)
            page.write_text(html, encoding="utf-8")
            ctl = animation.controler(page, data)
            controles.append({"tentative": tentative + 1, "erreurs": ctl.erreurs,
                              "debordements": ctl.debordements, "chevauchements": ctl.chevauchements,
                              "ms_par_image": ctl.ms_par_image})
            _journal(dossier, "controles_page", controles)
            # Seules les erreurs qui cassent le rendu valent une réécriture (~0,38 $) ; débordements
            # et chevauchements sont des avertissements montrés à la validation.
            if not ctl.erreurs:
                break
            retour = "\n".join(ctl.erreurs + ctl.debordements + ctl.chevauchements)
        if ctl.erreurs:
            _journal(dossier, "statut", "echec_page")
            raise RuntimeError(f"page HTML invalide après 2 essais : {ctl.erreurs[:3]} ; dossier {dossier}")

        video = dossier / "video.mp4"
        progression(f"4/4 Capture de la vidéo ({int(data['duree'] * animation.FPS)} images)…")
        secondes = animation.capturer(page, data, wav, video, _musique(rnd), recette.visuel.audio.music_db)
        _journal(dossier, "rendu", {"moteur": "html", "capture_s": round(secondes, 1),
                                    "images": int(data["duree"] * animation.FPS)})

        legende = (f"⚠ AI-generated : à cocher dans TikTok\n\n{meta['titre']}\n\n{meta['legende']}\n\n"
                   + " ".join(meta["hashtags"]))
        (dossier / "legende.txt").write_text(legende, encoding="utf-8")
        if ctl.debordements or ctl.chevauchements:
            _journal(dossier, "avertissements_page", ctl.debordements + ctl.chevauchements)
        _journal(dossier, "statut", "a_valider")
        return dossier
    finally:
        _journal(dossier, "appels_llm", [asdict(a) for a in appels])
        _journal(dossier, "cout_llm_usd", round(sum(a.cout_usd for a in appels), 4))
