"""Tests des étapes d'analyse (section 6) sur des vidéos synthétiques générées par ffmpeg (lavfi)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from trendforge import analyse as a

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")

POLICE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def video_plans(tmp_path_factory) -> Path:
    """3 plans de 2 s (rouge, vert, bleu), texte blanc connu au centre, bip 440 Hz."""
    d = tmp_path_factory.mktemp("plans")
    sortie = d / "plans.mp4"
    police = f":fontfile={POLICE}" if Path(POLICE).exists() else ""
    texte = (f"drawtext=text='SECRET FACT':fontsize=80:fontcolor=white{police}"
             ":x=(w-text_w)/2:y=(h-text_h)/2")
    filtres = ";".join(
        f"color=c={c}:s=720x1280:d=2:r=30,{texte}[v{i}]" for i, c in enumerate(["red", "green", "blue"])
    ) + ";[v0][v1][v2]concat=n=3:v=1:a=0[v]"
    ff("-filter_complex", filtres, "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
       "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
       "-shortest", str(sortie))
    return sortie


def test_plans_detecte_les_coupes(video_plans):
    p = a.plans(video_plans)
    assert p.nombre == 3
    assert p.debuts_s == pytest.approx([0, 2, 4], abs=0.1)
    assert p.duree_moyenne_s == pytest.approx(2.0, abs=0.1)
    assert p.coupes_par_minute == pytest.approx(20, abs=1)  # 2 coupes en 6 s
    assert p.rythme == "moyen"


def test_ocr_lit_le_texte_connu(video_plans):
    o = a.ocr(video_plans, [0.0, 2.0, 4.0], 6.0)
    assert o.images_analysees == 3  # coupes à 0,2 / 2,2 / 4,2 s, et images toutes les 2 s fusionnées
    assert o.images_avec_texte == 3
    lus = {t["texte"].replace(" ", "").upper() for t in o.textes}
    assert lus == {"SECRETFACT"}
    assert o.mots_par_image_max == 2
    assert o.position_dominante == "centre"
    r, g, b = (int(o.couleur_dominante[i:i + 2], 16) for i in (1, 3, 5))
    assert min(r, g, b) > 180  # texte blanc


def test_instants_ocr_coupes_et_pas_de_2s():
    assert a.instants_ocr([0.0, 3.0], 7.0) == [0.0, 2.0, 3.2, 4.0, 6.0]


def test_images_cles(video_plans, tmp_path):
    images = a.images_cles(video_plans, tmp_path, [0.0, 2.0, 4.0], [2.0, 4.0, 6.0], 6.0)
    assert len(images) == 6  # trop peu de plans : 6 images régulières
    assert all(Path(i).suffix == ".jpg" and Path(i).stat().st_size > 0 for i in images)


def test_instants_images_cles_bornes():
    assert len(a.instants_images_cles([float(i) for i in range(30)],
                                      [float(i + 1) for i in range(30)], 30.0)) == 10
    assert a.instants_images_cles([0, 1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6, 7], 7.0) == \
        [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5]


def test_transcrire_sans_voix_passe_en_texte_ecran(video_plans, tmp_path):
    t = a.transcrire(video_plans, tmp_path, langue=None)  # bip seul : Whisper n'est pas chargé
    assert not t.parle and t.mots == [] and t.format == "texte_ecran"
    assert "aucun passage parlé" in t.message
    assert not (tmp_path / "audio16k.wav").exists()


def test_audio_compare_voix_et_musique(video_plans, tmp_path):
    r = a.audio(video_plans, tmp_path, [{"texte": "x", "debut": 1.0, "fin": 3.0}])
    assert not r.silence
    assert r.volume_parole_db is not None and r.volume_sans_voix_db is not None
    assert r.musique_sous_voix_db == pytest.approx(0, abs=1.5)  # même bip partout


def test_intervalles_parole_fusionne():
    mots = [{"debut": 0.0, "fin": 0.4}, {"debut": 0.5, "fin": 0.9}, {"debut": 3.0, "fin": 3.5}]
    assert a.intervalles_parole(mots) == [(0.0, 0.9), (3.0, 3.5)]


def test_hashtags_et_avertissement_duree():
    assert a._hashtags("Wow #StoryTime #facts", "#facts #fyp") == ["#storytime", "#facts", "#fyp"]
    assert a.avertissement_duree(10) and a.avertissement_duree(700)
    assert a.avertissement_duree(75) is None


@pytest.mark.parametrize("msg,classe", [
    ("ERROR: [TikTok] 1: Video unavailable", a.VideoInaccessible),
    ("ERROR: [tiktok:user] x: This user's account is private", a.VideoInaccessible),
    ("ERROR: [TikTok] 1: Unexpected response from webpage request", a.TelechargementBloque),
    ("ERROR: x: HTTP Error 429: Too Many Requests", a.TelechargementBloque),
])
def test_classement_des_erreurs(msg, classe):
    assert a._classer_erreur(msg) is classe


@pytest.mark.parametrize("url, attendu", [
    ("https://www.tiktok.com/@x/video/1", True),
    ("https://vm.tiktok.com/abc/", True),
    ("https://tiktok.com/@x/video/1", True),
    ("https://www.tiktok.com.evil.example/video", False),
    ("https://exemple.invalid/video", False),
    ("/home/x/video.mp4", False),
])
def test_est_tiktok(url, attendu):
    assert a._est_tiktok(url) is attendu


def test_telecharger_tiktok_impose_une_empreinte_de_navigateur(tmp_path, monkeypatch):
    import yt_dlp
    from yt_dlp.networking.impersonate import ImpersonateTarget

    vus = {}

    class FauxYDL:
        def __init__(self, opts):
            vus.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            (tmp_path / "video.mp4").write_bytes(b"x")
            return {"id": "1", "duration": 30, "upload_date": "20260101", "description": "x"}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FauxYDL)
    r = a.telecharger("https://www.tiktok.com/@x/video/1", tmp_path, attente_s=0)
    assert isinstance(vus["impersonate"], ImpersonateTarget)
    assert str(vus["impersonate"]).startswith("chrome")
    assert r.duree_s == 30


def test_telecharger_hors_tiktok_sans_empreinte(tmp_path, monkeypatch):
    import yt_dlp

    vus = {}

    class FauxYDL:
        def __init__(self, opts):
            vus.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download=True):
            (tmp_path / "video.mp4").write_bytes(b"x")
            return {"id": "1", "duration": 30, "description": "x"}

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FauxYDL)
    a.telecharger("https://exemple.invalid/video", tmp_path, attente_s=0)
    assert "impersonate" not in vus


def test_telecharger_sans_curl_cffi_donne_un_message_clair(tmp_path, monkeypatch):
    import yt_dlp

    class FauxYDL:
        def __init__(self, opts):
            raise yt_dlp.utils.YoutubeDLError(
                'Impersonate target "chrome" is not available. You may be missing dependencies')

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FauxYDL)
    with pytest.raises(a.TelechargementBloque, match="curl-cffi"):
        a.telecharger("https://www.tiktok.com/@x/video/1", tmp_path, attente_s=0)


def test_telecharger_lien_mort(tmp_path):
    with pytest.raises(a.VideoInaccessible, match="inaccessible"):
        a.telecharger("https://exemple.invalid/pas-une-video", tmp_path, attente_s=0,
                      delai_reseau_s=3)


def test_importer_fichier_local(video_plans, tmp_path):
    with pytest.raises(a.VideoInaccessible):
        a.importer(tmp_path / "absent.mp4", tmp_path)
    r = a.importer(video_plans, tmp_path / "import")
    assert Path(r.fichier).suffix == ".mp4" and r.duree_s == pytest.approx(6, abs=0.2)
    assert r.avertissement  # 6 s < 15 s : recette « peu fiable »
