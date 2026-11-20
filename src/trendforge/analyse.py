"""Étapes d'analyse du module Recette (section 6), sans l'appel à Claude.

Profil Léger (section 4, exigence mémoire) : les étapes s'exécutent l'une après l'autre ; chaque
fonction charge son modèle, s'en sert puis le libère avant de rendre la main. Les bibliothèques
lourdes sont importées dans les fonctions, pour qu'une étape ne paie que ce qu'elle utilise.
"""

from __future__ import annotations

import gc
import re
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from trendforge.captions import Mot
from trendforge.voix import MODELES, horodater

DUREE_MIN_FIABLE = 15.0
DUREE_MAX_FIABLE = 600.0
TAUX_WHISPER = 16000


# --------------------------------------------------------------------------- erreurs


class ErreurAnalyse(Exception):
    """Erreur prévue, dont le message peut être montré tel quel à l'utilisateur."""


class VideoInaccessible(ErreurAnalyse):
    """Lien mort, vidéo privée ou supprimée : proposer l'import du .mp4 à la main."""


class TelechargementBloque(ErreurAnalyse):
    """yt-dlp bloqué par la plateforme après 1 nouvelle tentative."""


class ModeleManquant(ErreurAnalyse):
    """Le modèle demandé n'est pas dans modeles/ et son téléchargement n'est pas autorisé."""


def dico(obj) -> dict:
    return asdict(obj)


def _ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


# --------------------------------------------------------------------------- 1. téléchargement


@dataclass
class Telechargement:
    fichier: str
    url: str
    id: str
    duree_s: float | None
    vues: int | None
    likes: int | None
    date: str | None  # AAAA-MM-JJ
    legende: str
    hashtags: list[str]
    son: str | None
    auteur: str | None
    avertissement: str | None = None


_INACCESSIBLE = (
    "private", "privée", "unavailable", "not available", "does not exist", "removed", "deleted",
    "404", "410", "unsupported url", "no video", "account does not have any videos",
    "this post may not be comfortable", "status code 10204", "status code 10216",
    "name or service not known", "nodename nor servname", "getaddrinfo failed",
)
_BLOCAGE = (
    "unexpected response from webpage request", "failed to parse json", "403", "429",
    "impersonat", "captcha", "rate limit", "too many requests", "timed out", "unable to extract",
)


def _classer_erreur(msg: str) -> type[ErreurAnalyse]:
    m = msg.lower()
    if any(k in m for k in _BLOCAGE):
        return TelechargementBloque
    if any(k in m for k in _INACCESSIBLE):
        return VideoInaccessible
    return TelechargementBloque  # par défaut on retente une fois, puis message « bloqué »


def _hashtags(*textes: str | None) -> list[str]:
    vus: list[str] = []
    for t in textes:
        for h in re.findall(r"#(\w+)", t or ""):
            h = "#" + h.lower()
            if h not in vus:
                vus.append(h)
    return vus


def avertissement_duree(duree: float | None) -> str | None:
    if duree is None:
        return None
    if duree < DUREE_MIN_FIABLE or duree > DUREE_MAX_FIABLE:
        return f"durée {duree:.0f} s hors de 15 s - 10 min : recette peu fiable"
    return None


def _est_tiktok(url: str) -> bool:
    hote = (urlparse(url).hostname or "").lower()
    return hote == "tiktok.com" or hote.endswith(".tiktok.com")


