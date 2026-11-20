"""Moteur visuel HTML : prompt, nettoyage de la réponse, contrôle des pages et capture dans Chrome.

Les tests marqués `navigateur` lancent Chrome via Playwright sur de petites pages écrites dans
tmp_path ; ils sont ignorés si Playwright (groupe `bench`) ou Chrome n'est pas disponible.
Aucune requête ne sort de la machine : la page « réseau » vise 127.0.0.1.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from trendforge import animation
from trendforge.animation import ZONE_SURE, nettoyer_html, prompt_animation
from trendforge.captions import Charte, Mot
from trendforge.models import charger_recette_dict

RECETTES = Path(__file__).resolve().parents[1] / "recettes"


# --------------------------------------------------------------------------- sans navigateur

@pytest.mark.parametrize("brut", [
    "```html\n<!doctype html><html><body>x</body></html>\n```",
    "Voici la page :\n```\n<!DOCTYPE html>\n<html><body>x</body></html>```\nBonne vidéo !",
    "  <!doctype html><html><body>x</body></html>  ",
])
def test_nettoyer_html_retire_les_balises_markdown(brut):
    propre = nettoyer_html(brut)
    assert propre.lower().startswith("<!doctype html>") and propre.endswith("</html>")
    assert "```" not in propre


def test_nettoyer_html_sans_doctype_rend_le_texte_nettoye():
    assert nettoyer_html("  <div>pas un document</div>\n") == "<div>pas un document</div>"


def test_prompt_animation_contient_les_mots_et_les_scenes():
    recette = charger_recette_dict(json.loads((RECETTES / "top-5.json").read_text(encoding="utf-8")))
    mots = [Mot("Five", 0.0, 0.3), Mot("things", 0.35, 0.8), Mot("nobody", 0.9, 1.4)]
    charte = Charte(police="Ubuntu", couleur="#FFFFFF", accent="#FFD400")
    p = prompt_animation(recette, "Five things nobody tells you.", mots, charte)
    assert "0 Five 0.00-0.30" in p and "1 things 0.35-0.80" in p and "2 nobody 0.90-1.40" in p
    assert "Total duration: 2.00 s." in p
    assert "Five things nobody tells you." in p
    assert 'font "Ubuntu"' in p and "#FFD400" in p
    # Une scène par partie de la structure (scène par défaut pour une partie non décrite)
    debut = p.index("Planned structure")
    parties = json.loads(p[p.index("[", debut):p.index("\n]", debut) + 2])
    assert len(parties) == len(recette.contenu.structure)
    for partie, attendu in zip(parties, recette.contenu.structure):
        assert partie["part"] == attendu.part
        assert partie["scene"] == recette.visuel.scene_pour(attendu.part)
    # Le visuel envoyé n'inclut ni la voix ni l'audio
    visuel = json.loads(p[p.index("{"):p.index("\n}") + 2])
    assert "voix" not in visuel and "audio" not in visuel and "scenes" in visuel


def test_ecrire_page_appelle_le_llm_et_nettoie(monkeypatch):
    recette = charger_recette_dict(json.loads((RECETTES / "top-5.json").read_text(encoding="utf-8")))
    vus = {}

    def faux_generer_texte(nom, systeme, message):
        vus.update(nom=nom, systeme=systeme, message=message)
        return "```html\n<!doctype html><html></html>\n```", "appel"

    monkeypatch.setattr(animation.llm, "generer_texte", faux_generer_texte)
    html, appel = animation.ecrire_page(recette, "s", [Mot("a", 0, 1)], Charte(police="Ubuntu"),
                                        retour="dessiner absent", consignes="plus de rouge")
    assert html == "<!doctype html><html></html>" and appel == "appel"
    assert vus["nom"] == "animation_html"
    assert '"Ubuntu"' in vus["systeme"] and "{police}" not in vus["systeme"] and "{changement}" not in vus["systeme"]
    assert "dessiner absent" in vus["message"] and "plus de rouge" in vus["message"]


# --------------------------------------------------------------------------- navigateur

def _chrome_disponible() -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Playwright absent (uv run --group bench pytest)"
    try:
        with sync_playwright() as p:
            p.chromium.launch(channel="chrome").close()
    except Exception as e:  # noqa: BLE001
        return f"Chrome indisponible : {str(e).splitlines()[0]}"
    return None


_RAISON = None


@pytest.fixture(scope="module")
def chrome():
    global _RAISON
    if _RAISON is None:
        _RAISON = _chrome_disponible() or ""
    if _RAISON:
        pytest.skip(_RAISON)


DATA = {"duree": 2.0, "mots": [{"w": "hello", "d": 0.1, "f": 0.5}, {"w": "world", "d": 0.6, "f": 1.0}]}


def page(tmp_path: Path, corps: str, script: str) -> Path:
    f = tmp_path / "page.html"
    f.write_text(f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
html, body {{ margin: 0; width: 1080px; height: 1920px; overflow: hidden; background: #123; color: #fff;
             font: 60px sans-serif; }}
.t {{ position: absolute; white-space: nowrap; }}
</style></head><body>{corps}<script>{script}</script></body></html>""", encoding="utf-8")
    return f


