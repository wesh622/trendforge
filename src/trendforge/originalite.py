"""Contrôles d'originalité du script (section 7, « Définitions des contrôles qualité »).

- recouvrement lexical : part des suites de 5 mots du script présentes dans la source (seuil 3 %) ;
- recouvrement de sens : part des phrases du script dont la similarité cosinus avec au moins
  une phrase de la source dépasse 0,85 (seuil 10 %), embeddings `BAAI/bge-small-en-v1.5`
  via fastembed (CPU, ONNX) ;
- similarité entre scripts complets (vidéos passées), seuil provisoire 0,90.

Le modèle d'embeddings est chargé une seule fois, à la première utilisation
(`modele_embeddings()`), et peut être libéré avec `liberer_modele()`.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

RACINE = Path(__file__).resolve().parents[2]
CACHE_FASTEMBED = RACINE / "modeles" / "fastembed"
NOM_MODELE = "BAAI/bge-small-en-v1.5"

TAILLE_NGRAMME = 5
SEUIL_LEXICAL = 0.03  # part max de suites de 5 mots communes
SEUIL_COSINUS_PHRASE = 0.85  # une phrase « recopiée en sens » dépasse ce cosinus
SEUIL_SENS = 0.10  # part max de phrases recopiées en sens
SEUIL_SCRIPTS = 0.90  # provisoire, étalonné en V0 (section 12, point 6)
MIN_MOTS_PHRASE = 3  # les phrases plus courtes (« Wow. », « Yes. ») sont ignorées

# --------------------------------------------------------------------------- modèle

_modele = None
_verrou = threading.Lock()


def modele_embeddings():
    """Singleton paresseux du modèle fastembed (téléchargé au besoin dans modeles/fastembed/)."""
    global _modele
    if _modele is None:
        with _verrou:
            if _modele is None:
                from fastembed import TextEmbedding

                CACHE_FASTEMBED.mkdir(parents=True, exist_ok=True)
                _modele = TextEmbedding(NOM_MODELE, cache_dir=str(CACHE_FASTEMBED))
    return _modele


def liberer_modele() -> None:
    """Libère le modèle (mémoire ONNX) ; il sera rechargé au prochain appel."""
    global _modele
    with _verrou:
        _modele = None
    import gc

    gc.collect()


def embeddings(textes: list[str]) -> np.ndarray:
    """Embeddings normalisés (norme 1), une ligne par texte."""
    if not textes:
        return np.zeros((0, 384), dtype=np.float32)
    v = np.asarray(list(modele_embeddings().embed(textes)), dtype=np.float32)
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / np.maximum(n, 1e-12)


# --------------------------------------------------------------------------- texte


def mots_normalises(texte: str) -> list[str]:
    """Minuscules, sans accents ni ponctuation (les apostrophes sont collées : don't → dont)."""
    t = unicodedata.normalize("NFKD", texte.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"['’`´]", "", t)
    return re.findall(r"[^\W_]+", t)


def decouper_phrases(texte: str) -> list[str]:
    """Découpe en phrases sur . ! ? … et les retours à la ligne."""
    morceaux = re.split(r"(?<=[.!?…])[\"'”»)\]]*\s+|\n+", texte)
    return [m.strip() for m in morceaux if m and m.strip()]


def _ngrammes(mots: list[str], n: int = TAILLE_NGRAMME) -> list[tuple[str, ...]]:
    return [tuple(mots[i : i + n]) for i in range(len(mots) - n + 1)]


# --------------------------------------------------------------------------- mesures


def _lexical(script: str, source: str) -> tuple[float, list[str]]:
    mots = mots_normalises(script)
    ng_script = _ngrammes(mots)
    if not ng_script:
        return 0.0, []
    ng_source = set(_ngrammes(mots_normalises(source)))
    communs = [g in ng_source for g in ng_script]
    part = sum(communs) / len(ng_script)
    # passages fautifs : suites contiguës de n-grammes communs, fusionnées en plages de mots
    passages, i = [], 0
    while i < len(communs):
        if communs[i]:
            j = i
            while j + 1 < len(communs) and communs[j + 1]:
                j += 1
            passages.append(" ".join(mots[i : j + TAILLE_NGRAMME]))
            i = j + 1
        else:
            i += 1
    return part, passages


def recouvrement_lexical(script: str, source: str) -> float:
    """Part (0-1) des suites de 5 mots normalisés du script présentes dans la source."""
    return _lexical(script, source)[0]


def _phrases_utiles(texte: str) -> list[str]:
    return [p for p in decouper_phrases(texte) if len(mots_normalises(p)) >= MIN_MOTS_PHRASE]


def _sens(
    script: str, source: str, seuil_cosinus: float = SEUIL_COSINUS_PHRASE
) -> tuple[float, list[tuple[str, str, float]]]:
    ph_script, ph_source = _phrases_utiles(script), _phrases_utiles(source)
    if not ph_script or not ph_source:
        return 0.0, []
    e = embeddings(ph_script + ph_source)
    sim = e[: len(ph_script)] @ e[len(ph_script) :].T
    meilleur = sim.argmax(axis=1)
    fautifs = [
        (ph_script[i], ph_source[meilleur[i]], float(sim[i, meilleur[i]]))
        for i in range(len(ph_script))
        if sim[i, meilleur[i]] > seuil_cosinus
    ]
    return len(fautifs) / len(ph_script), fautifs


def recouvrement_sens(script: str, source: str, seuil_cosinus: float = SEUIL_COSINUS_PHRASE) -> float:
    """Part (0-1) des phrases du script (>= 3 mots) dont le cosinus avec au moins une
    phrase de la source dépasse `seuil_cosinus` (0,85)."""
    return _sens(script, source, seuil_cosinus)[0]


def similarite_scripts(a: str, b: str) -> float:
    """Cosinus entre les embeddings des deux scripts complets."""
    e = embeddings([a, b])
    return float(e[0] @ e[1])


def scripts_trop_proches(a: str, b: str, seuil: float = SEUIL_SCRIPTS) -> bool:
    """Vrai si `a` est trop proche de `b` (seuil provisoire 0,90, à étalonner en V0)."""
    return similarite_scripts(a, b) >= seuil


# --------------------------------------------------------------------------- contrôle


@dataclass
class ResultatSource:
    lexical: float
    sens: float
    seuil_lexical: float = SEUIL_LEXICAL
    seuil_sens: float = SEUIL_SENS
    seuil_cosinus: float = SEUIL_COSINUS_PHRASE
    passages_lexicaux: list[str] = field(default_factory=list)
    # (phrase du script, phrase la plus proche de la source, cosinus)
    phrases_proches: list[tuple[str, str, float]] = field(default_factory=list)

    @property
    def ok_lexical(self) -> bool:
        return self.lexical < self.seuil_lexical

    @property
    def ok_sens(self) -> bool:
        return self.sens < self.seuil_sens

    @property
    def ok(self) -> bool:
        return self.ok_lexical and self.ok_sens

    @property
    def raisons(self) -> list[str]:
        r = []
        if not self.ok_lexical:
            r.append(f"recouvrement lexical {self.lexical:.1%} >= {self.seuil_lexical:.0%}")
        if not self.ok_sens:
            r.append(f"recouvrement de sens {self.sens:.1%} >= {self.seuil_sens:.0%}")
        return r


def controle_source(
    script: str,
    source: str,
    seuil_lexical: float = SEUIL_LEXICAL,
    seuil_sens: float = SEUIL_SENS,
    seuil_cosinus: float = SEUIL_COSINUS_PHRASE,
) -> ResultatSource:
    """Contrôle « similarité avec la source » (texte du post collé ou transcription de la vidéo)."""
    lex, passages = _lexical(script, source)
    sens, proches = _sens(script, source, seuil_cosinus)
    return ResultatSource(
        lexical=lex,
        sens=sens,
        seuil_lexical=seuil_lexical,
        seuil_sens=seuil_sens,
        seuil_cosinus=seuil_cosinus,
        passages_lexicaux=passages,
        phrases_proches=proches,
    )
