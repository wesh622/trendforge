"""Tests des sources de sujets (sans réseau : réponses réelles enregistrées dans tests/fixtures/)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from trendforge.models import FicheSujet, Reference, SourceType
from trendforge.sujets import Reserve, collecter_toutes
from trendforge.sujets.base import SourceSujets
from trendforge.sujets.bluesky import (
    SourceBluesky,
    parser_tendances,
    posts_depuis_reponse,
    references_depuis_posts,
    uri_flux,
)
from trendforge.sujets.google import (
    SourceGoogleActualites,
    SourceGoogleTrends,
    parser_actualites,
    parser_trends,
)
from trendforge.sujets.idees import SourceIdees, date_dans_texte, titre_depuis_url
from trendforge.sujets.x import CompteurDepenses, SourceX, parser_tendances_x

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)


def fixture_json(nom: str) -> dict:
    return json.loads((FIX / nom).read_text(encoding="utf-8"))


def fiche(type_=SourceType.actualite, titre="Un sujet", url="https://example.com/a", heures=1, **kw) -> FicheSujet:
    d = NOW - timedelta(hours=heures)
    refs = [] if type_ in {SourceType.forum, SourceType.invente} else [Reference(titre="src", url="https://example.com/s")]
    return FicheSujet(id=kw.pop("id", f"{type_.value}-{titre}"), type=type_, url=url, date_source=d,
                      ajoutee_le=NOW, titre=titre, resume=titre, references=refs, **kw)


# --- idees/ ---------------------------------------------------------------------------

REDDIT = "https://www.reddit.com/r/AmItheAsshole/comments/1abcde/aita_for_refusing_to_pay_for_my_sisters_wedding/"


@pytest.fixture
def dossier_idees(tmp_path: Path) -> Path:
    d = tmp_path / "idees"
    d.mkdir()
    (d / "lien_seul.txt").write_text(REDDIT + "\n", encoding="utf-8")
    (d / "texte_seul.md").write_text(
        "# My neighbor kept stealing my packages\n\nSo this happened on 2026-11-02. My neighbor took three "
        "packages. Then I set up a camera! The rest is history.", encoding="utf-8")
    (d / "lien_et_texte.txt").write_text(
        "https://forum.example.org/t/boss-story/42\nMy boss asked me to train my replacement. "
        "I said yes. Then the twist came.", encoding="utf-8")
    (d / "raccourci.url").write_text("[InternetShortcut]\nURL=https://www.reddit.com/r/pettyrevenge/comments/9xyz/the_parking_spot/\n",
                                     encoding="utf-8")
    (d / "vide.txt").write_text("   \n", encoding="utf-8")
    (d / ".syncthing.en_cours.txt.tmp").write_text("partiel", encoding="utf-8")
    (d / "image.jpg").write_bytes(b"\xff\xd8")
    return d


def test_idees_formats(dossier_idees: Path) -> None:
    src = SourceIdees(dossier_idees)
    fiches = {f.titre: f for f in src.collecter()}
    assert len(fiches) == 4
    assert all(f.type is SourceType.forum for f in fiches.values())

    lien = fiches["Aita for refusing to pay for my sisters wedding"]
    assert str(lien.url) == REDDIT and lien.texte_source is None

    texte = fiches["My neighbor kept stealing my packages"]
    assert texte.url is None
    assert "three packages" in texte.texte_source
    assert texte.date_source == datetime(2026, 11, 2, tzinfo=timezone.utc)  # date trouvée dans le texte
    assert texte.resume.startswith("My neighbor kept stealing")

    mixte = next(f for f in fiches.values() if f.url and "forum.example.org" in str(f.url))
    assert mixte.texte_source.startswith("My boss asked me")
    assert "forum.example.org" not in mixte.texte_source
    assert mixte.titre.startswith("My boss asked me")

    racc = next(f for f in fiches.values() if f.url and "pettyrevenge" in str(f.url))
    assert racc.titre == "The parking spot"

    # le fichier vide est signalé et laissé en place ; les fichiers ignorés ne sont pas lus
    assert [p.name for p, _ in src.erreurs] == ["vide.txt"]


def test_idees_archivage(dossier_idees: Path) -> None:
    src = SourceIdees(dossier_idees)
    src.collecter()
    assert (dossier_idees / "lien_seul.txt").exists()  # rien ne bouge avant archiver()
    deplaces = src.archiver()
    assert len(deplaces) == 4
    restants = sorted(p.name for p in dossier_idees.iterdir() if p.is_file())
    assert restants == [".syncthing.en_cours.txt.tmp", "image.jpg", "vide.txt"]
    assert (dossier_idees / "traitees" / "raccourci.url").exists()
    # un 2e import ne relit pas les fichiers traités
    assert SourceIdees(dossier_idees).collecter() == []


def test_idees_date_fichier_par_defaut(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("A story without any date.", encoding="utf-8")
    t = datetime(2026, 10, 1, 12, tzinfo=timezone.utc).timestamp()
    os.utime(f, (t, t))
    (fi,) = SourceIdees(tmp_path).collecter()
    assert fi.date_source == datetime(2026, 10, 1, 12, tzinfo=timezone.utc)


def test_date_et_titre_helpers() -> None:
    assert date_dans_texte("posted 3/11/2026") == datetime(2026, 11, 3, tzinfo=timezone.utc)
    assert date_dans_texte("Posted Nov 5, 2026 by someone") == datetime(2026, 11, 5, tzinfo=timezone.utc)
    assert date_dans_texte("rien") is None
    assert titre_depuis_url("https://example.com/blog/my-great-story.html") == "My great story"


def test_idees_jamais_de_reseau(dossier_idees: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def interdit(*a, **k):
        raise AssertionError("idees ne doit jamais télécharger la page")
    monkeypatch.setattr(httpx.Client, "send", interdit)
    assert len(SourceIdees(dossier_idees).collecter()) == 4


# --- réserve ---------------------------------------------------------------------------


def test_dedoublonnage(tmp_path: Path) -> None:
    r = Reserve(tmp_path)
    a = fiche(titre="Wii turns 20", url="https://www.example.com/a/?utm_source=x")
    assert r.ajouter([a], NOW)["ajoutees"] == 1
    stats = r.ajouter([
        fiche(id="autre-1", titre="Autre titre", url="https://example.com/a"),  # même URL normalisée
        fiche(id="autre-2", titre="wii   TURNS 20 !", url="https://example.com/b"),  # même titre normalisé
        fiche(id="autre-3", titre="Vraiment nouveau", url="https://example.com/c"),
        a,  # même id
    ], NOW)
    assert stats == {"ajoutees": 1, "doublons": 3, "perimees": 0}
    assert [f.titre for f in r.charger()] == ["Wii turns 20", "Vraiment nouveau"]


def test_peremption_48h(tmp_path: Path) -> None:
    r = Reserve(tmp_path)
    r.ajouter([
        fiche(titre="fraiche", heures=47, url="https://e.com/1"),
        fiche(titre="limite", heures=40, url="https://e.com/2"),
        fiche(type_=SourceType.forum, titre="vieille histoire", heures=24 * 30, url="https://e.com/3"),
    ], NOW)
    # une tendance déjà périmée n'entre pas
    assert r.ajouter([fiche(titre="trop vieille", heures=49, url="https://e.com/4")], NOW)["perimees"] == 1
    retirees = r.purger(NOW + timedelta(hours=5))  # « fraiche » a maintenant 52 h
    assert [f.titre for f in retirees] == ["fraiche"]
    assert {f.titre for f in r.charger()} == {"limite", "vieille histoire"}  # l'histoire collée reste


def test_ordre_selection(tmp_path: Path) -> None:
    r = Reserve(tmp_path)
    r.ajouter([
        fiche(type_=SourceType.forum, titre="histoire ancienne", heures=500, url="https://e.com/1"),
        fiche(type_=SourceType.tendance_bluesky, titre="tendance 10h", heures=10, url="https://e.com/2"),
        fiche(type_=SourceType.forum, titre="histoire recente", heures=3, url="https://e.com/3"),
        fiche(type_=SourceType.google_trends, titre="tendance 2h", heures=2, url="https://e.com/4"),
    ], NOW)
    assert [f.titre for f in r.selection(NOW)] == [
        "tendance 2h", "tendance 10h", "histoire recente", "histoire ancienne"]


# --- isolement des sources -------------------------------------------------------------


class SourceEnPanne(SourceSujets):
    nom = "panne"

    def collecter(self):
        raise RuntimeError("boum")


class SourceOk(SourceSujets):
    nom = "ok"

    def collecter(self):
        return [fiche()]


def test_source_en_panne_isolee() -> None:
    res = collecter_toutes([SourceEnPanne(), SourceOk()])
    assert [(r.nom, r.statut) for r in res] == [("panne", "erreur"), ("ok", "ok")]
    assert len(res[1].fiches) == 1 and "boum" in res[0].message


# --- X ---------------------------------------------------------------------------------


def test_x_desactive_sans_jeton(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    src = SourceX(tmp_path / "dep.json")
    ok, raison = src.disponible()
    assert not ok and "X_BEARER_TOKEN" in raison
    (r,) = collecter_toutes([src])
    assert r.statut == "desactivee" and r.fiches == []
    assert not (tmp_path / "dep.json").exists()


def test_x_compteur_et_plafond(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X_BEARER_TOKEN", "jeton-de-test")
    appels = []

    def repondre(req: httpx.Request) -> httpx.Response:
        if req.url.host == "api.x.com":
            appels.append(req)
            assert req.headers["Authorization"] == "Bearer jeton-de-test"
            assert req.url.path == "/2/trends/by/woeid/23424977"
            return httpx.Response(200, json={"data": [{"trend_name": "#Wii20", "tweet_count": 1200}]})
        return httpx.Response(200, content=(FIX / "gnews_search.xml").read_bytes())

    src = SourceX(tmp_path / "dep.json", cout_par_appel=1.4, plafond=3.0,
                  transport=httpx.MockTransport(repondre))
    for _ in range(2):
        (r,) = collecter_toutes([src])
        assert r.statut == "ok", r.message
        f = r.fiches[0]
        assert f.type is SourceType.tendance_x and f.titre == "#Wii20" and len(f.references) == 3
    # 2 × 1,4 = 2,8 $ ; un 3e appel dépasserait 3 $ : la source se désactive sans appeler X
    (r,) = collecter_toutes([src])
    assert r.statut == "desactivee" and "plafond" in r.message
    assert len(appels) == 2
    d = json.loads((tmp_path / "dep.json").read_text())
    assert d["appels"] == 2 and d["depense"] == pytest.approx(2.8)


def test_x_compteur_change_de_mois(tmp_path: Path) -> None:
    c = CompteurDepenses(tmp_path / "dep.json", plafond=3.0)
    c.enregistrer(2.9, datetime(2026, 10, 31, tzinfo=timezone.utc))
    assert not c.peut_depenser(0.2, datetime(2026, 10, 31, tzinfo=timezone.utc))
    assert c.peut_depenser(0.2, datetime(2026, 11, 1, tzinfo=timezone.utc))


def test_x_parser() -> None:
    assert parser_tendances_x({"data": [{"trend_name": "A", "tweet_count": 3}, {"trend_name": "B"}]}) == [
        {"nom": "A", "posts": 3}, {"nom": "B", "posts": None}]
    with pytest.raises(Exception):
        parser_tendances_x({"errors": [{"message": "nope"}]})


# --- Bluesky (réponses réelles enregistrées) ------------------------------------------


def test_bluesky_parser_getTrends() -> None:
    ts = parser_tendances(fixture_json("bsky_getTrends.json"))
    assert len(ts) == 5
    t = ts[0]
    assert t["nom"] == "Epstein files release" and t["category"] == "politics"
    assert t["started_at"].tzinfo is not None and t["post_count"] == 894
    assert uri_flux(t["link"]) == "at://did:plc:qrz3lhbyuxbeilrc6nekdqme/app.bsky.feed.generator/29030774f525"


def test_bluesky_parser_getTrendingTopics() -> None:
    ts = parser_tendances(fixture_json("bsky_getTrendingTopics.json"))
    assert len(ts) == 5 and ts[0]["started_at"] is None and ts[0]["description"]


@pytest.mark.parametrize("nom", ["bsky_getFeed.json", "bsky_searchPosts.json"])
def test_bluesky_references(nom: str) -> None:
    posts = posts_depuis_reponse(fixture_json(nom))
    refs = references_depuis_posts(posts, 3)
    assert 1 <= len(refs) <= 3
    assert all(str(r.url).startswith("https://bsky.app/profile/") and "/post/" in str(r.url) for r in refs)
    assert all(r.titre.startswith("@") for r in refs)


def test_bluesky_source_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("trendforge.sujets.bluesky.maintenant", lambda: NOW)

    def repondre(req: httpx.Request) -> httpx.Response:
        assert req.headers["User-Agent"] == "TrendForge/0.1"
        if req.url.path.endswith("getTrends"):
            return httpx.Response(200, json=fixture_json("bsky_getTrends.json"))
        if req.url.path.endswith("getFeed"):
            return httpx.Response(200, json=fixture_json("bsky_getFeed.json"))
        return httpx.Response(404)

    fiches = SourceBluesky(transport=httpx.MockTransport(repondre)).collecter()
    assert len(fiches) == 3  # les 2 tendances « politics » de l'enregistrement sont écartées
    f = fiches[0]
    assert f.type is SourceType.tendance_bluesky and f.references
    assert str(f.url).startswith("https://bsky.app/profile/")


def test_bluesky_repli_topics_et_search(monkeypatch: pytest.MonkeyPatch) -> None:
    def repondre(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p.endswith("getTrends"):
            return httpx.Response(500)
        if p.endswith("getTrendingTopics"):
            return httpx.Response(200, json=fixture_json("bsky_getTrendingTopics.json"))
        if p.endswith("getFeed"):
            return httpx.Response(401)
        if p.endswith("searchPosts") and req.url.host == "public.api.bsky.app":
            return httpx.Response(403)
        return httpx.Response(200, json=fixture_json("bsky_searchPosts.json"))

    src = SourceBluesky(transport=httpx.MockTransport(repondre))
    fiches = src.collecter()
    assert len(fiches) == 5 and all(f.references for f in fiches)
    assert any("getTrendingTopics" in n for n in src.notes)


# --- Google (réponses réelles enregistrées) -------------------------------------------


def test_google_parser_actualites() -> None:
    items = parser_actualites((FIX / "gnews_top.xml").read_bytes())
    assert len(items) == 3
    i = items[0]
    assert i["media"] and not i["titre"].endswith(f" - {i['media']}")
    assert i["date"].tzinfo is not None
    assert 1 <= len(i["grappe"]) and str(i["grappe"][0].url).startswith("https://news.google.com/")


def test_google_parser_trends() -> None:
    ts = parser_trends((FIX / "gtrends.xml").read_bytes())
    assert len(ts) == 10
    assert ts[0]["terme"] == "troy aikman" and ts[0]["trafic"] == "2000+"
    assert ts[0]["date"] == datetime(2026, 11, 19, 21, 10, tzinfo=timezone.utc)  # 13:10 -0800
    assert ts[0]["articles"] == []  # le flux actuel n'a plus de ht:news_item


def test_google_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("trendforge.sujets.google.maintenant", lambda: NOW)

    def repondre(req: httpx.Request) -> httpx.Response:
        if req.url.host == "trends.google.com":
            return httpx.Response(200, content=(FIX / "gtrends.xml").read_bytes())
        if "/rss/search" in req.url.path:
            return httpx.Response(200, content=(FIX / "gnews_search.xml").read_bytes())
        return httpx.Response(200, content=(FIX / "gnews_top.xml").read_bytes())

    t = httpx.MockTransport(repondre)
    tendances = SourceGoogleTrends(limite=3, transport=t).collecter()
    assert len(tendances) == 3 and all(len(f.references) == 3 for f in tendances)
    assert tendances[0].type is SourceType.google_trends
    actus = SourceGoogleActualites(transport=t).collecter()
    assert len(actus) == 3 and all(f.type is SourceType.actualite and f.references for f in actus)
