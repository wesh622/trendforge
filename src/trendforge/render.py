"""Montage et rendu avec FFmpeg piloté directement (section 7, étape 9).

Une seule commande FFmpeg : plans de fond découpés et animés (Ken Burns par panoramique),
sous-titres ASS incrustés, voix + musique mixées et normalisées à -14 LUFS.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Encodeur = Literal["libx264", "h264_qsv", "h264_vaapi"]

L, H, FPS = 1080, 1920, 30
DEVICE_VAAPI = "/dev/dri/renderD128"


@dataclass
class Plan:
    """Un extrait de vidéo de fond : fichier, point d'entrée, durée."""

    fichier: Path
    debut: float
    duree: float


@dataclass
class Rendu:
    plans: list[Plan]
    voix: Path
    ass: Path
    sortie: Path
    musique: Path | None = None
    musique_db: float = -22.0
    encodeur: Encodeur = "h264_vaapi"  # V0 : QSV indisponible ; libx264 en secours
    debit: str = "8M"
    preset_x264: str = "veryfast"
    extra: list[str] = field(default_factory=list)


def _filtre_plan(idx: int, duree: float) -> str:
    """Remplit 1080x1920 (crop « cover »), puis panoramique lent, sens alterné."""
    sens = "" if idx % 2 == 0 else "1-"
    return (
        f"[{idx}:v]scale={int(L * 1.15)}:{int(H * 1.15)}:force_original_aspect_ratio=increase,"
        f"crop={L}:{H}:x='(iw-{L})*({sens}t/{duree:.3f})':y='(ih-{H})/2',"
        f"fps={FPS},setsar=1,format=yuv420p,trim=duration={duree:.3f},setpts=PTS-STARTPTS[p{idx}]"
    )


def construire_commande(r: Rendu) -> list[str]:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if r.encodeur == "h264_vaapi":
        cmd += ["-vaapi_device", DEVICE_VAAPI]
    for p in r.plans:
        # 1 thread de décodage par extrait : pic mémoire divisé par 2 (V0 : 946 Mo au lieu de 1947 Mo
        # en VAAPI) pour ~10 s de rendu en plus sur 75 s de vidéo.
        cmd += ["-threads", "1", "-ss", f"{p.debut:.3f}", "-t", f"{p.duree + 0.5:.3f}", "-i", str(p.fichier)]
    i_voix = len(r.plans)
    cmd += ["-i", str(r.voix)]
    i_mus = None
    if r.musique:
        i_mus = i_voix + 1
        cmd += ["-stream_loop", "-1", "-i", str(r.musique)]

    graphe = [_filtre_plan(i, p.duree) for i, p in enumerate(r.plans)]
    entrees = "".join(f"[p{i}]" for i in range(len(r.plans)))
    ass = str(r.ass).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    sortie_v = f"{entrees}concat=n={len(r.plans)}:v=1:a=0,ass='{ass}'"
    if r.encodeur == "h264_vaapi":
        sortie_v += ",format=nv12,hwupload"
    elif r.encodeur == "h264_qsv":
        sortie_v += ",format=nv12"
    graphe.append(sortie_v + "[v]")

    if i_mus is not None:
        graphe.append(f"[{i_mus}:a]volume={r.musique_db}dB[m]")
        graphe.append(f"[{i_voix}:a][m]amix=inputs=2:duration=first:dropout_transition=0,volume=2[mx]")
        src_audio = "[mx]"
    else:
        src_audio = f"[{i_voix}:a]"
    graphe.append(f"{src_audio}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")

    cmd += ["-filter_complex", ";".join(graphe), "-map", "[v]", "-map", "[a]"]
    if r.encodeur == "libx264":
        cmd += ["-c:v", "libx264", "-preset", r.preset_x264, "-b:v", r.debit,
                "-maxrate", r.debit, "-bufsize", "16M", "-profile:v", "high"]
    elif r.encodeur == "h264_vaapi":
        # Le pilote i965 de ce PC n'accepte que le mode CQP (qualité constante), pas de débit cible.
        cmd += ["-c:v", "h264_vaapi", "-rc_mode", "CQP", "-qp", "22"]
    else:
        cmd += ["-c:v", r.encodeur, "-b:v", r.debit, "-maxrate", r.debit]
    cmd += ["-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", "-shortest", *r.extra, str(r.sortie)]
    return cmd


def decouper(fonds: list[tuple[Path, float]], duree_totale: float, coupe_s: float) -> list[Plan]:
    """Découpe la durée totale en plans de `coupe_s` s, en parcourant les fonds tour à tour."""
    plans: list[Plan] = []
    t, k = 0.0, 0
    curseurs = [0.0] * len(fonds)
    while t < duree_totale - 0.01:
        d = min(coupe_s, duree_totale - t)
        f, longueur = fonds[k % len(fonds)]
        debut = curseurs[k % len(fonds)]
        if debut + d > longueur:
            debut = 0.0
        plans.append(Plan(f, debut, d))
        curseurs[k % len(fonds)] = debut + d
        t += d
        k += 1
    return plans


def afficher(cmd: list[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)