def telecharger(url: str, dossier: Path, attente_s: float = 3.0,
                delai_reseau_s: float = 10.0, user_agent: str | None = None) -> Telechargement:
    """Télécharge la vidéo en .mp4 avec yt-dlp (bibliothèque) et renvoie ses métadonnées.

    Lève VideoInaccessible (sans nouvelle tentative) ou TelechargementBloque (après 1 nouvelle
    tentative). Les messages ne contiennent aucune trace technique.
    """
    import yt_dlp

    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True, "no_warnings": True, "noprogress": True, "overwrites": True,
        "outtmpl": str(dossier / "video.%(ext)s"),
        "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        "socket_timeout": delai_reseau_s, "retries": 1, "extractor_retries": 0,
        "noplaylist": True,
    }
    if _est_tiktok(url):
        # TikTok refuse les clients sans l'empreinte TLS d'un navigateur : la page renvoie un
        # challenge WAF, puis le CDN répond 403. curl_cffi (extra yt-dlp[curl-cffi]) fournit
        # cette empreinte. L'option couvre aussi le téléchargement du fichier, pas seulement
        # la page : sans elle, l'extraction passe mais le .mp4 reste bloqué.
        from yt_dlp.networking.impersonate import ImpersonateTarget

        opts["impersonate"] = ImpersonateTarget.from_str("chrome")
    if user_agent:  # certains hébergeurs (Wikimedia) refusent l'agent navigateur par défaut
        opts["http_headers"] = {"User-Agent": user_agent}
    derniere = ""
    for tentative in range(2):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            break
        except yt_dlp.utils.YoutubeDLError as e:
            derniere = str(e)
            if "impersonate target" in derniere.lower():
                raise TelechargementBloque(
                    "TikTok exige une empreinte de navigateur, mais curl-cffi est absent ou "
                    "incompatible. Lance « uv sync » puis réessaie, ou importe le fichier .mp4 "
                    "à la main.") from None
            classe = _classer_erreur(derniere)
            if classe is VideoInaccessible:
                raise VideoInaccessible(
                    "Vidéo inaccessible (lien mort, privée ou supprimée). "
                    "Tu peux importer le fichier .mp4 à la main.") from None
            if tentative == 0:
                time.sleep(attente_s)
    else:
        raise TelechargementBloque(
            "Téléchargement bloqué par la plateforme. Mets à jour yt-dlp ou importe le fichier "
            f".mp4 à la main. (détail : {derniere.removeprefix('ERROR: ')[:160]})")

    fichier = dossier / "video.mp4"
    if not fichier.exists():  # remux impossible : on garde ce que yt-dlp a produit
        candidats = sorted(dossier.glob("video.*"))
        if not candidats:
            raise TelechargementBloque("Téléchargement interrompu : aucun fichier reçu.")
        fichier = candidats[0]
    d = info.get("upload_date")
    duree = info.get("duration") or duree_video(fichier)
    son = info.get("track") or info.get("artist")
    if info.get("track") and info.get("artist"):
        son = f"{info['artist']} - {info['track']}"
    legende = info.get("description") or info.get("title") or ""
    return Telechargement(
        fichier=str(fichier), url=url, id=str(info.get("id")), duree_s=duree,
        vues=info.get("view_count"), likes=info.get("like_count"),
        date=f"{d[:4]}-{d[4:6]}-{d[6:]}" if d else None, legende=legende,
        hashtags=_hashtags(legende, " ".join("#" + t for t in info.get("tags") or [])),
        son=son, auteur=info.get("uploader") or info.get("creator"),
        avertissement=avertissement_duree(duree),
    )


def importer(fichier: Path, dossier: Path) -> Telechargement:
    """Import manuel d'un fichier vidéo (repli quand le lien est mort ou bloqué)."""
    fichier, dossier = Path(fichier), Path(dossier)
    if not fichier.is_file():
        raise VideoInaccessible(f"Fichier introuvable : {fichier.name}")
    dossier.mkdir(parents=True, exist_ok=True)
    sortie = dossier / "video.mp4"
    try:
        _ff("-i", str(fichier), "-map", "0:v:0", "-map", "0:a?", "-c", "copy", str(sortie))
    except subprocess.CalledProcessError:
        raise VideoInaccessible(f"Fichier illisible : {fichier.name}") from None
    duree = duree_video(sortie)
    return Telechargement(str(sortie), fichier.as_uri(), fichier.stem, duree, None, None, None,
                          "", [], None, None, avertissement_duree(duree))


def duree_video(fichier: Path) -> float:
    sortie = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(fichier)], capture_output=True, text=True, check=True).stdout.strip()
    return float(sortie)


# --------------------------------------------------------------------------- 2. transcription


