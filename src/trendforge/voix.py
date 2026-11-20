"""Voix locale (Kokoro via ONNX) et horodatage des mots (faster-whisper) — section 7, étape 4.

Profil Léger : un seul modèle chargé à la fois ; chaque fonction libère son modèle en sortant.
"""

from __future__ import annotations

import gc
import re
from pathlib import Path

import numpy as np
import soundfile as sf

from trendforge.captions import Mot

RACINE = Path(__file__).resolve().parents[2]
MODELES = RACINE / "modeles"
KOKORO_ONNX = MODELES / "kokoro-v1.0.onnx"  # fp32 : 3x plus rapide que int8 sur ce CPU (V0)
KOKORO_VOIX = MODELES / "voices-v1.0.bin"
TAUX = 24000
# Mesuré en V0 : 184 mots en 52,6 s à vitesse 1,05 (af_heart), soit ~200 mots/min à vitesse 1,0.
DEBIT_KOKORO_1X = 200.0


def vitesse_pour_debit(wpm: float, ajustement: float = 1.0) -> float:
    """Vitesse Kokoro qui donne le débit voulu par la recette (bornée à 0,8-1,3)."""
    return round(min(1.3, max(0.8, wpm / DEBIT_KOKORO_1X * ajustement)), 3)


def _phrases(texte: str) -> list[str]:
    morceaux = re.split(r"(?<=[.!?])\s+", texte.strip())
    return [m for m in morceaux if m]


def synthetiser(texte: str, sortie: Path, voix: str = "af_heart", vitesse: float = 1.0,
                pause_s: float = 0.12) -> float:
    """Écrit un WAV 24 kHz mono et renvoie sa durée en secondes."""
    from kokoro_onnx import Kokoro

    k = Kokoro(str(KOKORO_ONNX), str(KOKORO_VOIX))
    try:
        blocs = []
        silence = np.zeros(int(TAUX * pause_s), dtype=np.float32)
        for ph in _phrases(texte):
            audio, taux = k.create(ph, voice=voix, speed=vitesse, lang="en-us")
            assert taux == TAUX, taux
            blocs += [audio.astype(np.float32), silence]
        signal = np.concatenate(blocs) if blocs else silence
        sf.write(sortie, signal, TAUX)
        return len(signal) / TAUX
    finally:
        del k
        gc.collect()


def horodater(wav: Path, texte_attendu: str | None = None, modele: str = "small.en") -> list[Mot]:
    """Horodatage mot par mot. Le texte attendu sert d'amorce pour fiabiliser la reconnaissance."""
    from faster_whisper import WhisperModel

    m = WhisperModel(modele, device="cpu", compute_type="int8", cpu_threads=4,
                     download_root=str(MODELES / "whisper"))
    try:
        segments, _ = m.transcribe(str(wav), language="en", word_timestamps=True, beam_size=1,
                                   vad_filter=False,
                                   initial_prompt=texte_attendu[:400] if texte_attendu else None)
        mots = [Mot(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or [])]
        return [m_ for m_ in mots if m_.texte]
    finally:
        del m
        gc.collect()


def duree_wav(wav: Path) -> float:
    info = sf.info(str(wav))
    return info.frames / info.samplerate
