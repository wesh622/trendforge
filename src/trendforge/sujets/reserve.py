"""Réserve de fiches sujet.

Stockage : un seul fichier JSON (`reserve/reserve.json`), écrit de façon atomique
(fichier temporaire puis `replace`). Choix : quelques dizaines à quelques centaines de fiches,
lisible et corrigeable à la main, aucune migration de schéma (pydantic valide à la lecture),
pas de concurrence (un seul processus écrit). SQLite deviendra utile quand on stockera les
embeddings pour le dédoublonnage par similarité ; l'interface `Reserve` ne changera pas.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from trendforge.models import FicheSujet, SourceType
from trendforge.sujets.base import maintenant

NOM_FICHIER = "reserve.json"
PARAMS_PISTAGE = {"ref", "ref_source", "ref_campaign", "share_id", "si", "context", "fbclid", "gclid"}
TYPES_HISTOIRE = {SourceType.forum, SourceType.invente}

# (candidate, fiches existantes) -> True si doublon. Le contrôle par embeddings (cosinus > 0,85)
# sera ajouté ici plus tard, sans toucher au reste.
ControleDoublon = Callable[[FicheSujet, list[FicheSujet]], bool]


def normaliser_url(url: str | None) -> str | None:
    if not url:
        return None
    u = urlsplit(str(url).strip())
    hote = u.netloc.lower().removeprefix("www.").removeprefix("old.").removeprefix("m.")
    params = [(k, v) for k, v in parse_qsl(u.query)
              if not k.lower().startswith("utm_") and k.lower() not in PARAMS_PISTAGE]
    return urlunsplit(("", hote, u.path.rstrip("/"), urlencode(params), ""))


def normaliser_titre(titre: str) -> str:
    t = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def doublon_basique(candidate: FicheSujet, existantes: list[FicheSujet]) -> bool:
    """Même id, même URL normalisée ou même titre normalisé."""
    url = normaliser_url(str(candidate.url) if candidate.url else None)
    titre = normaliser_titre(candidate.titre)
    for f in existantes:
        if f.id == candidate.id:
            return True
        if url and url == normaliser_url(str(f.url) if f.url else None):
            return True
        if titre and titre == normaliser_titre(f.titre):
            return True
    return False


class Reserve:
    def __init__(self, dossier: Path, controles: Iterable[ControleDoublon] = (doublon_basique,)) -> None:
        self.dossier = Path(dossier)
        self.controles = list(controles)

    @property
    def fichier(self) -> Path:
        return self.dossier / NOM_FICHIER

    def charger(self) -> list[FicheSujet]:
        if not self.fichier.exists():
            return []
        brut = json.loads(self.fichier.read_text(encoding="utf-8"))
        return [FicheSujet.model_validate(f) for f in brut.get("fiches", [])]

    def enregistrer(self, fiches: list[FicheSujet]) -> None:
        self.dossier.mkdir(parents=True, exist_ok=True)
        tmp = self.fichier.with_suffix(".tmp")
        donnees = {"version": 1, "fiches": [f.model_dump(mode="json") for f in fiches]}
        tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.fichier)

    def ajouter(self, nouvelles: Iterable[FicheSujet], quand: datetime | None = None) -> dict[str, int]:
        """Ajoute les fiches non doublons et non périmées. Renvoie les compteurs."""
        quand = quand or maintenant()
        fiches = self.charger()
        stats = {"ajoutees": 0, "doublons": 0, "perimees": 0}
        for f in nouvelles:
            if f.est_perimee(quand):
                stats["perimees"] += 1
            elif any(c(f, fiches) for c in self.controles):
                stats["doublons"] += 1
            else:
                fiches.append(f)
                stats["ajoutees"] += 1
        self.enregistrer(fiches)
        return stats

    def purger(self, quand: datetime | None = None, heures: int = 48) -> list[FicheSujet]:
        """Retire les tendances de plus de `heures` heures ; renvoie les fiches retirées."""
        quand = quand or maintenant()
        fiches = self.charger()
        gardees = [f for f in fiches if not f.est_perimee(quand, heures)]
        retirees = [f for f in fiches if f.est_perimee(quand, heures)]
        if retirees:
            self.enregistrer(gardees)
        return retirees

    def retirer(self, id_: str) -> bool:
        fiches = self.charger()
        reste = [f for f in fiches if f.id != id_]
        if len(reste) != len(fiches):
            self.enregistrer(reste)
        return len(reste) != len(fiches)

    def vider(self) -> None:
        self.enregistrer([])

    def selection(self, quand: datetime | None = None) -> list[FicheSujet]:
        """Ordre de sélection (section 7) : tendances encore fraîches, puis histoires collées,
        les plus récentes d'abord dans chaque groupe. Le filtre « qui collent à la recette »
        sera appliqué par l'étape de génération."""
        quand = quand or maintenant()
        fiches = [f for f in self.charger() if not f.est_perimee(quand)]
        tendances = [f for f in fiches if f.type not in TYPES_HISTOIRE]
        histoires = [f for f in fiches if f.type in TYPES_HISTOIRE]
        cle = lambda f: f.date_source  # noqa: E731
        return sorted(tendances, key=cle, reverse=True) + sorted(histoires, key=cle, reverse=True)
