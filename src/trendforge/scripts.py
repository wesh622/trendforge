"""Rédaction du script (section 7, étapes 2 et 3) à partir du bloc contenu d'une recette et d'une fiche sujet.

Le rédacteur ne lit que `recette.contenu` : le bloc visuel n'a aucune influence sur le texte."""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from trendforge import llm
from trendforge.models import FicheSujet, Recipe, SourceType
from trendforge.voix import DEBIT_KOKORO_1X, vitesse_pour_debit

DEBIT_ELEVENLABS_1X = 140.0  # mots/min à vitesse 1,0 (mesuré)


class Variante(BaseModel):
    hook: str
    script: str = Field(description="Texte complet à lire, hook compris, sans indications de mise en scène")
    angle: str = Field(description="L'angle propre ajouté : verdict, rebondissement, question au public…")


class Variantes(BaseModel):
    variantes: list[Variante] = Field(min_length=3, max_length=3)


class ScriptFinal(BaseModel):
    variante_choisie: int = Field(ge=1, le=3)
    raison: str
    hook: str
    script: str
    titre: str
    legende: str
    hashtags: list[str] = Field(min_length=3, max_length=5)


class NoteHook(BaseModel):
    question_ouverte: bool
    detail_concret: bool
    enjeu_ou_conflit: bool
    promesse_tenue: bool
    commentaire: str


SYSTEME_REDACTEUR = """You write voice-over scripts for faceless short-form vertical videos (TikTok), in English.
Rules:
- Spoken text only: no stage directions, no emojis, no hashtags inside the script.
- Grade-6 reading level, short sentences, concrete details.
- The hook is the first sentence: at most 10 words, it opens a question without answering it, contains a concrete detail and a conflict or stake, and its promise is kept later in the script (no clickbait).
- Never copy sentences from the source material. Rewrite everything in your own words.
- For a forum story: change the names, the place and the job, change at least two other details, and add your own angle (a verdict, a twist, or a question to the audience). Never claim the story is true. Never mention Reddit or any username.
- For a trending topic: use only facts present in the provided sources; if something is uncertain, say so or leave it out. No accusations against private individuals, no unconfirmed rumors."""


def _bloc_sujet(fiche: FicheSujet) -> str:
    """Ce que le rédacteur reçoit du sujet. Jamais le texte brut d'un post de forum."""
    d = {
        "type": fiche.type.value,
        "title": fiche.titre,
        "summary": fiche.resume,
        "characters": fiche.personnages,
        "conflict": fiche.conflit,
        "striking_detail": fiche.detail_marquant,
        "twist": fiche.rebondissement,
    }
    if fiche.type != SourceType.forum:
        d["sources"] = [r.model_dump(mode="json") for r in fiche.references]
    return json.dumps(d, ensure_ascii=False, indent=2)


def mots_cibles(recette: Recipe) -> int:
    """Nombre de mots pour tomber au milieu de la fourchette, au débit réel de Kokoro."""
    c = recette.contenu
    if (recette.visuel.voix.engine_hint or "").startswith("elevenlabs:"):
        # Débit réel mesuré (voix Liam, 20/11/2026) : 114 mots en 46,4 s à vitesse 1,05.
        debit_reel = DEBIT_ELEVENLABS_1X * recette.visuel.voix.speed
        lo, hi = c.target_duration_s
        return round((lo + hi) / 2 / 60 * debit_reel)
    vitesse = vitesse_pour_debit(c.script_style.wpm)
    debit_reel = DEBIT_KOKORO_1X * vitesse
    lo, hi = c.target_duration_s
    return round((lo + hi) / 2 / 60 * debit_reel)


def prompt_variantes(recette: Recipe, fiche: FicheSujet, consignes: str | None = None) -> str:
    c = recette.contenu
    structure = [p.model_dump(exclude_none=True) for p in c.structure]
    return f"""Write 3 different script variants for this video.

Recipe (structure to follow, with approximate timing in seconds):
{json.dumps(structure, ensure_ascii=False, indent=2)}

Promise of the format: {c.angle}
How to transform the real source so the result is original: {c.transformation}
Style: point of view {c.script_style.pov}, tone "{c.script_style.tone}", reading level {c.script_style.reading_level}.
Length: about {mots_cibles(recette)} words each (target duration {c.target_duration_s[0]:.0f}-{c.target_duration_s[1]:.0f} s).
Call to action: {next((p.pattern for p in c.structure if p.part == "cta" and p.pattern), "a question to the audience")}.

Subject (the only material you may use):
{_bloc_sujet(fiche)}

Make the 3 variants genuinely different in hook and angle.""" + (
        f"\n\nExtra instructions from the channel owner (follow them unless they break the rules):\n{consignes}"
        if consignes else "")


