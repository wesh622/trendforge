"""File des tâches longues : un seul ouvrier, ordre d'exécution, états et messages d'erreur."""

from __future__ import annotations

import re
import threading
import time

import pytest

from trendforge.taches import File, Tache


def attendre(*taches: Tache, delai: float = 5.0) -> None:
    fin = time.monotonic() + delai
    while any(t.fin is None for t in taches):
        if time.monotonic() > fin:
            pytest.fail("la file n'a pas traité les tâches à temps")
        time.sleep(0.01)


def test_execute_dans_l_ordre_d_ajout():
    f = File()
    ordre: list[int] = []
    verrou = threading.Event()

    def bloquante(t: Tache):
        verrou.wait(5)
        ordre.append(0)

    taches = [f.ajouter("première", bloquante)]
    taches += [f.ajouter(f"n{i}", lambda t, i=i: ordre.append(i)) for i in range(1, 6)]
    # Tant que la première tourne, les autres attendent (un seul ouvrier)
    time.sleep(0.05)
    assert taches[0].etat == "en cours"
    assert all(t.etat == "en attente" for t in taches[1:])
    assert f.actives() == taches
    verrou.set()
    attendre(*taches)
    assert ordre == [0, 1, 2, 3, 4, 5]
    assert all(t.etat == "terminée" for t in taches)
    assert f.actives() == []


def test_terminee_garde_le_resultat_et_les_dates():
    f = File()
    t = f.ajouter("calcul", lambda t: 42)
    attendre(t)
    assert t.etat == "terminée" and t.resultat == 42 and t.erreur is None
    assert t.debut is not None and t.fin >= t.debut


def test_echec_avec_message_premiere_ligne():
    f = File()

    def casse(t: Tache):
        t.noter("début")
        raise RuntimeError("téléchargement impossible\ndétail de la pile")

    t = f.ajouter("casse", casse)
    attendre(t)
    assert t.etat == "échec"
    assert t.erreur == "téléchargement impossible"
    assert t.derniere.endswith("✗ téléchargement impossible")
    assert len(t.lignes) == 2


def test_echec_sans_message_donne_le_type():
    f = File()

    def casse(t: Tache):
        raise KeyError

    t = f.ajouter("casse", casse)
    attendre(t)
    assert t.etat == "échec" and t.erreur == "KeyError"


def test_echec_message_tronque_a_300_caracteres():
    f = File()
    t = f.ajouter("casse", lambda t: (_ for _ in ()).throw(ValueError("x" * 1000)))
    attendre(t)
    assert t.erreur == "x" * 300


def test_echec_message_commencant_par_un_saut_de_ligne():
    f = File()

    def casse(t: Tache):
        raise RuntimeError("\nla vraie cause")

    t = f.ajouter("casse", casse)
    attendre(t)
    assert t.erreur


def test_une_erreur_n_arrete_pas_l_ouvrier():
    f = File()
    t1 = f.ajouter("casse", lambda t: 1 / 0)
    t2 = f.ajouter("ok", lambda t: "ok")
    attendre(t1, t2)
    assert (t1.etat, t2.etat) == ("échec", "terminée")
    assert t2.resultat == "ok"


def test_noter_horodate_les_lignes():
    t = Tache("x", lambda t: None)
    assert t.derniere == ""
    t.noter("étape 1")
    t.noter("étape 2")
    assert len(t.lignes) == 2
    assert re.fullmatch(r"\d{2}:\d{2}:\d{2}  étape 1", t.lignes[0])
    assert t.derniere.endswith("  étape 2")


def test_identifiants_croissants_et_recentes():
    f = File()
    taches = [f.ajouter(f"t{i}", lambda t: None) for i in range(10)]
    attendre(*taches)
    ids = [t.id for t in taches]
    assert ids == sorted(ids) and len(set(ids)) == 10
    assert f.recentes(3) == [taches[9], taches[8], taches[7]]
    assert f.recentes() == list(reversed(taches[-8:]))
