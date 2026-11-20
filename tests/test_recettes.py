"""Recette v3 : blocs contenu + visuel, mélange, migration depuis la v2."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from trendforge.models import (FicheSujet, Recipe, SourceType, charger_recette_dict, combiner,
                               migrer_v2)

RECETTES = Path(__file__).resolve().parents[1] / "recettes"


def charger(nom: str) -> Recipe:
    return charger_recette_dict(json.loads((RECETTES / f"{nom}.json").read_text(encoding="utf-8")))


@pytest.mark.parametrize("f", sorted(RECETTES.glob("*.json")), ids=lambda f: f.stem)
def test_recettes_du_depot_valides_en_v3(f: Path):
    d = json.loads(f.read_text(encoding="utf-8"))
    assert d["schema_version"] == 3
    r = Recipe.model_validate(d)
    assert r.contenu.structure[0].part == "hook"
    assert r.visuel.scene_pour("hook")


def test_combiner_garde_le_contenu_de_l_une_et_le_visuel_de_l_autre():
    histoire, faits = charger("histoire-premiere-personne"), charger("faits-etonnants")
    mix = combiner(histoire, faits)
    assert mix.recipe_id == "histoire-premiere-personne--faits-etonnants"
    assert mix.contenu == histoire.contenu
    assert mix.visuel == faits.visuel
    assert mix.type_video == "longue" and mix.mots_cibles() == histoire.mots_cibles()
    # « twist » n'est pas décrit par le visuel des faits : on retombe sur la scène par défaut
    assert mix.visuel.scene_pour("twist") == faits.visuel.scene_defaut
    assert Recipe.model_validate(mix.model_dump(mode="json")) == mix


def test_combiner_avec_soi_meme_rend_la_recette():
    r = charger("top-5")
    assert combiner(r, r) is r


def test_contenu_filtre_les_fiches_par_source():
    histoire = charger("histoire-premiere-personne").contenu
    t = datetime(2026, 11, 20, tzinfo=timezone.utc)
    forum = FicheSujet(id="a", type=SourceType.forum, date_source=t, ajoutee_le=t, titre="x", resume="y")
    tendance = FicheSujet(id="b", type=SourceType.google_trends, date_source=t, ajoutee_le=t, titre="x",
                          resume="y", references=[{"titre": "article"}])
    assert histoire.accepte(forum) and not histoire.accepte(tendance)


def test_scene_pour_une_partie_inconnue_est_refusee():
    d = json.loads((RECETTES / "top-5.json").read_text(encoding="utf-8"))
    d["visuel"]["scenes"]["generique"] = "..."
    with pytest.raises(ValidationError, match="parties inconnues"):
        Recipe.model_validate(d)


def test_duree_hors_fourchette_refusee_dans_le_contenu():
    d = json.loads((RECETTES / "top-5.json").read_text(encoding="utf-8"))
    d["contenu"]["target_duration_s"] = [46, 60]
    with pytest.raises(ValidationError, match="hors des fourchettes"):
        Recipe.model_validate(d)


def test_migration_v2_vers_v3():
    v2 = {
        "schema_version": 2, "recipe_id": "ancienne", "niche": "amazing_facts", "format": "narration",
        "language": "en", "target_duration_s": [28, 40],
        "structure": [{"part": "hook", "seconds": [0, 3]}, {"part": "cta", "seconds": [30, 34]}],
        "script_style": {"pov": "narrator", "wpm": 180, "tone": "curieux"},
        "voice": {"gender": "male", "age": "25-35"},
        "visuals": {"background": "stock_illustratif", "cut_every_s": 2.5, "zoom_punch": True},
        "audio": {"music_mood": "upbeat"},
        "posting": {"hashtags": ["#a", "#b", "#c"]},
        "why_it_works": "test",
    }
    r = charger_recette_dict(v2)
    assert r.schema_version == 3
    assert r.visuel.moteur == "stock" and r.visuel.fond == "stock_illustratif"
    assert r.visuel.rythme.changement_s == 2.5 and r.visuel.rythme.zoom_punch
    assert r.contenu.target_duration_s == (28, 40)
    assert migrer_v2({"schema_version": 3}) == {"schema_version": 3}
