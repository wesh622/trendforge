"""Bibliothèque des vidéos (sorties/) : chargement, statuts, publication, statistiques.

Le dossier SORTIES est redirigé vers tmp_path : les vrais dossiers ne sont jamais touchés.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trendforge import bibliotheque as bib


@pytest.fixture
def sorties(tmp_path, monkeypatch) -> Path:
    d = tmp_path / "sorties"
    d.mkdir()
    monkeypatch.setattr(bib, "SORTIES", d)
    monkeypatch.setattr(bib, "RECETTES", tmp_path / "recettes")
    return d


def creer(sorties: Path, nom: str, statut: str = "a_valider", recette: str = "top-5", **extra) -> Path:
    d = sorties / nom
    d.mkdir()
    journal = {"statut": statut, "recette": {"recipe_id": recette}, **extra}
    (d / "journal.json").write_text(json.dumps(journal), encoding="utf-8")
    return d


def lire_journal(d: Path) -> dict:
    return json.loads((d / "journal.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- charger / lister

def test_charger_lit_le_journal_et_les_proprietes(sorties):
    d = creer(sorties, "20261119-101500_top-5", fiche_sujet={"titre": "Un titre"}, voix={"duree_s": 31.5},
              cout_llm_usd=0.12, avertissements_page=["texte hors zone"])
    (d / "script.txt").write_text("Le script", encoding="utf-8")
    (d / "video.mp4").write_bytes(b"\x00")
    v = bib.charger(d)
    assert v is not None
    assert v.id == "20261119-101500_top-5"
    assert v.statut == "a_valider" and v.recette == "top-5" and v.titre == "Un titre"
    assert v.date == datetime(2026, 11, 19, 10, 15, 0, tzinfo=timezone.utc)
    assert v.script == "Le script" and v.legende == ""
    assert v.fichier == d / "video.mp4"
    assert v.duree_s == 31.5 and v.cout_usd == 0.12
    assert v.avertissements == ["texte hors zone"] and v.publication == {}


def test_charger_valeurs_par_defaut(sorties):
    d = sorties / "sans-date"
    d.mkdir()
    (d / "journal.json").write_text("{}", encoding="utf-8")
    v = bib.charger(d)
    assert v.statut == "inconnu" and v.recette == "?" and v.fichier is None and v.cout_usd == 0.0
    # Nom sans horodatage : on retombe sur la date de modification du dossier
    assert v.date.tzinfo is timezone.utc


def test_charger_sans_journal_ou_json_invalide(sorties):
    vide = sorties / "vide"
    vide.mkdir()
    assert bib.charger(vide) is None
    casse = sorties / "casse"
    casse.mkdir()
    (casse / "journal.json").write_text("{pas du json", encoding="utf-8")
    assert bib.charger(casse) is None


def test_lister_trie_du_plus_recent_au_plus_ancien(sorties):
    creer(sorties, "20261118-090000_a")
    creer(sorties, "20261120-090000_c")
    creer(sorties, "20261119-090000_b")
    (sorties / "fichier-perdu.txt").write_text("x")
    assert [v.id for v in bib.lister()] == ["20261120-090000_c", "20261119-090000_b", "20261118-090000_a"]


def test_lister_filtre_par_statut(sorties):
    creer(sorties, "20261118-090000_a", statut="a_valider")
    creer(sorties, "20261119-090000_b", statut="validee")
    creer(sorties, "20261120-090000_c", statut="publiee")
    assert [v.id for v in bib.lister({"validee", "publiee"})] == ["20261120-090000_c", "20261119-090000_b"]
    assert bib.lister({"rejetee"}) == []


def test_lister_ignore_un_journal_illisible(sorties):
    creer(sorties, "20261119-090000_ok")
    casse = sorties / "20261120-090000_casse"
    casse.mkdir()
    (casse / "journal.json").write_text('{"statut": "a_valider",', encoding="utf-8")
    assert [v.id for v in bib.lister()] == ["20261119-090000_ok"]


def test_lister_ignore_un_journal_binaire(sorties):
    creer(sorties, "20261119-090000_ok")
    casse = sorties / "20261120-090000_binaire"
    casse.mkdir()
    (casse / "journal.json").write_bytes(b"\xff\xfe\x00garbage")
    assert [v.id for v in bib.lister()] == ["20261119-090000_ok"]


def test_lister_ignore_un_journal_qui_n_est_pas_un_objet(sorties):
    creer(sorties, "20261119-090000_ok")
    casse = sorties / "20261120-090000_liste"
    casse.mkdir()
    (casse / "journal.json").write_text("[1, 2]", encoding="utf-8")
    assert [v.id for v in bib.lister({"a_valider"})] == ["20261119-090000_ok"]


def test_lister_sans_dossier_sorties(tmp_path, monkeypatch):
    monkeypatch.setattr(bib, "SORTIES", tmp_path / "absent")
    assert bib.lister() == []


# --------------------------------------------------------------------------- statuts

def test_changer_statut_ecrit_le_champ_date(sorties):
    d = creer(sorties, "20261119-090000_a", note="conservée")
    v = bib.changer_statut(bib.charger(d), "validee")
    j = lire_journal(d)
    assert j["statut"] == "validee" == v.statut
    assert datetime.fromisoformat(j["validee_le"]).tzinfo is not None
    assert j["note"] == "conservée"  # les autres champs du journal sont gardés
    bib.changer_statut(v, "rejetee")
    j = lire_journal(d)
    assert j["statut"] == "rejetee" and "validee_le" in j and "rejetee_le" in j


def test_marquer_publiee_ajoute_une_date_par_plateforme(sorties):
    d = creer(sorties, "20261119-090000_a", statut="validee")
    v = bib.marquer_publiee(bib.charger(d), "tiktok")
    v = bib.marquer_publiee(bib.charger(d), "youtube")
    j = lire_journal(d)
    assert j["statut"] == "publiee" == v.statut
    assert set(j["publication"]) == {"tiktok", "youtube"}
    for date in j["publication"].values():
        datetime.fromisoformat(date)


def test_stats_par_recette(sorties):
    creer(sorties, "20261118-090000_a", statut="a_valider", recette="top-5")
    creer(sorties, "20261119-090000_b", statut="publiee", recette="top-5")
    creer(sorties, "20261120-090000_c", statut="publiee", recette="top-5")
    creer(sorties, "20261120-100000_d", statut="rejetee", recette="mystere")
    assert bib.stats_par_recette() == {
        "top-5": {"total": 3, "a_valider": 1, "publiee": 2},
        "mystere": {"total": 1, "rejetee": 1},
    }


def test_supprimer_efface_le_dossier(sorties):
    d = creer(sorties, "20261119-090000_a")
    (d / "video.mp4").write_bytes(b"\x00")
    bib.supprimer(bib.charger(d))
    assert not d.exists()
    assert bib.lister() == []


# --------------------------------------------------------------------------- publication

def test_ouvrir_publication_lance_le_dossier_et_chrome(sorties, monkeypatch):
    d = creer(sorties, "20261119-090000_a", statut="validee")
    commandes = []

    def faux_popen(cmd, **kw):
        commandes.append(cmd)

    monkeypatch.setattr(bib.subprocess, "Popen", faux_popen)
    ouverts = bib.ouvrir_publication(bib.charger(d), ["tiktok", "youtube"])
    assert ouverts == ["TikTok", "YouTube Shorts"]
    assert commandes == [
        ["xdg-open", str(d)],
        ["google-chrome", bib.PLATEFORMES["tiktok"][1]],
        ["google-chrome", bib.PLATEFORMES["youtube"][1]],
    ]
    assert subprocess.Popen is faux_popen  # le monkeypatch couvre bien le module utilisé


def test_ouvrir_publication_sans_plateforme_ouvre_seulement_le_dossier(sorties, monkeypatch):
    d = creer(sorties, "20261119-090000_a")
    commandes = []
    monkeypatch.setattr(bib.subprocess, "Popen", lambda cmd, **kw: commandes.append(cmd))
    assert bib.ouvrir_publication(bib.charger(d), []) == []
    assert commandes == [["xdg-open", str(d)]]


def test_ouvrir_publication_plateforme_inconnue(sorties, monkeypatch):
    d = creer(sorties, "20261119-090000_a")
    monkeypatch.setattr(bib.subprocess, "Popen", lambda cmd, **kw: None)
    with pytest.raises(KeyError):
        bib.ouvrir_publication(bib.charger(d), ["myspace"])
