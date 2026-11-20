"""Module Recette, étape 6 (section 6) : lien TikTok ou fichier → recette v3 (contenu + visuel).

Enchaîne les étapes 1 à 5 d'`analyse.py` (une à la fois, profil Léger), puis un seul appel à
Claude avec les images clés, la transcription et les mesures. La réponse est validée par le
modèle Recipe ; en cas d'échec, un second appel reçoit les erreurs (section 6, cas d'échec).
"""

from __future__ import annotations

import base64
import json
import re
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from pydantic import BaseModel, Field, ValidationError

from trendforge import analyse, llm
from trendforge.models import Recipe, SourceType

RACINE = Path(__file__).resolve().parents[2]
CACHE = RACINE / ".cache" / "analyses"
RECETTES = RACINE / "recettes"

Progression = Callable[[str], None]


# Schéma de sortie de Claude : types simples (listes plutôt que tuples), converti ensuite en Recipe.
class PartieSortie(BaseModel):
    part: Literal["hook", "setup", "escalation", "twist", "payoff", "list_item", "cta"]
    debut_s: float
    fin_s: float
    pattern: str | None = None
    example: str | None = Field(None, description="Example in the same spirit, NOT copied from the video")
    beats: int | None = None


class SceneSortie(BaseModel):
    part: Literal["hook", "setup", "escalation", "twist", "payoff", "list_item", "cta"]
    animation: str = Field(description="How this part should look and move, to be redrawn as an HTML animation")


class RecetteSortie(BaseModel):
    recipe_id: str = Field(description="lowercase-with-dashes, short, describes the format (not the topic)")
    # contenu
    niche: str
    themes: list[str]
    sources_acceptees: list[Literal["forum", "tendance_x", "tendance_bluesky", "google_trends", "actualite"]]
    angle: str
    transformation: str = Field(description="How a NEW real source must be transformed to stay original")
    format: Literal["narration", "texte_ecran"]
    duree_min_s: float
    duree_max_s: float
    structure: list[PartieSortie]
    pov: Literal["1st_person", "2nd_person", "3rd_person", "narrator"]
    wpm: int = Field(description="120-220")
    reading_level: str
    tone: str
    hashtags: list[str] = Field(description="3 to 5 hashtags")
    # visuel
    ambiance: str
    scene_defaut: str
    scenes: list[SceneSortie]
    changement_s: float = Field(description="seconds between visual changes, 0.8-10")
    zoom_punch: bool
    mots_a_l_ecran: int = Field(description="1-6")
    position_sous_titres: Literal["center", "lower_third"]
    voix_genre: Literal["female", "male"]
    voix_age: str
    voix_vitesse: float = Field(description="0.8-1.2")
    musique: str
    musique_db: float = Field(description="music level under the voice, -30 to -12 dB")
    sfx: list[str]
    why_it_works: str


SYSTEME = """You reverse-engineer short vertical videos (TikTok) into a reusable "recipe" that lets someone make NEW, ORIGINAL videos of the same kind.
The recipe has two independent halves:
- CONTENT: what kind of subject, which real sources can feed it, the promise (angle), the narrative structure with timings, the tone, and how to transform a new real source so the result is original.
- VISUAL: the look and motion of each part, to be redrawn from scratch as an HTML animation (text, emojis, shapes, counters, diagrams; no real footage), the caption style, the voice and the sound.
Rules:
- Describe the format, never the specific story: no names, no facts, no sentences copied from the video. Examples must be invented in the same spirit.
- Target durations must be 21-45 s (short) or 61-90 s (long); keep the source's rhythm but pick the nearest allowed range. The structure starts with the hook and ends before duree_max_s.
- The generated videos are in English, whatever the source language.
- sources_acceptees: which real sources can feed this format (forum = a story pasted from a forum like Reddit; tendance_x / tendance_bluesky / google_trends / actualite = trending topics and news)."""


def _image_bloc(chemin: str) -> dict:
    data = base64.standard_b64encode(Path(chemin).read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}}