@dataclass
class Transcription:
    mots: list[dict]  # {"texte", "debut", "fin"}
    langue: str | None
    proba_langue: float | None
    modele: str
    parle: bool
    format: str  # "narration" ou "texte_ecran"
    passages_parles: list[tuple[float, float]] = field(default_factory=list)
    duree_parlee_s: float = 0.0
    message: str | None = None


def extraire_audio(video: Path, wav: Path, taux: int = TAUX_WHISPER) -> Path:
    _ff("-i", str(video), "-vn", "-ac", "1", "-ar", str(taux), "-c:a", "pcm_s16le", str(wav))
    return wav


def detecter_parole(wav: Path) -> list[tuple[float, float]]:
    """Passages parlés (VAD Silero ONNX livré avec faster-whisper), en secondes."""
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio = decode_audio(str(wav), sampling_rate=TAUX_WHISPER)
    ts = get_speech_timestamps(audio, VadOptions(min_speech_duration_ms=250,
                                                 min_silence_duration_ms=500))
    del audio
    return [(round(t["start"] / TAUX_WHISPER, 2), round(t["end"] / TAUX_WHISPER, 2)) for t in ts]


def modele_en_cache(nom: str) -> bool:
    return any((MODELES / "whisper").glob(f"models--Systran--faster-whisper-{nom}/snapshots/*/model.bin"))


def _horodater_multilingue(wav: Path, modele: str) -> tuple[list[Mot], str, float]:
    from faster_whisper import WhisperModel

    m = WhisperModel(modele, device="cpu", compute_type="int8", cpu_threads=4,
                     download_root=str(MODELES / "whisper"))
    try:
        segments, info = m.transcribe(str(wav), language=None, word_timestamps=True, beam_size=1,
                                      vad_filter=True)
        mots = [Mot(w.word.strip(), w.start, w.end) for s in segments for w in (s.words or [])]
        return [x for x in mots if x.texte], info.language, info.language_probability
    finally:
        del m
        gc.collect()


def _dans_parole(mot: Mot, passages: list[tuple[float, float]], marge: float = 0.3) -> bool:
    milieu = (mot.debut + mot.fin) / 2
    return any(a - marge <= milieu <= b + marge for a, b in passages)


def transcrire(video: Path, dossier: Path, langue: str | None = "en",
               modele_multilingue: str = "small", telecharger_modele: bool = False) -> Transcription:
    """Transcription mot par mot avec horodatage.

    - langue="en" : réutilise trendforge.voix.horodater (small.en, déjà en cache).
    - langue=None (langue inconnue) : modèle multilingue `small` avec détection de la langue.
      S'il n'est pas dans modeles/whisper et que telecharger_modele est faux, lève ModeleManquant.
    Une VAD passe d'abord : sans passage parlé, Whisper n'est pas chargé et la recette passe en
    format texte_ecran (section 6, cas « vidéo sans voix »).
    """
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    wav = extraire_audio(Path(video), dossier / "audio16k.wav")
    try:
        passages = detecter_parole(wav)
        duree_parlee = round(sum(b - a for a, b in passages), 2)
        if duree_parlee < 1.0:
            return Transcription([], None, None, "aucun (VAD)", False, "texte_ecran", passages,
                                 duree_parlee, "aucun passage parlé : format texte_ecran")
        if langue == "en":
            mots, lang, proba, nom = horodater(wav), "en", None, "small.en"
        else:
            if not telecharger_modele and not modele_en_cache(modele_multilingue):
                raise ModeleManquant(
                    f"modèle faster-whisper « {modele_multilingue} » absent de modeles/whisper "
                    "(détection de langue impossible sans lui)")
            mots, lang, proba = _horodater_multilingue(wav, modele_multilingue)
            nom = modele_multilingue
        mots = [m for m in mots if _dans_parole(m, passages)]  # retire les hallucinations sur musique
        parle = len(mots) >= 3
        return Transcription(
            [{"texte": m.texte, "debut": round(m.debut, 2), "fin": round(m.fin, 2)} for m in mots],
            lang, round(proba, 3) if proba is not None else None, nom, parle,
            "narration" if parle else "texte_ecran", passages, duree_parlee,
            None if parle else "aucun passage parlé : format texte_ecran")
    finally:
        wav.unlink(missing_ok=True)


