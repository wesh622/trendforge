"""Empreinte : absence de contenu de la source dans le rendu (section 7, contrôle 10).

Images
    1 image/s du rendu contre 2 images/s de la source, pHash 64 bits (imagehash) calculé
    sur des vignettes 64x64 en niveaux de gris extraites par ffmpeg (sous-processus).
    Échec si une distance de Hamming est <= 10.
    Pour attraper une source recadrée (paysage -> 1080x1920) ou posée sur un fond
    (bandes / flou), on hache aussi, quand les rapports d'aspect diffèrent :
      - le centre de chaque image de la source, recadré au format du rendu ;
      - le centre de chaque image du rendu, recadré au format de la source.
    Toutes les paires (variante rendu, variante source) sont comparées.
    Les images presque unies (écart type < 6 niveaux de gris : noir, fondus, aplats)
    sont ignorées, car leurs pHash se ressemblent tous.

Son
    Chromaprint via le muxer ffmpeg `chromaprint` (`-f chromaprint -fp_format raw`) :
    une suite d'entiers 32 bits, environ 8,08 par seconde (algorithme 1, pas de
    4096/3 échantillons à 11025 Hz). On fait glisser chaque position du rendu contre
    chaque position de la source (toutes les décalages), et on calcule sur une fenêtre de
    FENETRE_SON items consécutifs le taux de bits différents (BER).
    Deux sons sans rapport donnent un BER proche de 0,5 ; le même son, même mixé sous
    des sous-titres et de la musique, descend nettement plus bas.
    Seuil retenu : BER <= 0,35 sur 16 items (~2 s d'empreinte, soit un extrait d'environ
    4 s présent en entier dans le rendu, puisque chaque item résume ~2,6 s de son).
    Étalonnage : bench/temoin_positif.py (min. observé « propre » ~0,40 ; « truqué »
    nettement sous 0,30, voir le rapport du témoin positif).
    Les fenêtres pauvres de la source (silence, son tenu : moins de FENETRE_SON/2 valeurs
    distinctes) sont ignorées : leur empreinte est constante et collerait à n'importe quel
    autre silence.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import imagehash
import numpy as np
from PIL import Image

# images
FPS_RENDU = 1.0
FPS_SOURCE = 2.0
COTE_VIGNETTE = 64
SEUIL_HAMMING = 10
ECART_TYPE_MIN = 6.0
ECART_ASPECT = 0.10  # au-delà de 10 % d'écart de rapport d'aspect, on ajoute les recadrages

# son
PAS_CHROMAPRINT_S = 4096 / 3 / 11025  # ~0,1238 s entre deux items
FENETRE_SON = 16
SEUIL_BER = 0.35


def _ffmpeg(args: list[str]) -> bytes:
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *args],
        capture_output=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué : {p.stderr.decode(errors='replace')[-800:]}")
    return p.stdout


def _sonde(chemin: Path) -> dict:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(chemin)],
        capture_output=True,
        check=True,
    )
    flux = json.loads(p.stdout)["streams"]
    video = next((s for s in flux if s.get("codec_type") == "video"), None)
    audio = next((s for s in flux if s.get("codec_type") == "audio"), None)
    aspect = None
    if video:
        w, h = int(video["width"]), int(video["height"])
        sar = video.get("sample_aspect_ratio", "1:1")
        num, den = (int(x) for x in sar.split(":")) if sar not in ("0:1", "N/A") else (1, 1)
        aspect = w * num / den / h
    return {"aspect": aspect, "audio": audio is not None}


def _popcount(x: np.ndarray) -> np.ndarray:
    return np.bitwise_count(x)


# --------------------------------------------------------------------------- images


def hashes_images(
    chemin: str | Path, fps: float, aspects: list[float | None]
) -> tuple[np.ndarray, np.ndarray]:
    """pHash (uint64) des images échantillonnées à `fps`.

    Renvoie (hashes, valides), deux tableaux (n_images, len(aspects)) ; dans `aspects`,
    `None` = image entière, un nombre r = recadrage central au rapport largeur/hauteur r.
    `valides` est faux pour les vignettes trop unies (écart type < ECART_TYPE_MIN).
    """
    k = len(aspects)
    c = COTE_VIGNETTE
    branches = []
    for i, r in enumerate(aspects):
        crop = "" if r is None else f"crop='min(iw,ih*{r:.5f})':'min(ih,iw/{r:.5f})',"
        branches.append(f"[s{i}]{crop}scale={c}:{c}:flags=area[o{i}]")
    tete = f"[0:v]fps={fps},scale=-2:360:flags=area,format=gray"
    if k == 1:
        graphe = f"{tete}[s0];{branches[0]}"
        sortie = "[o0]"
    else:
        graphe = (
            f"{tete},split={k}" + "".join(f"[s{i}]" for i in range(k)) + ";" + ";".join(branches)
            + ";" + "".join(f"[o{i}]" for i in range(k)) + f"hstack=inputs={k}[out]"
        )
        sortie = "[out]"
    brut = _ffmpeg(
        ["-i", str(chemin), "-filter_complex", graphe, "-map", sortie, "-an",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    )
    images = np.frombuffer(brut, dtype=np.uint8).reshape(-1, c, c * k)
    h = np.zeros((len(images), k), dtype=np.uint64)
    valides = np.zeros((len(images), k), dtype=bool)
    for n, img in enumerate(images):
        for i in range(k):
            v = img[:, i * c : (i + 1) * c]
            if v.std() < ECART_TYPE_MIN:
                continue
            bits = imagehash.phash(Image.fromarray(v)).hash.flatten()
            h[n, i] = np.packbits(bits).view(">u8")[0]
            valides[n, i] = True
    return h, valides


@dataclass
class CorrespondanceImage:
    t_rendu: float
    t_source: float
    distance: int


@dataclass
class ResultatImages:
    ok: bool
    distance_min: int | None  # None si aucune image exploitable
    correspondances: list[CorrespondanceImage] = field(default_factory=list)
    n_images_rendu: int = 0
    n_images_source: int = 0


def comparer_images(rendu: str | Path, source: str | Path, seuil: int = SEUIL_HAMMING) -> ResultatImages:
    a_r, a_s = _sonde(Path(rendu))["aspect"], _sonde(Path(source))["aspect"]
    differents = a_r and a_s and abs(a_r / a_s - 1) > ECART_ASPECT
    hr, vr = hashes_images(rendu, FPS_RENDU, [None, a_s] if differents else [None])
    hs, vs = hashes_images(source, FPS_SOURCE, [None, a_r] if differents else [None])
    if not vr.any() or not vs.any():
        return ResultatImages(True, None, [], len(hr), len(hs))
    # distances (n_r, k_r, n_s, k_s) ; paires invalides -> 64
    d = _popcount(hr[:, :, None, None] ^ hs[None, None, :, :]).astype(np.int16)
    d[~(vr[:, :, None, None] & vs[None, None, :, :])] = 64
    d = d.min(axis=(1, 3))  # (n_r, n_s)
    corr = []
    for i in range(d.shape[0]):
        j = int(d[i].argmin())
        if d[i, j] <= seuil:
            corr.append(CorrespondanceImage(i / FPS_RENDU, j / FPS_SOURCE, int(d[i, j])))
    return ResultatImages(not corr, int(d.min()), corr, len(hr), len(hs))


# --------------------------------------------------------------------------- son


def empreinte_son(chemin: str | Path) -> np.ndarray:
    """Empreinte Chromaprint brute (uint32), ~8 items par seconde."""
    brut = _ffmpeg(
        ["-i", str(chemin), "-vn", "-ac", "1", "-ar", "11025",
         "-f", "chromaprint", "-fp_format", "raw", "-"]
    )
    return np.frombuffer(brut, dtype="<u4").astype(np.uint32)


@dataclass
class CorrespondanceSon:
    t_rendu: float  # début approximatif dans le rendu (s)
    t_source: float  # début approximatif dans la source (s)
    duree: float  # longueur de la zone sous le seuil (s d'empreinte)
    ber: float  # taux de bits différents minimal sur la zone


@dataclass
class ResultatSon:
    ok: bool
    ber_min: float | None  # None si une empreinte est vide ou trop pauvre
    correspondances: list[CorrespondanceSon] = field(default_factory=list)


def comparer_empreintes_son(
    fr: np.ndarray, fs: np.ndarray, seuil: float = SEUIL_BER, fenetre: int = FENETRE_SON
) -> ResultatSon:
    """Glissement de l'empreinte de la source contre celle du rendu, à tous les décalages."""
    if len(fr) < fenetre or len(fs) < fenetre:
        return ResultatSon(True, None, [])
    # fenêtres exploitables de la source (assez de valeurs distinctes)
    riche = np.array(
        [len(np.unique(fs[j : j + fenetre])) >= fenetre // 2 for j in range(len(fs) - fenetre + 1)]
    )
    if not riche.any():
        return ResultatSon(True, None, [])
    bits = _popcount(fr[:, None] ^ fs[None, :]).astype(np.int32)  # (n_r, n_s)
    noyau = np.ones(fenetre, dtype=np.int32)
    ber_min, corr = 1.0, []
    for dec in range(-(len(fs) - fenetre), len(fr) - fenetre + 1):  # dec = i_rendu - j_source
        diag = np.diagonal(bits, offset=-dec)  # éléments (j+dec, j)
        if len(diag) < fenetre:
            continue
        j0 = max(0, -dec)  # indice source du premier élément de la diagonale
        ber = np.convolve(diag, noyau, mode="valid") / (32 * fenetre)
        ber = np.where(riche[j0 : j0 + len(ber)], ber, 1.0)
        m = float(ber.min())
        ber_min = min(ber_min, m)
        if m <= seuil:
            sous = np.flatnonzero(ber <= seuil)
            # zones contiguës sous le seuil
            coupures = np.flatnonzero(np.diff(sous) > 1)
            for bloc in np.split(sous, coupures + 1):
                j = j0 + int(bloc[0])
                corr.append(
                    CorrespondanceSon(
                        t_rendu=round((j + dec) * PAS_CHROMAPRINT_S, 2),
                        t_source=round(j * PAS_CHROMAPRINT_S, 2),
                        duree=round((len(bloc) + fenetre - 1) * PAS_CHROMAPRINT_S, 2),
                        ber=round(float(ber[bloc].min()), 3),
                    )
                )
    corr.sort(key=lambda c: c.ber)
    return ResultatSon(not corr, round(ber_min, 3), corr[:20])


def comparer_son(rendu: str | Path, source: str | Path, seuil: float = SEUIL_BER) -> ResultatSon:
    if not _sonde(Path(rendu))["audio"] or not _sonde(Path(source))["audio"]:
        return ResultatSon(True, None, [])
    return comparer_empreintes_son(empreinte_son(rendu), empreinte_son(source), seuil)


# --------------------------------------------------------------------------- contrôle


@dataclass
class ResultatEmpreinte:
    images: ResultatImages
    son: ResultatSon

    @property
    def ok(self) -> bool:
        return self.images.ok and self.son.ok

    @property
    def raisons(self) -> list[str]:
        r = []
        if not self.images.ok:
            c = self.images.correspondances[0]
            r.append(
                f"{len(self.images.correspondances)} image(s) du rendu proches de la source "
                f"(ex. {c.t_rendu:.0f} s <-> {c.t_source:.1f} s, distance {c.distance})"
            )
        if not self.son.ok:
            c = self.son.correspondances[0]
            r.append(
                f"son de la source retrouvé (rendu ~{c.t_rendu:.1f} s <-> source ~{c.t_source:.1f} s, "
                f"BER {c.ber:.2f})"
            )
        return r


def controle_empreinte(
    rendu: str | Path,
    source: str | Path,
    seuil_hamming: int = SEUIL_HAMMING,
    seuil_ber: float = SEUIL_BER,
) -> ResultatEmpreinte:
    """Contrôle bloquant « absence de contenu de la source » : images (pHash) et son (Chromaprint)."""
    return ResultatEmpreinte(
        images=comparer_images(rendu, source, seuil_hamming),
        son=comparer_son(rendu, source, seuil_ber),
    )