def _mesures_texte(tel, trans, pl, oc, au) -> str:
    texte_parle = " ".join(m["texte"] for m in trans.mots)[:6000]
    return f"""Source video measurements:
- duration {tel.duree_s:.1f} s, views {tel.vues}, likes {tel.likes}, caption: {tel.legende[:300]!r}, hashtags {tel.hashtags}
- speech: {"yes" if trans.parle else "no"} (language {trans.langue}), format {trans.format}, words per minute {len(trans.mots) / max(trans.duree_parlee_s, 1) * 60:.0f}
- shots: {pl.nombre}, mean {pl.duree_moyenne_s:.1f} s, rhythm {pl.rythme}, cuts per minute {pl.coupes_par_minute:.0f}
- on-screen text: {oc.images_avec_texte}/{oc.images_analysees} frames, {oc.mots_par_image_moyen:.1f} words per frame, position {oc.position_dominante}, color {oc.couleur_dominante}
- audio: tempo {au.tempo_bpm} bpm, music level relative to voice {au.musique_sous_voix_db} dB, transient hits (sound effects) {au.pics_transitoires}

Transcript with timestamps (for structure and timing only, never reuse its words):
{" ".join(f"[{m['debut']:.1f}] {m['texte']}" for m in trans.mots)[:8000] or "(no speech)"}

On-screen text read by OCR: {oc.texte_reconstruit[:1500]!r}
(Spoken text length: {len(texte_parle)} characters.)

The images are key frames, one per shot, in order."""


def _borne(x: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, x))


def _vers_recette(s: RecetteSortie, tel) -> dict:
    """Convertit la sortie de Claude en recette v3, en ramenant les valeurs dans leurs bornes
    (les bornes numériques du schéma ne sont pas imposées par l'API)."""
    hashtags = list(dict.fromkeys(s.hashtags))[:5]
    for h in ("#fyp", "#foryou", "#viral", "#learnontiktok"):
        if len(hashtags) >= 3:
            break
        if h not in hashtags:
            hashtags.append(h)
    return {
        "schema_version": 3,
        "recipe_id": re.sub(r"[^a-z0-9-]+", "-", s.recipe_id.lower()).strip("-")[:60] or "recette",
        "source": {"url": tel.url if tel.url.startswith("http") else None, "views": tel.vues,
                   "duration_s": tel.duree_s, "language": "en"},
        "contenu": {
            "niche": s.niche, "themes": s.themes, "sources_acceptees": s.sources_acceptees,
            "angle": s.angle, "transformation": s.transformation, "format": s.format, "language": "en",
            "target_duration_s": [s.duree_min_s, s.duree_max_s],
            "structure": [{"part": p.part, "seconds": [p.debut_s, p.fin_s], "pattern": p.pattern,
                           "example": p.example, "beats": p.beats} for p in s.structure],
            "script_style": {"pov": s.pov, "wpm": int(_borne(s.wpm, 120, 220)), "reading_level": s.reading_level, "tone": s.tone},
            "posting": {"hashtags": hashtags},
        },
        "visuel": {
            "moteur": "html", "ambiance": s.ambiance, "fond": "anime", "scene_defaut": s.scene_defaut,
            "scenes": {sc.part: sc.animation for sc in s.scenes},
            "rythme": {"changement_s": _borne(s.changement_s, 0.8, 10), "declencheur": "mots_cles", "zoom_punch": s.zoom_punch},
            "sous_titres": {"style": "word_by_word", "words_on_screen": int(_borne(s.mots_a_l_ecran, 1, 6)),
                            "position": s.position_sous_titres, "use_channel_charter": True},
            "voix": {"gender": s.voix_genre, "age": s.voix_age, "speed": _borne(s.voix_vitesse, 0.8, 1.2),
                     "engine_hint": None},
            "audio": {"music_mood": s.musique, "music_db": _borne(s.musique_db, -40, -10), "sfx": s.sfx},
        },
        "why_it_works": s.why_it_works,
    }


def voix_elevenlabs_par_defaut(genre: str) -> str:
    """Voix de la bibliothèque par défaut du compte (offre gratuite) selon le genre."""
    return "elevenlabs:" + ("FGY2WhTYpPnrIDTdsKH5" if genre == "female" else "TX3LPaxmHKxFdv7VOQHJ")


