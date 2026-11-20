"""Filtre de modération minimal des tendances, sans LLM (section 7, « Règles de transformation »).

Écarte ce qui est sensible : décès, drames, politique, accusations, rumeurs. Volontairement large :
un faux positif coûte un sujet, un faux négatif peut coûter le compte. Le filtre par Claude, plus fin,
viendra s'ajouter quand une clé sera disponible ; tu gardes le dernier mot dans la file de validation.
"""

from __future__ import annotations

import re

from trendforge.models import FicheSujet, SourceType

MOTS_SENSIBLES = {
    "deces": r"\b(dies|died|dead|death|deaths|killed|killing|obituary|funeral|passed away|mourn\w*|fatal\w*)\b",
    "violence": r"\b(shooting|shot|stabb\w*|murder\w*|massacre|genocide|terror\w*|attack(ed|s)?|bomb\w*|war|hostage\w*)\b",
    "drame": r"\b(crash|wreck|disaster|tragedy|victims?|injured|missing child|abuse\w*|assault\w*|suicide)\b",
    "politique": r"\b(trump|biden|harris|vance|putin|xi|netanyahu|zelensky\w*|election\w*|senat\w*|congress|"
                 r"democrat\w*|republican\w*|gop|white house|parliament|poll(s|ing)?|campaign|impeach\w*|president)\b",
    "accusation": r"\b(arrest\w*|charged|indict\w*|accus\w*|alleg\w*|lawsuit|sued|convicted|sentenced|scandal)\b",
    "rumeur": r"\b(rumou?r\w*|unconfirmed|leaked|reportedly)\b",
}
_REGEX = {k: re.compile(v, re.IGNORECASE) for k, v in MOTS_SENSIBLES.items()}


def raisons(fiche: FicheSujet) -> list[str]:
    """Catégories sensibles détectées dans le titre, le résumé et les titres des références."""
    texte = " ".join([fiche.titre, fiche.resume, *(r.titre for r in fiche.references)])
    return [k for k, rx in _REGEX.items() if rx.search(texte)]


def ecarter(fiche: FicheSujet) -> bool:
    """FiltreModeration par défaut : True = fiche écartée. Les histoires collées à la main ne sont pas filtrées ici
    (tu les as choisies ; le rédacteur applique ses propres règles)."""
    if fiche.type in {SourceType.forum, SourceType.invente}:
        return False
    return bool(raisons(fiche))
