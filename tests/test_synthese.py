"""Synthèse de recette : conversion de la sortie de Claude en recette v3 (sans appel à Claude)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from trendforge.models import Recipe
from trendforge.synthese import (PartieSortie, RecetteSortie, SceneSortie, _borne, _vers_recette,
                                 voix_elevenlabs_par_defaut)


def sortie(**maj) -> RecetteSortie:
    d = dict(
        recipe_id="numbered-facts",
        niche="science", themes=["space", "oceans"], sources_acceptees=["actualite", "google_trends"],
        angle="Facts that sound fake but are true", transformation="Re-tell the fact with a new angle",
        format="narration", duree_min_s=25, duree_max_s=40,
        structure=[PartieSortie(part="hook", debut_s=0, fin_s=3, pattern="shocking promise",
                                example="This planet rains glass."),
                   PartieSortie(part="list_item", debut_s=3, fin_s=20, beats=3),
                   PartieSortie(part="cta", debut_s=20, fin_s=24)],
        pov="narrator", wpm=170, reading_level="grade 6", tone="curious",
        hashtags=["#science", "#facts", "#space"],
        ambiance="dark blue gradient", scene_defaut="big emoji pop",
        scenes=[SceneSortie(part="hook", animation="title slams in"),
                SceneSortie(part="list_item", animation="numbered card slides in")],
        changement_s=2.5, zoom_punch=True, mots_a_l_ecran=2, position_sous_titres="center",
        voix_genre="female", voix_age="young adult", voix_vitesse=1.05,
        musique="lofi", musique_db=-22, sfx=["whoosh"], why_it_works="Curiosity gap",
    )
    d.update(maj)
    return RecetteSortie(**d)


TEL = SimpleNamespace(url="https://www.tiktok.com/@x/video/123", vues=120000, duree_s=33.4)


def valider(s: RecetteSortie, tel=TEL) -> Recipe:
    return Recipe.model_validate(_vers_recette(s, tel))


@pytest.mark.parametrize("x, attendu", [(5, 5), (0.1, 0.8), (40, 10), (0.8, 0.8), (10, 10)])
def test_borne(x, attendu):
    assert _borne(x, 0.8, 10) == attendu


def test_vers_recette_donne_une_recette_valide():
    r = valider(sortie())
    assert r.schema_version == 3 and r.recipe_id == "numbered-facts"
    assert str(r.source.url) == TEL.url and r.source.views == 120000 and r.source.duration_s == 33.4
    c = r.contenu
    assert c.target_duration_s == (25, 40) and c.type_video == "courte"
    assert [p.part for p in c.structure] == ["hook", "list_item", "cta"]
    assert c.structure[0].seconds == (0, 3) and c.structure[0].example == "This planet rains glass."
    assert c.structure[1].beats == 3
    assert [s.value for s in c.sources_acceptees] == ["actualite", "google_trends"]
    assert c.script_style.wpm == 170 and c.posting.hashtags == ["#science", "#facts", "#space"]
    v = r.visuel
    assert v.moteur == "html" and v.fond == "anime"
    assert v.scene_pour("hook") == "title slams in" and v.scene_pour("cta") == "big emoji pop"
    assert v.rythme.changement_s == 2.5 and v.rythme.zoom_punch
    assert v.sous_titres.words_on_screen == 2 and v.sous_titres.position == "center"
    assert v.voix.gender == "female" and v.voix.speed == 1.05 and v.voix.engine_hint is None
    assert v.audio.music_db == -22 and v.audio.sfx == ["whoosh"]
    assert r.why_it_works == "Curiosity gap"


def test_source_locale_sans_url():
    tel = SimpleNamespace(url="/home/x/video.mp4", vues=None, duree_s=12.0)
    assert valider(sortie(), tel).source.url is None


def test_valeurs_hors_bornes_ramenees():
    r = valider(sortie(changement_s=40, wpm=400, voix_vitesse=2.0, musique_db=0, mots_a_l_ecran=12))
    assert r.visuel.rythme.changement_s == 10
    assert r.contenu.script_style.wpm == 220
    assert r.visuel.voix.speed == 1.2
    assert r.visuel.audio.music_db == -10
    assert r.visuel.sous_titres.words_on_screen == 6


def test_valeurs_sous_les_bornes_ramenees():
    r = valider(sortie(changement_s=0.1, wpm=50, voix_vitesse=0.3, musique_db=-80, mots_a_l_ecran=0))
    assert r.visuel.rythme.changement_s == 0.8
    assert r.contenu.script_style.wpm == 120
    assert r.visuel.voix.speed == 0.8
    assert r.visuel.audio.music_db == -40
    assert r.visuel.sous_titres.words_on_screen == 1


@pytest.mark.parametrize("donnes, attendus", [
    ([], ["#fyp", "#foryou", "#viral"]),
    (["#a"], ["#a", "#fyp", "#foryou"]),
    (["#a", "#b"], ["#a", "#b", "#fyp"]),
    (["#a", "#b", "#c", "#d"], ["#a", "#b", "#c", "#d"]),
    (["#a", "#b", "#c", "#d", "#e", "#f", "#g"], ["#a", "#b", "#c", "#d", "#e"]),
])
def test_hashtags_completes_ou_tronques(donnes, attendus):
    assert valider(sortie(hashtags=donnes)).contenu.posting.hashtags == attendus


@pytest.mark.parametrize("brut, attendu", [
    ("Numbered Facts", "numbered-facts"),
    ("  Top_5 / Facts!! ", "top-5-facts"),
    ("--déjà-vu--", "d-j--vu"),
    ("!!!", "recette"),
    ("a" * 80, "a" * 60),
])
def test_recipe_id_nettoye(brut, attendu):
    assert valider(sortie(recipe_id=brut)).recipe_id == attendu


def test_voix_elevenlabs_par_defaut():
    f, m = voix_elevenlabs_par_defaut("female"), voix_elevenlabs_par_defaut("male")
    assert f.startswith("elevenlabs:") and m.startswith("elevenlabs:") and f != m
    assert voix_elevenlabs_par_defaut("autre") == m
    # La recette complète avec la voix par défaut reste valide
    d = _vers_recette(sortie(), TEL)
    d["visuel"]["voix"]["engine_hint"] = f
    assert Recipe.model_validate(d).visuel.voix.engine_hint == f