def extraire_recette(source: str, progression: Progression = print, langue: str | None = "en") -> Path:
    """Lien TikTok ou chemin de fichier .mp4 → recettes/<id>.json. Renvoie le chemin de la recette."""
    horo = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dossier = CACHE / horo
    dossier.mkdir(parents=True, exist_ok=True)
    appels = []
    try:
        progression("1/6 Téléchargement de la vidéo…")
        if Path(source).expanduser().is_file():
            tel = analyse.importer(Path(source).expanduser().resolve(), dossier)
        else:
            try:
                tel = analyse.telecharger(source, dossier)
            except analyse.TelechargementBloque:
                if "tiktok.com" not in source:
                    raise
                # Repli : bouton « Télécharger » de TikTok, dans le Chrome de l'utilisateur.
                from trendforge.telechargement_navigateur import telecharger_via_navigateur

                progression("yt-dlp bloqué par TikTok : passage par ton navigateur.")
                fichier = telecharger_via_navigateur(source, dossier / "navigateur.mp4", progression)
                tel = analyse.importer(fichier, dossier)
                tel.url = source  # garder le lien d'origine dans la recette
        video = Path(tel.fichier)
        if tel.avertissement:
            progression(f"⚠ {tel.avertissement}")
        progression(f"2/6 Transcription ({tel.duree_s:.0f} s de vidéo)…")
        trans = analyse.transcrire(video, dossier, langue=langue)
        progression("3/6 Découpage en plans…")
        pl = analyse.plans(video)
        progression(f"4/6 Texte à l'écran ({pl.nombre} plans)…")
        oc = analyse.ocr(video, pl.debuts_s, tel.duree_s)
        progression("5/6 Analyse du son…")
        au = analyse.audio(video, dossier, trans.mots)
        images = analyse.images_cles(video, dossier, pl.debuts_s, pl.fins_s, tel.duree_s)
        (dossier / "analyse.json").write_text(json.dumps(
            {"telechargement": asdict(tel), "transcription": asdict(trans), "plans": asdict(pl),
             "ocr": {k: v for k, v in asdict(oc).items() if k != "textes"}, "audio": asdict(au)},
            ensure_ascii=False, indent=1, default=str))

        progression(f"6/6 Synthèse par Claude ({len(images)} images clés)…")
        contenu = [_image_bloc(i) for i in images] + [{"type": "text", "text": _mesures_texte(tel, trans, pl, oc, au)}]
        try:
            sortie, a = llm.generer_structure("analyse_recette", SYSTEME, contenu, RecetteSortie, max_tokens=16000)
            appels.append(a)
            d = _vers_recette(sortie, tel)
            d["visuel"]["voix"]["engine_hint"] = voix_elevenlabs_par_defaut(sortie.voix_genre)
            r = Recipe.model_validate(d)
        except ValidationError as e:
            progression("La recette ne passe pas la validation : nouvel essai avec les erreurs…")
            erreurs = "\n".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
            contenu[-1] = {"type": "text", "text": contenu[-1]["text"]
                           + f"\n\nA previous answer failed validation, fix these points:\n{erreurs}"}
            sortie, a = llm.generer_structure("analyse_recette", SYSTEME, contenu, RecetteSortie, max_tokens=16000)
            appels.append(a)
            d = _vers_recette(sortie, tel)
            d["visuel"]["voix"]["engine_hint"] = voix_elevenlabs_par_defaut(sortie.voix_genre)
            r = Recipe.model_validate(d)  # deuxième échec : l'erreur remonte (édition à la main)

        chemin = RECETTES / f"{r.recipe_id}.json"
        n = 2
        while chemin.exists():
            chemin = RECETTES / f"{r.recipe_id}-{n}.json"
            n += 1
        r = r.model_copy(update={"recipe_id": chemin.stem})
        donnees = r.model_dump(mode="json", exclude_none=True)
        donnees["extraite_le"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        donnees["cout_extraction_usd"] = round(sum(x.cout_usd for x in appels), 4)
        chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        progression(f"✓ Recette « {r.recipe_id} » enregistrée ({donnees['cout_extraction_usd']} $).")
        return chemin
    finally:
        # La vidéo source ne sert qu'à l'analyse (section 6) : on ne garde que les mesures.
        for f in dossier.glob("*.mp4"):
            f.unlink()
        if not any(dossier.iterdir()):
            shutil.rmtree(dossier, ignore_errors=True)