CORRECTE = ('<div id="a" class="t" style="left:200px; top:400px">Titre</div>'
            '<div id="b" class="t" style="left:200px; top:1300px">légende</div>',
            "window.dessiner = function (t) { document.getElementById('b').textContent = t < 1 ? 'hello' : 'world'; };")


@pytest.mark.navigateur
def test_controler_page_correcte(tmp_path, chrome):
    c = animation.controler(page(tmp_path, *CORRECTE), DATA, n_instants=6)
    assert c.ok, c
    assert c.erreurs == c.debordements == c.chevauchements == []
    assert c.ms_par_image > 0


@pytest.mark.navigateur
def test_controler_sans_dessiner(tmp_path, chrome):
    c = animation.controler(page(tmp_path, '<div class="t">x</div>', "window.autre = 1;"), DATA, n_instants=4)
    assert not c.ok
    assert c.erreurs == ["window.dessiner is not defined"]


@pytest.mark.navigateur
def test_controler_dessiner_leve_une_exception(tmp_path, chrome):
    script = "window.dessiner = function (t) { if (t > 1) throw new Error('boum'); };"
    c = animation.controler(page(tmp_path, CORRECTE[0], script), DATA, n_instants=4)
    assert not c.ok
    assert any("threw" in e and "boum" in e for e in c.erreurs), c.erreurs
    # Seuls les instants t > 1 cassent (2 sur 4)
    assert sum("threw" in e for e in c.erreurs) == 2


@pytest.mark.navigateur
def test_controler_erreur_au_chargement(tmp_path, chrome):
    script = "window.dessiner = function (t) {}; undefinedFunction();"
    c = animation.controler(page(tmp_path, CORRECTE[0], script), DATA, n_instants=2)
    assert any(e.startswith("exception:") and "undefinedFunction" in e for e in c.erreurs), c.erreurs


@pytest.mark.navigateur
def test_controler_texte_hors_zone_persistant(tmp_path, chrome):
    corps = CORRECTE[0] + '<div class="t" style="left:900px; top:600px">DÉBORDE ICI</div>'
    c = animation.controler(page(tmp_path, corps, CORRECTE[1]), DATA, n_instants=4)
    assert not c.ok and not c.erreurs
    assert len(c.debordements) == 1  # signalé une seule fois malgré 4 instants
    assert "DÉBORDE ICI" in c.debordements[0] and "outside the safe zone" in c.debordements[0]