# --------------------------------------------------------------------------- 3. plans


@dataclass
class Plans:
    nombre: int
    duree_moyenne_s: float
    duree_mediane_s: float
    coupes_par_minute: float
    rythme: str  # "rapide" < 2 s, "moyen" < 5 s, sinon "lent"
    debuts_s: list[float]
    fins_s: list[float]


def plans(video: Path, seuil: float = 27.0) -> Plans:
    from scenedetect import ContentDetector, detect

    scenes = detect(str(video), ContentDetector(threshold=seuil))
    if scenes:
        debuts = [round(a.seconds, 2) for a, _ in scenes]
        fins = [round(b.seconds, 2) for _, b in scenes]
    else:  # aucune coupe : un seul plan
        debuts, fins = [0.0], [round(duree_video(Path(video)), 2)]
    durees = [f - d for d, f in zip(debuts, fins)]
    total = fins[-1] - debuts[0]
    moy = statistics.mean(durees)
    del scenes
    gc.collect()
    return Plans(
        nombre=len(durees), duree_moyenne_s=round(moy, 2),
        duree_mediane_s=round(statistics.median(durees), 2),
        coupes_par_minute=round((len(durees) - 1) / total * 60, 1) if total > 0 else 0.0,
        rythme="rapide" if moy < 2 else "moyen" if moy < 5 else "lent",
        debuts_s=debuts, fins_s=fins,
    )


# --------------------------------------------------------------------------- 4. texte à l'écran


@dataclass
class TexteEcran:
    t: float
    texte: str
    boite: tuple[float, float, float, float]  # x, y, largeur, hauteur (fractions de l'image)
    hauteur_rel: float  # hauteur du texte / hauteur de l'image (indice de taille de police)
    couleur: str  # #RRGGBB
    score: float


@dataclass
class Ocr:
    images_analysees: int
    images_avec_texte: int
    mots_par_image_moyen: float
    mots_par_image_max: int
    position_dominante: str | None  # haut, centre, bas
    couleur_dominante: str | None
    hauteur_texte_mediane: float | None
    textes: list[dict]
    texte_reconstruit: str  # texte lu, sans répétitions consécutives (script en texte_ecran)


