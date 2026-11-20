"""Voix ElevenLabs sans réseau : httpx.MockTransport à la place de l'API, clé factice."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

from trendforge import voix_elevenlabs as el
from trendforge.captions import Mot

ffmpeg_requis = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")


@pytest.fixture(autouse=True)
def cle_factice(monkeypatch):
    monkeypatch.setattr(el, "lire_cle", lambda: "cle-de-test")


@pytest.fixture(scope="module")
def mp3_1s(tmp_path_factory) -> bytes:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg absent")
    f = tmp_path_factory.mktemp("audio") / "out.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-ac", "1", str(f)], check=True)
    return f.read_bytes()


def alignement(texte: str, pas: float = 0.1) -> dict:
    return {"characters": list(texte),
            "character_start_times_seconds": [i * pas for i in range(len(texte))],
            "character_end_times_seconds": [(i + 1) * pas for i in range(len(texte))]}


# --------------------------------------------------------------------------- fonctions pures

def test_mots_depuis_alignement_simple():
    assert el.mots_depuis_alignement(alignement("ab cd", pas=0.25)) == [Mot("ab", 0.0, 0.5), Mot("cd", 0.75, 1.25)]


def test_mots_depuis_alignement_espaces_multiples_et_bords():
    mots = el.mots_depuis_alignement(alignement("  Hi   there \n you  "))
    assert [m.texte for m in mots] == ["Hi", "there", "you"]
    assert mots[0].debut == pytest.approx(0.2) and mots[0].fin == pytest.approx(0.4)
    assert mots[1].debut == pytest.approx(0.7) and mots[1].fin == pytest.approx(1.2)


def test_mots_depuis_alignement_ponctuation_collee():
    mots = el.mots_depuis_alignement(alignement("Wait, what?! It's 5.2 km."))
    assert [m.texte for m in mots] == ["Wait,", "what?!", "It's", "5.2", "km."]


def test_mots_depuis_alignement_vide():
    assert el.mots_depuis_alignement(alignement("")) == []
    assert el.mots_depuis_alignement(alignement("   ")) == []


@pytest.mark.parametrize("hint, attendu", [
    ("elevenlabs:abc123", "abc123"),
    ("elevenlabs:a:b", "a:b"),
    ("kokoro:af_heart", None),
    ("", None),
    (None, None),
])
def test_voix_depuis_hint(hint, attendu):
    assert el.voix_depuis_hint(hint) == attendu


def test_lire_cle_absente(monkeypatch):
    import keyring

    monkeypatch.undo()  # retire la clé factice de ce module
    monkeypatch.setattr(keyring, "get_password", lambda *a: None)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(el.CleElevenLabsAbsente):
        el.lire_cle()
    monkeypatch.setenv("ELEVENLABS_API_KEY", "  depuis-env \n")
    assert el.lire_cle() == "depuis-env"
    monkeypatch.setattr(keyring, "get_password", lambda *a: "depuis-trousseau")
    assert el.lire_cle() == "depuis-trousseau"


# --------------------------------------------------------------------------- synthetiser

@ffmpeg_requis
def test_synthetiser_ecrit_le_wav_et_les_mots(tmp_path, mp3_1s):
    requetes: list[httpx.Request] = []

    def reponse(req: httpx.Request) -> httpx.Response:
        requetes.append(req)
        return httpx.Response(200, headers={"character-cost": "11", "request-id": "req-42"},
                              json={"audio_base64": base64.b64encode(mp3_1s).decode(),
                                    "alignment": alignement("Hello world")})

    wav = tmp_path / "voix.wav"
    s = el.synthetiser("Hello world", wav, "voix-x", vitesse=1.5, transport=httpx.MockTransport(reponse))
    assert wav.exists() and not wav.with_suffix(".mp3").exists()
    assert s.duree_s == pytest.approx(1.0, abs=0.1)
    assert [m.texte for m in s.mots] == ["Hello", "world"]
    assert s.caracteres == 11 and s.request_id == "req-42"
    import soundfile as sf

    info = sf.info(str(wav))
    assert info.samplerate == 44100 and info.channels == 1
    # Requête envoyée
    (req,) = requetes
    assert req.method == "POST"
    assert req.url.path == "/v1/text-to-speech/voix-x/with-timestamps"
    assert req.url.params["output_format"] == "mp3_44100_128"
    assert req.headers["xi-api-key"] == "cle-de-test"
    corps = json.loads(req.content)
    assert corps["text"] == "Hello world" and corps["model_id"] == el.MODELE
    assert corps["voice_settings"]["speed"] == el.VITESSE_MAX  # 1.5 ramené à 1.2


@ffmpeg_requis
def test_synthetiser_sans_en_tetes_compte_les_caracteres(tmp_path, mp3_1s):
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, json={"audio_base64": base64.b64encode(mp3_1s).decode(), "alignment": alignement("abc")}))
    s = el.synthetiser("abc", tmp_path / "v.wav", "v", vitesse=0.1, transport=transport)
    assert s.caracteres == 3 and s.request_id is None


@pytest.mark.parametrize("code, corps, attendu", [
    (401, {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}, "ElevenLabs 401 : Invalid API key"),
    (402, {"detail": {"status": "payment_required", "message": "Quota exceeded"}}, "ElevenLabs 402 : Quota exceeded"),
    (422, {"detail": "texte trop long"}, "ElevenLabs 422 : texte trop long"),
])
def test_synthetiser_erreurs_api(tmp_path, code, corps, attendu):
    transport = httpx.MockTransport(lambda req: httpx.Response(code, json=corps))
    wav = tmp_path / "v.wav"
    with pytest.raises(el.ErreurElevenLabs) as e:
        el.synthetiser("x", wav, "v", transport=transport)
    assert str(e.value) == attendu
    assert not wav.exists() and not wav.with_suffix(".mp3").exists()


def test_synthetiser_erreur_non_json(tmp_path):
    transport = httpx.MockTransport(lambda req: httpx.Response(503, text="<html>Service Unavailable</html>"))
    with pytest.raises(el.ErreurElevenLabs, match="ElevenLabs 503 : <html>Service Unavailable"):
        el.synthetiser("x", tmp_path / "v.wav", "v", transport=transport)


def test_synthetiser_sans_cle(tmp_path, monkeypatch):
    def absente():
        raise el.CleElevenLabsAbsente("pas de clé")

    monkeypatch.setattr(el, "lire_cle", absente)
    transport = httpx.MockTransport(lambda req: pytest.fail("aucune requête ne doit partir sans clé"))
    with pytest.raises(el.CleElevenLabsAbsente):
        el.synthetiser("x", tmp_path / "v.wav", "v", transport=transport)


# --------------------------------------------------------------------------- quota

def test_quota():
    def reponse(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/user/subscription" and req.headers["xi-api-key"] == "cle-de-test"
        return httpx.Response(200, json={"character_count": 1234, "character_limit": 10000, "tier": "free"})

    assert el.quota(httpx.MockTransport(reponse)) == (1234, 10000)


def test_quota_indisponible(monkeypatch):
    assert el.quota(httpx.MockTransport(lambda req: httpx.Response(401, json={}))) is None
    assert el.quota(httpx.MockTransport(lambda req: httpx.Response(200, text="pas du json"))) is None

    def coupe(req):
        raise httpx.ConnectError("hors ligne", request=req)

    assert el.quota(httpx.MockTransport(coupe)) is None

    def absente():
        raise el.CleElevenLabsAbsente("pas de clé")

    monkeypatch.setattr(el, "lire_cle", absente)
    assert el.quota(httpx.MockTransport(lambda req: httpx.Response(200, json={}))) is None