@pytest.mark.navigateur
def test_controler_texte_hors_zone_bref_non_signale(tmp_path, chrome):
    # Le texte entre par la gauche : hors zone seulement pendant les 0,2 premières s de chaque seconde.
    corps = CORRECTE[0] + '<div id="e" class="t" style="top:800px">ENTRÉE</div>'
    script = """window.dessiner = function (t) {
      const f = t % 1;
      document.getElementById('e').style.left = (f < 0.2 ? -300 + f * 1500 : 200) + 'px';
    };"""
    c = animation.controler(page(tmp_path, corps, script), DATA, n_instants=24)
    # Vérifie que le contrôle a bien échantillonné un instant où le texte sortait
    instants = [DATA["duree"] * (k + 0.5) / 24 for k in range(24)]
    assert any(t % 1 < 0.2 for t in instants)
    assert c.debordements == [], c.debordements
    assert c.ok, c


@pytest.mark.navigateur
def test_controler_textes_superposes(tmp_path, chrome):
    corps = ('<div class="t" style="left:200px; top:700px">SUPERPOSÉ</div>'
             '<div class="t" style="left:210px; top:710px">CACHÉ</div>'
             '<div class="t" style="left:200px; top:1300px">légende</div>')
    c = animation.controler(page(tmp_path, corps, "window.dessiner = function (t) {};"), DATA, n_instants=4)
    assert not c.ok and not c.erreurs and not c.debordements
    assert len(c.chevauchements) == 1
    assert "SUPERPOSÉ" in c.chevauchements[0] and "CACHÉ" in c.chevauchements[0]


@pytest.mark.navigateur
def test_controler_texte_invisible_ignore(tmp_path, chrome):
    corps = (CORRECTE[0] + '<div class="t" style="left:0px; top:0px; opacity:0.2">fantôme</div>'
             '<div class="t" style="left:0px; top:1700px; display:none">caché</div>')
    c = animation.controler(page(tmp_path, corps, CORRECTE[1]), DATA, n_instants=4)
    assert c.ok, c


@pytest.mark.navigateur
def test_controler_requete_reseau_interdite(tmp_path, chrome):
    # 127.0.0.1:9 (port discard) : refusé localement, rien ne sort de la machine.
    corps = CORRECTE[0] + '<img src="http://127.0.0.1:9/image.png">'
    c = animation.controler(page(tmp_path, corps, CORRECTE[1]), DATA, n_instants=2)
    assert not c.ok
    assert any(e.startswith("network request forbidden: http://127.0.0.1:9/image.png") for e in c.erreurs), c.erreurs


@pytest.mark.navigateur
def test_controler_data_injectee_avant_les_scripts(tmp_path, chrome):
    script = """if (!window.DATA || window.DATA.mots[1].w !== 'world') throw new Error('DATA absente');
    window.dessiner = function (t) {};"""
    c = animation.controler(page(tmp_path, CORRECTE[0], script), DATA, n_instants=2)
    assert c.erreurs == []


@pytest.mark.navigateur
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")
def test_capturer_produit_un_mp4_d_une_seconde(tmp_path, chrome):
    wav = tmp_path / "voix.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-ac", "1", "-ar", "44100", str(wav)], check=True)
    data = {"duree": 1.0, "mots": [{"w": "hello", "d": 0.0, "f": 0.9}]}
    sortie = tmp_path / "video.mp4"
    duree_capture = animation.capturer(page(tmp_path, *CORRECTE), data, wav, sortie)
    assert sortie.exists() and duree_capture > 0
    sonde = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate",
         "-of", "json", str(sortie)], capture_output=True, text=True, check=True).stdout)
    assert float(sonde["format"]["duration"]) == pytest.approx(1.0, abs=0.15)
    flux = {s["codec_type"]: s for s in sonde["streams"]}
    assert set(flux) == {"video", "audio"}
    assert (flux["video"]["width"], flux["video"]["height"]) == (animation.LARGEUR, animation.HAUTEUR)
    assert flux["video"]["r_frame_rate"] == "30/1"


def test_zone_sure_coherente():
    assert ZONE_SURE["x_min"] < ZONE_SURE["x_max"] <= animation.LARGEUR
    assert ZONE_SURE["y_min"] < ZONE_SURE["y_max"] <= animation.HAUTEUR
