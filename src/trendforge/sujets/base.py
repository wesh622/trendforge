"""Interface commune des sources de sujets (section 7, « Sources de sujets »).

Chaque source est un plugin isolé : `collecter_toutes` attrape les erreurs source
par source, une source en panne n'empêche donc jamais les autres de remplir la réserve.
"""

from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable, Protocol

import httpx

from trendforge.models import FicheSujet, SourceType

log = logging.getLogger(__name__)

USER_AGENT = "TrendForge/0.1"
TIMEOUT_S = 15.0


def client_http(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Client HTTP générique : User-Agent neutre, aucune donnée personnelle."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT_S,
        follow_redirects=True,
        transport=transport,
    )


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def id_fiche(type_: SourceType, cle: str) -> str:
    """Identifiant stable : même source + même lien/titre -> même id."""
    h = hashlib.sha1(f"{type_.value}|{cle.strip().lower()}".encode()).hexdigest()[:12]
    return f"{type_.value}-{h}"


def phrases(texte: str, n: int = 2, max_car: int = 300) -> str:
    """Les n premières phrases (résumé provisoire, en attendant la réduction par Claude)."""
    propre = re.sub(r"\s+", " ", texte).strip()
    morceaux = re.split(r"(?<=[.!?])\s+", propre)
    out = " ".join(morceaux[:n]).strip()
    if len(out) > max_car:
        out = out[: max_car - 1].rsplit(" ", 1)[0] + "…"
    return out


class ErreurSource(Exception):
    """Erreur attendue d'une source (réponse inattendue, service indisponible…)."""


class SourceSujets(ABC):
    """Plugin de source de sujets."""

    nom: str = "source"

    def disponible(self) -> tuple[bool, str]:
        """(True, "") si la source peut tourner ; sinon (False, raison lisible)."""
        return True, ""

    @abstractmethod
    def collecter(self) -> list[FicheSujet]:
        """Renvoie des fiches sujet valides. Peut lever une exception : elle sera isolée."""


@dataclass
class ResultatSource:
    nom: str
    fiches: list[FicheSujet] = field(default_factory=list)
    statut: str = "ok"  # ok | desactivee | erreur
    message: str = ""


def collecter_toutes(sources: Iterable[SourceSujets]) -> list[ResultatSource]:
    resultats = []
    for s in sources:
        ok, raison = s.disponible()
        if not ok:
            resultats.append(ResultatSource(s.nom, statut="desactivee", message=raison))
            continue
        try:
            fiches = s.collecter()
            resultats.append(ResultatSource(s.nom, fiches, message=f"{len(fiches)} fiche(s)"))
        except Exception as e:  # isolement volontaire : une source ne casse pas les autres
            log.exception("source %s en panne", s.nom)
            resultats.append(ResultatSource(s.nom, statut="erreur", message=f"{type(e).__name__}: {e}"))
    return resultats


# --- Points d'extension (branchés plus tard) -------------------------------------


class ReducteurFiche(Protocol):
    """Réduction d'un post (texte_source) en « fiche situation » : personnages, conflit,
    détail marquant, rebondissement, résumé neutre. Sera implémenté par un appel à Claude
    (section 7, « Règles de transformation »). Doit renvoyer une NOUVELLE fiche."""

    def __call__(self, fiche: FicheSujet) -> FicheSujet: ...


def reducteur_identite(fiche: FicheSujet) -> FicheSujet:
    """Réducteur par défaut, sans LLM : la fiche reste provisoire (titre/résumé = premières phrases)."""
    return fiche


FiltreModeration = Callable[[FicheSujet], bool]
"""Renvoie True si la fiche doit être écartée (décès, drames, politique…). À brancher plus tard."""
