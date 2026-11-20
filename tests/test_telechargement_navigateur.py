"""Repli « bouton Télécharger de TikTok » piloté par Claude Code : sans réseau ni vrai Claude."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from trendforge import telechargement_navigateur as tn


def test_prompt_interdit_les_contournements():
    p = tn.prompt_telechargement("https://www.tiktok.com/@x/video/1")
    assert "https://www.tiktok.com/@x/video/1" in p
    for interdit in ("third-party", "developer tools", "never type a password", "download_disabled"):
        assert interdit in p


def test_attendre_fichier_attend_la_fin_du_telechargement(tmp_path):
    avant, depuis = tn._fichiers(tmp_path), time.time()

    def chrome():
        partiel = tmp_path / "video.mp4.crdownload"
        partiel.write_bytes(b"x" * 10)
        time.sleep(1.5)
        partiel.rename(tmp_path / "video.mp4")
    threading.Thread(target=chrome).start()
    f = tn._attendre_fichier(tmp_path, avant, depuis, 10, lambda _: None)
    assert f.name == "video.mp4" and f.stat().st_size == 10


def test_attendre_fichier_ignore_les_anciens(tmp_path):
    vieux = tmp_path / "ancien.mp4"
    vieux.write_bytes(b"y")
    avant = tn._fichiers(tmp_path)
    with pytest.raises(tn.TelechargementImpossible):
        tn._attendre_fichier(tmp_path, avant, time.time(), 1.5, lambda _: None)


def test_telechargement_desactive_par_le_createur(tmp_path, monkeypatch):
    monkeypatch.setattr(tn, "dossier_telechargements", lambda: tmp_path)
    monkeypatch.setattr(tn.pa, "executer", lambda *a, **k: {"sortie": {"status": "download_disabled", "details": "no"}})
    with pytest.raises(tn.TelechargementImpossible, match="désactivé"):
        tn.telecharger_via_navigateur("https://www.tiktok.com/@x/video/1", tmp_path / "c" / "v.mp4", lambda _: None)


def test_telechargement_reussi_deplace_le_fichier(tmp_path, monkeypatch):
    dl = tmp_path / "Downloads"
    dl.mkdir()
    monkeypatch.setattr(tn, "dossier_telechargements", lambda: dl)

    def faux_executer(*a, **k):
        (dl / "tiktok_123.mp4").write_bytes(b"z" * 100)
        return {"sortie": {"status": "download_started", "details": "ok"}}
    monkeypatch.setattr(tn.pa, "executer", faux_executer)
    cible = tmp_path / "cache" / "navigateur.mp4"
    assert tn.telecharger_via_navigateur("https://www.tiktok.com/@x/video/1", cible, lambda _: None,
                                         delai_fichier_s=10) == cible
    assert cible.read_bytes() == b"z" * 100 and not (dl / "tiktok_123.mp4").exists()


def test_synthese_passe_par_le_navigateur_si_ytdlp_bloque(tmp_path, monkeypatch):
    from trendforge import analyse, synthese

    monkeypatch.setattr(synthese, "CACHE", tmp_path)

    def bloque(*a, **k):
        raise analyse.TelechargementBloque("bloqué")
    monkeypatch.setattr(analyse, "telecharger", bloque)
    appels = []

    def faux_nav(url, cible, progression, **k):
        appels.append(url)
        raise tn.TelechargementImpossible("désactivé")
    monkeypatch.setattr(tn, "telecharger_via_navigateur", faux_nav)
    with pytest.raises(tn.TelechargementImpossible):
        synthese.extraire_recette("https://www.tiktok.com/@x/video/1", progression=lambda _: None)
    assert appels == ["https://www.tiktok.com/@x/video/1"]