def instants_ocr(debuts_plans: list[float], duree: float, pas_s: float = 2.0,
                 ecart_min_s: float = 0.5) -> list[float]:
    """Une image par changement de plan (un peu après la coupe) et une image toutes les 2 s."""
    candidats = sorted({round(min(d + 0.2, max(duree - 0.05, 0)), 2) for d in debuts_plans}
                       | {round(t * pas_s, 2) for t in range(int(duree // pas_s) + 1)})
    instants: list[float] = []
    for t in candidats:
        if t < duree and (not instants or t - instants[-1] >= ecart_min_s):
            instants.append(t)
    return instants


def _couleur_texte(img, boite) -> str:
    import cv2
    import numpy as np

    xs = [int(p[0]) for p in boite]
    ys = [int(p[1]) for p in boite]
    roi = img[max(min(ys), 0):max(ys), max(min(xs), 0):max(xs)]
    if roi.size == 0:
        return "#000000"
    gris = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, masque = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    clair = masque > 0
    texte = clair if clair.mean() < 0.5 else ~clair  # le texte est la classe minoritaire
    b, g, r = (np.median(roi[..., i][texte]) if texte.any() else 0 for i in range(3))
    return f"#{int(r):02X}{int(g):02X}{int(b):02X}"


def _lire_images(video: Path, instants: list[float], largeur_max: int):
    """Lit la vidéo d'un bout à l'autre et rend (t, image) aux instants demandés."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    cibles = [round(t * fps) for t in instants]
    i, k = 0, 0
    try:
        while k < len(cibles):
            if not cap.grab():
                break
            if i >= cibles[k]:
                ok, img = cap.retrieve()
                if ok:
                    h, w = img.shape[:2]
                    if w > largeur_max:
                        img = cv2.resize(img, (largeur_max, round(h * largeur_max / w)),
                                         interpolation=cv2.INTER_AREA)
                    yield instants[k], img
                k += 1
            i += 1
    finally:
        cap.release()


def ocr(video: Path, debuts_plans: list[float], duree: float | None = None, pas_s: float = 2.0,
        largeur_max: int = 720, score_min: float = 0.6) -> Ocr:
    from rapidocr_onnxruntime import RapidOCR

    video = Path(video)
    duree = duree or duree_video(video)
    instants = instants_ocr(debuts_plans, duree, pas_s)
    moteur = RapidOCR()
    textes: list[TexteEcran] = []
    mots_image: list[int] = []
    try:
        for t, img in _lire_images(video, instants, largeur_max):
            h, w = img.shape[:2]
            res, _ = moteur(img)
            n = 0
            for boite, texte, score in res or []:
                if float(score) < score_min or not texte.strip():
                    continue
                xs = [p[0] for p in boite]
                ys = [p[1] for p in boite]
                textes.append(TexteEcran(
                    t, texte.strip(),
                    (round(min(xs) / w, 3), round(min(ys) / h, 3),
                     round((max(xs) - min(xs)) / w, 3), round((max(ys) - min(ys)) / h, 3)),
                    round((max(ys) - min(ys)) / h, 3), _couleur_texte(img, boite),
                    round(float(score), 3)))
                n += len(texte.split())
            mots_image.append(n)
    finally:
        del moteur
        gc.collect()

    avec = [n for n in mots_image if n]

    def zone(tx: TexteEcran) -> str:
        cy = tx.boite[1] + tx.boite[3] / 2
        return "haut" if cy < 1 / 3 else "centre" if cy < 2 / 3 else "bas"

    def mode(valeurs: list[str]) -> str | None:
        return max(set(valeurs), key=valeurs.count) if valeurs else None

    lignes: list[str] = []
    vues: set[str] = set()
    for tx in textes:  # un texte qui reste affiché sur plusieurs images n'est gardé qu'une fois
        cle = re.sub(r"\W+", "", tx.texte.lower())
        if cle and cle not in vues:
            vues.add(cle)
            lignes.append(tx.texte)
    return Ocr(
        images_analysees=len(mots_image), images_avec_texte=len(avec),
        mots_par_image_moyen=round(statistics.mean(avec), 1) if avec else 0.0,
        mots_par_image_max=max(avec, default=0),
        position_dominante=mode([zone(tx) for tx in textes]),
        couleur_dominante=mode([tx.couleur for tx in textes]),
        hauteur_texte_mediane=round(statistics.median(tx.hauteur_rel for tx in textes), 3)
        if textes else None,
        textes=[dico(tx) for tx in textes], texte_reconstruit=" ".join(lignes),
    )


# --------------------------------------------------------------------------- 5. audio


@dataclass
class AnalyseAudio:
    tempo_bpm: float | None
    volume_global_db: float  # dBFS médian (RMS)
    volume_parole_db: float | None  # passages avec voix (voix + musique)
    volume_sans_voix_db: float | None  # passages sans voix (musique seule ou silence)
    musique_db: float | None  # estimation du niveau de la musique, en dBFS
    musique_sous_voix_db: float | None  # écart musique - passages parlés (négatif = sous la voix)
    silence: bool
    pics_transitoires: int  # indice de bruitages (whoosh, ding...)
    note: str | None = None


def intervalles_parole(mots: list[dict], ecart_max: float = 0.6) -> list[tuple[float, float]]:
    """Fusionne les horodatages des mots en passages parlés."""
    passages: list[list[float]] = []
    for m in sorted(mots, key=lambda x: x["debut"]):
        if passages and m["debut"] - passages[-1][1] <= ecart_max:
            passages[-1][1] = max(passages[-1][1], m["fin"])
        else:
            passages.append([m["debut"], m["fin"]])
    return [(a, b) for a, b in passages]


def audio(video: Path, dossier: Path, mots: list[dict], taux: int = 22050) -> AnalyseAudio:
    import librosa
    import numpy as np

    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    wav = extraire_audio(Path(video), dossier / "audio22k.wav", taux)
    try:
        y, sr = librosa.load(str(wav), sr=taux, mono=True)
    finally:
        wav.unlink(missing_ok=True)
    saut = 512
    rms = librosa.feature.rms(y=y, hop_length=saut)[0]
    db = 20 * np.log10(np.maximum(rms, 1e-5))
    t = librosa.frames_to_time(np.arange(len(db)), sr=sr, hop_length=saut)
    parole = np.zeros(len(db), dtype=bool)
    for a, b in intervalles_parole(mots):
        parole |= (t >= a) & (t <= b)
    silence = bool(np.percentile(db, 95) < -60)

    tempo = None
    if not silence:
        bpm, _ = librosa.beat.beat_track(y=y, sr=sr, hop_length=saut)
        tempo = round(float(np.atleast_1d(bpm)[0]), 1) or None
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=saut)
    pics = librosa.util.peak_pick(env, pre_max=10, post_max=10, pre_avg=20, post_avg=20,
                                  delta=float(env.mean() + 3 * env.std()), wait=20)
    del y, env

    def med(masque) -> float | None:
        return round(float(np.median(db[masque])), 1) if masque.sum() > sr / saut else None

    v_parole, v_sans = med(parole), med(~parole)
    note = None
    if v_parole is None:
        musique = v_sans  # pas de voix : tout le son est de la musique (ou du silence)
        note = "aucune voix : niveau de musique = niveau global"
    elif v_sans is None:
        # voix continue : la musique est estimée par les creux entre les mots (10e centile)
        musique = round(float(np.percentile(db[parole], 10)), 1)
        note = "voix continue : musique estimée sur les creux entre les mots"
    else:
        musique = v_sans
    gc.collect()
    return AnalyseAudio(
        tempo_bpm=tempo, volume_global_db=round(float(np.median(db)), 1),
        volume_parole_db=v_parole, volume_sans_voix_db=v_sans,
        musique_db=None if silence else musique,
        musique_sous_voix_db=round(musique - v_parole, 1)
        if (musique is not None and v_parole is not None and not silence) else None,
        silence=silence, pics_transitoires=int(len(pics)), note=note,
    )


# --------------------------------------------------------------------------- 6. images clés


def instants_images_cles(debuts: list[float], fins: list[float], duree: float,
                         n_min: int = 6, n_max: int = 10) -> list[float]:
    """Milieu des plans si leur nombre tombe dans 6-10, sinon répartition régulière."""
    milieux = [round((d + f) / 2, 2) for d, f in zip(debuts, fins)]
    if n_min <= len(milieux) <= n_max:
        return milieux
    if len(milieux) > n_max:  # trop de plans : n_max plans répartis sur toute la vidéo
        pas = (len(milieux) - 1) / (n_max - 1)
        return [milieux[round(i * pas)] for i in range(n_max)]
    n = n_min  # trop peu de plans : images régulières
    return [round(duree * (i + 0.5) / n, 2) for i in range(n)]


def images_cles(video: Path, dossier: Path, debuts: list[float], fins: list[float],
                duree: float | None = None, hauteur: int = 768) -> list[str]:
    """Extrait 6 à 10 images JPEG (pour l'appel à Claude de l'étape 6)."""
    video, dossier = Path(video), Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    for ancien in dossier.glob("cle_*.jpg"):
        ancien.unlink()
    duree = duree or duree_video(video)
    sorties = []
    for i, t in enumerate(instants_images_cles(debuts, fins, duree)):
        sortie = dossier / f"cle_{i:02d}_{t:06.2f}s.jpg"
        _ff("-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
            "-vf", f"scale=-2:{hauteur}", "-q:v", "3", str(sortie))
        if sortie.exists():
            sorties.append(str(sortie))
    return sorties
