"""Tendances X (Twitter) via l'API officielle v2, payée à l'usage.

Endpoint retenu (vérifié sur docs.x.com, page « Get Trends by WOEID ») :
    GET https://api.x.com/2/trends/by/woeid/{woeid}?max_trends=1..50&trend.fields=trend_name,tweet_count
    Auth : Bearer token (ou OAuth 2.0 utilisateur).
    Réponse : {"data": [{"trend_name": str, "tweet_count": int}], "errors": [...],
               "meta": {"location": {...}}}
Tarif (docs.x.com, page Pricing) : 0,010 $ par requête Trends ; lecture de posts 0,005 $ par
post renvoyé. Avec un plafond de 3 $/mois, on ne lit donc PAS les posts de chaque tendance
(la recherche récente renvoie au moins 10 posts, soit ≥ 0,05 $ par sujet) : la fiche cite un
lien de recherche x.com et 2 articles Google Actualités pour le contexte.

Le jeton est lu dans la variable d'environnement X_BEARER_TOKEN, jamais en dur. Sans jeton,
la source se désactive proprement. Chaque appel est compté dans un fichier JSON persistant
(par mois calendaire UTC) ; si l'appel ferait dépasser le plafond, il n'est pas fait.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from trendforge.models import FicheSujet, Reference, SourceType
from trendforge.sujets.base import ErreurSource, SourceSujets, client_http, id_fiche, maintenant

API = "https://api.x.com/2"
WOEID_USA = 23424977
VAR_JETON = "X_BEARER_TOKEN"
COUT_PAR_APPEL_DEFAUT = 0.02  # prudent : le double du tarif publié (0,010 $)
PLAFOND_MENSUEL_DEFAUT = 3.0


class PlafondAtteint(ErreurSource):
    pass


@dataclass
class CompteurDepenses:
    """Compteur mensuel persistant (fichier JSON). Remis à zéro au changement de mois."""

    fichier: Path
    plafond: float = PLAFOND_MENSUEL_DEFAUT

    @staticmethod
    def _mois(quand: datetime) -> str:
        return quand.strftime("%Y-%m")

    def lire(self, quand: datetime | None = None) -> dict[str, Any]:
        mois = self._mois(quand or maintenant())
        try:
            d = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        if d.get("mois") != mois:
            d = {"mois": mois, "depense": 0.0, "appels": 0}
        return d

    def depense(self, quand: datetime | None = None) -> float:
        return float(self.lire(quand)["depense"])

    def peut_depenser(self, montant: float, quand: datetime | None = None) -> bool:
        return self.depense(quand) + montant <= self.plafond + 1e-9

    def enregistrer(self, montant: float, quand: datetime | None = None) -> None:
        d = self.lire(quand)
        d["depense"] = round(d["depense"] + montant, 4)
        d["appels"] += 1
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.fichier.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
        tmp.replace(self.fichier)


def parser_tendances_x(donnees: dict[str, Any]) -> list[dict[str, Any]]:
    if "data" not in donnees:
        erreurs = donnees.get("errors") or donnees.get("detail") or donnees
        raise ErreurSource(f"réponse X sans 'data' : {erreurs}")
    return [{"nom": t["trend_name"], "posts": t.get("tweet_count")}
            for t in donnees["data"] if t.get("trend_name")]


class ClientX:
    def __init__(self, jeton: str, compteur: CompteurDepenses, cout_par_appel: float = COUT_PAR_APPEL_DEFAUT,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.jeton = jeton
        self.compteur = compteur
        self.cout_par_appel = cout_par_appel
        self.transport = transport

    def _get(self, chemin: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.compteur.peut_depenser(self.cout_par_appel):
            raise PlafondAtteint(
                f"plafond X atteint ({self.compteur.depense():.2f} $ / {self.compteur.plafond:.2f} $ ce mois-ci), "
                "relevé sauté")
        with client_http(self.transport) as c:
            r = c.get(f"{API}{chemin}", params=params, headers={"Authorization": f"Bearer {self.jeton}"})
        # compté dès qu'une réponse arrive (prudent : on ne sait pas toujours si une erreur est facturée)
        self.compteur.enregistrer(self.cout_par_appel)
        if r.status_code in (401, 403):
            raise ErreurSource(f"X a refusé le jeton ({r.status_code}) : {r.text[:200]}")
        if r.status_code == 402:
            raise ErreurSource("X : crédits épuisés sur le compte développeur (402)")
        r.raise_for_status()
        return r.json()

    def tendances(self, woeid: int = WOEID_USA, max_trends: int = 20) -> list[dict[str, Any]]:
        return parser_tendances_x(self._get(
            f"/trends/by/woeid/{woeid}",
            {"max_trends": max_trends, "trend.fields": "trend_name,tweet_count"}))


class SourceX(SourceSujets):
    nom = "x"

    def __init__(self, fichier_depenses: Path, woeid: int = WOEID_USA, limite: int = 10,
                 cout_par_appel: float = COUT_PAR_APPEL_DEFAUT, plafond: float = PLAFOND_MENSUEL_DEFAUT,
                 contexte_google: bool = True, transport: httpx.BaseTransport | None = None) -> None:
        self.jeton = os.environ.get(VAR_JETON, "").strip()
        self.compteur = CompteurDepenses(Path(fichier_depenses), plafond)
        self.woeid = woeid
        self.limite = limite
        self.cout_par_appel = cout_par_appel
        self.contexte_google = contexte_google
        self.transport = transport

    def disponible(self) -> tuple[bool, str]:
        if not self.jeton:
            return False, f"pas de jeton X (variable {VAR_JETON} absente) : source désactivée"
        if not self.compteur.peut_depenser(self.cout_par_appel):
            return False, (f"plafond mensuel atteint ({self.compteur.depense():.2f} $ / "
                           f"{self.compteur.plafond:.2f} $) : relevé sauté")
        return True, ""

    def collecter(self) -> list[FicheSujet]:
        client = ClientX(self.jeton, self.compteur, self.cout_par_appel, self.transport)
        releve = maintenant()
        fiches = []
        for t in client.tendances(self.woeid, max_trends=self.limite):
            recherche = f"https://x.com/search?q={quote(t['nom'])}&f=top"
            refs = [Reference(titre=f"Posts les plus vus sur X : {t['nom']}", url=recherche)]
            if self.contexte_google:
                try:
                    from trendforge.sujets.google import rechercher_articles
                    with client_http(self.transport) as c:
                        refs += rechercher_articles(c, t["nom"].lstrip("#"), n=2)
                except Exception:  # le contexte Google est un bonus, jamais bloquant
                    pass
            volume = f" ({t['posts']} posts)" if t["posts"] else ""
            fiches.append(FicheSujet(
                id=id_fiche(SourceType.tendance_x, t["nom"]),
                type=SourceType.tendance_x,
                url=recherche,
                date_source=releve,  # X ne donne pas la date de début de la tendance
                ajoutee_le=releve,
                titre=t["nom"],
                resume=f"Tendance X{volume}",
                references=refs,
            ))
        return fiches
