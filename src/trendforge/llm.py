"""Couche unique d'appel aux modèles (section 9, « Couche LLM »).

Le cahier prévoyait LiteLLM ; on passe par le SDK officiel Anthropic, derrière cette interface,
pour que le reste du code ne dépende pas du fournisseur. Le modèle est choisi par tâche (TACHES).
La clé est lue dans le trousseau du système (keyring), sinon dans ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TypeVar

import anthropic
from pydantic import BaseModel

SERVICE_TROUSSEAU = "trendforge"

# Prix en $ par million de jetons (entrée, sortie) — à revérifier, voir section 10.
PRIX = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

# Choix du modèle et de l'effort par tâche (modifiable dans les réglages plus tard).
TACHES: dict[str, dict] = {
    "variantes_script": {"modele": "claude-haiku-5-5", "effort": "low"},
    "choix_script": {"modele": "claude-sonnet-5-5", "effort": "medium"},
    "score_hook": {"modele": "claude-haiku-5-5", "effort": "low"},
    "fiche_situation": {"modele": "claude-haiku-5-5", "effort": "low"},
    "analyse_recette": {"modele": "claude-sonnet-5-5", "effort": "medium"},
    "recette_personnalisee": {"modele": "claude-sonnet-5-5", "effort": "medium"},
    # Page HTML animée (moteur visuel HTML, section 7) : code long et exigeant → Opus.
    "animation_html": {"modele": "claude-opus-5-5", "effort": "medium"},  # choix d'Omar 20/11/2026 (high : 0,74 $)
}

T = TypeVar("T", bound=BaseModel)


class CleAbsente(RuntimeError):
    pass


class Refus(RuntimeError):
    """Le modèle (et ses modèles de secours) a refusé la demande."""


@dataclass
class Appel:
    modele: str
    jetons_entree: int
    jetons_sortie: int
    cout_usd: float
    request_id: str | None


def lire_cle() -> str:
    try:
        import keyring

        cle = keyring.get_password(SERVICE_TROUSSEAU, "anthropic")
    except Exception:  # noqa: BLE001 — trousseau indisponible (session sans D-Bus, etc.)
        cle = None
    cle = cle or os.environ.get("ANTHROPIC_API_KEY")
    if not cle:
        raise CleAbsente(
            "Aucune clé Anthropic. Enregistre-la avec : uv run trendforge config cle-anthropic"
        )
    return cle


def enregistrer_cle(cle: str) -> None:
    import keyring

    keyring.set_password(SERVICE_TROUSSEAU, "anthropic", cle)


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=lire_cle(), max_retries=3)
    return _client


def cout(modele: str, entree: int, sortie: int) -> float:
    pe, ps = PRIX.get(modele, PRIX["claude-opus-5-5"])
    return (entree * pe + sortie * ps) / 1_000_000


def generer_structure(tache: str, systeme: str, message: str | list, schema: type[T],
                      max_tokens: int = 8000) -> tuple[T, Appel]:
    """Un appel, réponse validée par le schéma Pydantic. Lève Refus si tout a refusé.

    `message` est un texte, ou une liste de blocs de contenu (images + texte) pour la vision.
    """
    conf = TACHES[tache]
    modele = conf["modele"]
    params = dict(
        model=modele,
        max_tokens=max_tokens,
        system=systeme,
        messages=[{"role": "user", "content": message}],
        output_format=schema,
        output_config={"effort": conf["effort"]},
    )
    c = client()
    if modele == "claude-sonnet-5-5":
        # Repli côté serveur en cas de refus d'un classifieur de sécurité.
        rep = c.beta.messages.parse(**params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    else:
        rep = c.messages.parse(**params)
    if rep.stop_reason == "refusal":
        cat = getattr(rep.stop_details, "category", None) if rep.stop_details else None
        raise Refus(f"refus ({cat}) pour la tâche {tache}")
    if rep.stop_reason == "max_tokens":
        raise RuntimeError(f"réponse tronquée (max_tokens={max_tokens}) pour la tâche {tache}")
    u = rep.usage
    appel = Appel(rep.model, u.input_tokens, u.output_tokens,
                  cout(rep.model, u.input_tokens, u.output_tokens), getattr(rep, "_request_id", None))
    return rep.parsed_output, appel


def generer_texte(tache: str, systeme: str, message: str, max_tokens: int = 64000) -> tuple[str, Appel]:
    """Un appel en streaming pour une réponse longue en texte libre (ex. une page HTML).

    Streaming obligatoire : avec un max_tokens élevé, un appel non streamé dépasserait le délai HTTP.
    """
    conf = TACHES[tache]
    modele = conf["modele"]
    params = dict(
        model=modele,
        max_tokens=max_tokens,
        system=systeme,
        messages=[{"role": "user", "content": message}],
        output_config={"effort": conf["effort"]},
    )
    c = client()
    if modele in ("claude-opus-5-5", "claude-sonnet-5-5"):
        flux = c.beta.messages.stream(**params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    else:
        flux = c.messages.stream(**params)
    with flux as stream:
        rep = stream.get_final_message()
    if rep.stop_reason == "refusal":
        cat = getattr(rep.stop_details, "category", None) if rep.stop_details else None
        raise Refus(f"refus ({cat}) pour la tâche {tache}")
    if rep.stop_reason == "max_tokens":
        raise RuntimeError(f"réponse tronquée (max_tokens={max_tokens}) pour la tâche {tache}")
    texte = "".join(b.text for b in rep.content if b.type == "text")
    u = rep.usage
    appel = Appel(rep.model, u.input_tokens, u.output_tokens,
                  cout(rep.model, u.input_tokens, u.output_tokens), getattr(rep, "_request_id", None))
    return texte, appel