def ecrire_script(recette: Recipe, fiche: FicheSujet,
                  consignes: str | None = None) -> tuple[ScriptFinal, list[llm.Appel]]:
    variantes, a1 = llm.generer_structure("variantes_script", SYSTEME_REDACTEUR,
                                          prompt_variantes(recette, fiche, consignes), Variantes)
    choix_prompt = f"""Here are 3 script variants for the same video. Pick the best one for retention (hook strength, rhythm, originality), then improve it.
Keep about {mots_cibles(recette)} words. Keep the structure of the recipe. Then write a short title, a caption (one or two sentences, no hashtags) and 3 to 5 hashtags.

{variantes.model_dump_json(indent=2)}

Recipe hashtags you may reuse: {recette.contenu.posting.hashtags}""" + (
        f"\n\nExtra instructions from the channel owner:\n{consignes}" if consignes else "")
    final, a2 = llm.generer_structure("choix_script", SYSTEME_REDACTEUR, choix_prompt, ScriptFinal)
    return final, [a1, a2]


def mots(texte: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9'’-]+", texte)


def noter_hook(hook: str, script: str, wpm: float) -> tuple[int, dict, llm.Appel | None]:
    """Grille de la section 7 : 5 critères à 2 points. Le critère de longueur est calculé, pas noté par l'IA."""
    n = len(mots(hook))
    duree = n / wpm * 60
    longueur_ok = n <= 10 and duree <= 3.5
    note, appel = llm.generer_structure(
        "score_hook",
        "You grade the opening hook of a short video script. Be strict and literal.",
        f"Hook: {hook!r}\n\nFull script:\n{script}\n\nFor each criterion answer true or false.",
        NoteHook, max_tokens=2000)
    criteres = {
        "question_ouverte": note.question_ouverte,
        "detail_concret": note.detail_concret,
        "longueur": longueur_ok,
        "enjeu_ou_conflit": note.enjeu_ou_conflit,
        "promesse_tenue": note.promesse_tenue,
    }
    return 2 * sum(criteres.values()), {**criteres, "mots": n, "duree_s": round(duree, 2),
                                        "commentaire": note.commentaire}, appel


class ScriptAjuste(BaseModel):
    script: str


def ajuster_longueur(recette: Recipe, texte: str, duree_s: float, mots_vises: int) -> tuple[str, llm.Appel]:
    """Rallonge ou resserre le script (section 7, étape 5) en gardant hook, structure et faits."""
    sens = "Shorten" if duree_s > recette.contenu.target_duration_s[1] else "Lengthen"
    prompt = f"""{sens} this voice-over script to about {mots_vises} words (it currently reads in {duree_s:.0f} s; target {recette.contenu.target_duration_s[0]:.0f}-{recette.contenu.target_duration_s[1]:.0f} s).
Keep the hook (first sentence) word for word, keep the structure and the call to action, keep only facts already present. Return the full new script.

{texte}"""
    r, a = llm.generer_structure("choix_script", SYSTEME_REDACTEUR, prompt, ScriptAjuste)
    return r.script, a


# --------------------------------------------------------------------------- fiche situation


class FicheSituation(BaseModel):
    titre: str = Field(description="Neutral 5-10 word title, no names")
    resume: str = Field(description="Neutral two-sentence summary, no usernames")
    personnages: list[str] = Field(description="Roles only (e.g. 'the narrator', 'her sister'), no names")
    conflit: str
    detail_marquant: str
    rebondissement: str | None


def reducteur_claude(fiche: FicheSujet) -> FicheSujet:
    """Réduit le texte d'un post collé en fiche situation (section 7, « Règles de transformation »).

    Le texte source reste dans la fiche pour le contrôle de similarité, mais le rédacteur du
    script ne reçoit que la fiche (voir _bloc_sujet)."""
    if not fiche.texte_source:
        return fiche
    r, _ = llm.generer_structure(
        "fiche_situation",
        "You reduce a forum post to a neutral situation sheet. Never copy sentences, never keep names or usernames.",
        f"Post:\n{fiche.texte_source[:12000]}", FicheSituation, max_tokens=3000)
    return fiche.model_copy(update={
        "titre": r.titre, "resume": r.resume, "personnages": r.personnages, "conflit": r.conflit,
        "detail_marquant": r.detail_marquant, "rebondissement": r.rebondissement})
