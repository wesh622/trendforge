"""Voix ElevenLabs (section 7, étape 4, version 3) : audio + horodatage de chaque mot en un appel.

La clé est lue dans le trousseau (service « trendforge », nom « elevenlabs »), sinon dans
ELEVENLABS_API_KEY. Le recette indique la voix par `engine_hint = "elevenlabs:<voice_id>"`.
"""

from __future__ import annotations

import base64
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

from trendforge.captions import Mot

API = "https://api.elevenlabs.io/v1"
MODELE = "eleven_multilingual_v2"
VITESSE_MIN, VITESSE_MAX = 0.7, 1.2  # bornes acceptées par l'API pour voice_settings.speed


class CleElevenLabsAbsente(RuntimeError):
    pass


class ErreurElevenLabs(RuntimeError):
    pass


@dataclass
class Synthese:
    duree_s: float
    mots: list[Mot]
    caracteres: int  # caractères facturés (en-tête character-cost)
    request_id: str | None


def lire_cle() -> str:
    try:
        import keyring

        cle = keyring.get_password("trendforge", "elevenlabs")
    except Exception:  # noqa: BLE001 — trousseau indisponible
        cle = None
    cle = (cle or os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not cle:
        raise CleElevenLabsAbsente("Aucune clé ElevenLabs : uv run keyring set trendforge elevenlabs")
    return cle


def voix_depuis_hint(engine_hint: str | None) -> str | None:
    """'elevenlabs:<voice_id>' → voice_id ; autre moteur → None."""
    if engine_hint and engine_hint.startswith("elevenlabs:"):
        return engine_hint.split(":", 1)[1]
    return None


def mots_depuis_alignement(alignement: dict) -> list[Mot]:
    """Regroupe l'horodatage caractère par caractère en mots (séparés par des espaces)."""
    mots: list[Mot] = []
    cur, debut, fin = "", 0.0, 0.0
    for c, d, f in zip(alignement["characters"], alignement["character_start_times_seconds"],
                       alignement["character_end_times_seconds"]):
        if c.isspace():
            if cur:
                mots.append(Mot(cur, debut, fin))
                cur = ""
            continue
        if not cur:
            debut = d
        cur += c
        fin = f
    if cur:
        mots.append(Mot(cur, debut, fin))
    return mots


def synthetiser(texte: str, sortie_wav: Path, voice_id: str, vitesse: float = 1.0,
                transport: httpx.BaseTransport | None = None) -> Synthese:
    """Écrit un WAV 44,1 kHz mono et renvoie la durée et les mots horodatés."""
    vitesse = round(min(VITESSE_MAX, max(VITESSE_MIN, vitesse)), 3)
    with httpx.Client(transport=transport, timeout=120) as c:
        r = c.post(f"{API}/text-to-speech/{voice_id}/with-timestamps",
                   headers={"xi-api-key": lire_cle()},
                   params={"output_format": "mp3_44100_128"},
                   json={"text": texte, "model_id": MODELE, "voice_settings": {"speed": vitesse}})
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", {})
            msg = detail.get("message") if isinstance(detail, dict) else str(detail)
        except ValueError:
            msg = r.text[:200]
        raise ErreurElevenLabs(f"ElevenLabs {r.status_code} : {msg}")
    d = r.json()
    mp3 = sortie_wav.with_suffix(".mp3")
    mp3.write_bytes(base64.b64decode(d["audio_base64"]))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "44100",
                    str(sortie_wav)], check=True)
    mp3.unlink()
    from trendforge.voix import duree_wav

    return Synthese(duree_s=duree_wav(sortie_wav), mots=mots_depuis_alignement(d["alignment"]),
                    caracteres=int(r.headers.get("character-cost") or len(texte)),
                    request_id=r.headers.get("request-id"))


def quota(transport: httpx.BaseTransport | None = None) -> tuple[int, int] | None:
    """(caractères utilisés, limite) du mois en cours, ou None si indisponible."""
    try:
        with httpx.Client(transport=transport, timeout=10) as c:
            r = c.get(f"{API}/user/subscription", headers={"xi-api-key": lire_cle()})
        if r.status_code != 200:
            return None
        d = r.json()
        return int(d.get("character_count", 0)), int(d.get("character_limit", 0))
    except (httpx.HTTPError, CleElevenLabsAbsente, ValueError):
        return None
