"""V0, point 2 : rendu d'une vidéo de 75 s, FFmpeg seul (3 encodeurs) contre MoviePy.

Usage : uv run python bench/bench_rendu.py [--sans-moviepy] [--repetitions N]
Les fonds, la voix et la musique sont synthétiques : on mesure la machine, pas le contenu.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
from pathlib import Path

from trendforge.captions import Charte, Mot, ecrire_ass
from trendforge.mesure import Mesure, mesurer_commande, mesurer_fonction
from trendforge.render import Rendu, construire_commande, decouper

RACINE = Path(__file__).resolve().parent.parent
CACHE = RACINE / ".cache" / "bench"
DUREE = 75.0
WPM = 175
COUPE = 4.0


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def preparer() -> tuple[list[tuple[Path, float]], Path, Path, list[Mot]]:
    CACHE.mkdir(parents=True, exist_ok=True)
    fonds = []
    sources = ["testsrc2", "mandelbrot", "life=s=320x180:mold=10:ratio=0.1:death_color=#C83232:life_color=#00ff00", "cellauto=s=320x180"]
    for i, src in enumerate(sources):
        f = CACHE / f"fond{i}.mp4"
        if not f.exists():
            ff("-f", "lavfi", "-i", f"{src}" if "=" in src else f"{src}=s=1920x1080:r=30",
               "-t", "25", "-vf", "scale=1920:1080,format=yuv420p,fps=30",
               "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", str(f))
        fonds.append((f, 25.0))
    voix = CACHE / "voix.wav"
    if not voix.exists():
        # « voix » : tonalité modulée, 24 kHz mono comme Kokoro
        ff("-f", "lavfi", "-i", f"sine=f=220:d={DUREE},volume='0.6*(0.5+0.5*sin(2*PI*3*t))':eval=frame",
           "-ar", "24000", "-ac", "1", str(voix))
    musique = CACHE / "musique.wav"
    if not musique.exists():
        ff("-f", "lavfi", "-i", "anoisesrc=d=30:c=pink:a=0.3", "-af", "lowpass=f=800",
           "-ar", "44100", "-ac", "2", str(musique))
    n = round(DUREE / 60 * WPM)
    pas = DUREE / n
    rnd = random.Random(1)
    vocab = "my sister banned me from her wedding because of a cake and nobody believed what happened next".split()
    mots = [Mot(rnd.choice(vocab), i * pas, i * pas + pas * 0.9) for i in range(n)]
    return fonds, voix, musique, mots


def probe(f: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,width,height,r_frame_rate",
         "-of", "json", str(f)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def rendu_moviepy(fonds, voix, musique, mots, sortie: Path) -> None:
    from moviepy import AudioFileClip, CompositeAudioClip, CompositeVideoClip, TextClip, VideoFileClip, concatenate_videoclips
    from moviepy.audio.fx import AudioLoop, MultiplyVolume

    plans = decouper(fonds, DUREE, COUPE)
    clips = []
    for k, p in enumerate(plans):
        c = VideoFileClip(str(p.fichier)).subclipped(p.debut, p.debut + p.duree)
        c = c.resized(height=int(1920 * 1.15))
        excedent = c.w - 1080
        sens = 1 if k % 2 == 0 else -1
        c = c.cropped(x_center=c.w / 2, y_center=c.h / 2, width=1080 + excedent, height=1920)
        c = c.with_position(lambda t, e=excedent, d=p.duree, s=sens: (-(e * (t / d if s > 0 else 1 - t / d)), 0))
        clips.append(CompositeVideoClip([c], size=(1080, 1920)).with_duration(p.duree))
    fond = concatenate_videoclips(clips)
    police = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    textes = []
    for g in range(0, len(mots), 2):
        groupe = mots[g:g + 2]
        txt = " ".join(m.texte.upper() for m in groupe)
        tc = (TextClip(font=police, text=txt, font_size=92, color="white", stroke_color="black", stroke_width=6, method="label")
              .with_start(groupe[0].debut).with_end(groupe[-1].fin).with_position("center"))
        textes.append(tc)
    video = CompositeVideoClip([fond, *textes], size=(1080, 1920))
    a_voix = AudioFileClip(str(voix))
    a_mus = AudioFileClip(str(musique)).with_effects([AudioLoop(duration=DUREE), MultiplyVolume(10 ** (-22 / 20))])
    video = video.with_audio(CompositeAudioClip([a_voix, a_mus])).with_duration(DUREE)
    video.write_videofile(str(sortie), fps=30, codec="libx264", preset="veryfast", bitrate="8M",
                          audio_codec="aac", logger=None, threads=8)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sans-moviepy", action="store_true")
    ap.add_argument("--repetitions", type=int, default=2)
    args = ap.parse_args()

    fonds, voix, musique, mots = preparer()
    ass = ecrire_ass(mots, CACHE / "sous-titres.ass", Charte(), mots_par_ecran=2)
    plans = decouper(fonds, DUREE, COUPE)
    resultats: dict[str, dict] = {}

    for enc in ["libx264", "h264_qsv", "h264_vaapi"]:
        sortie = CACHE / f"rendu_{enc}.mp4"
        r = Rendu(plans=plans, voix=voix, ass=ass, sortie=sortie, musique=musique, encodeur=enc)
        mesures: list[Mesure] = []
        for _ in range(args.repetitions):
            m = mesurer_commande(construire_commande(r))
            mesures.append(m)
            if m.code != 0:
                break
        ok = all(m.code == 0 for m in mesures)
        resultats[enc] = {
            "ok": ok,
            "secondes": [round(m.secondes, 1) for m in mesures],
            "pic_mo": round(max(m.pic_mo for m in mesures)),
            "erreur": "" if ok else mesures[-1].erreur.strip().splitlines()[-3:],
            "sortie": probe(sortie) if ok else None,
        }
        print(enc, json.dumps({k: v for k, v in resultats[enc].items() if k != "sortie"}, ensure_ascii=False))

    if not args.sans_moviepy:
        sortie = CACHE / "rendu_moviepy.mp4"
        try:
            _, m = mesurer_fonction(rendu_moviepy, fonds, voix, musique, mots, sortie)
            resultats["moviepy"] = {"ok": True, "secondes": [round(m.secondes, 1)], "pic_mo": round(m.pic_mo),
                                    "sortie": probe(sortie)}
        except Exception as e:  # noqa: BLE001 — on veut le résultat de la mesure, même en échec
            resultats["moviepy"] = {"ok": False, "erreur": repr(e)[:500]}
        print("moviepy", json.dumps({k: v for k, v in resultats["moviepy"].items() if k != "sortie"}, ensure_ascii=False))

    ref = [v for k, v in resultats.items() if k == "libx264" and v["ok"]]
    if ref and resultats.get("moviepy", {}).get("ok"):
        ratio = resultats["moviepy"]["secondes"][0] / statistics.median(ref[0]["secondes"])
        resultats["ratio_moviepy_sur_ffmpeg"] = round(ratio, 2)
        print("ratio MoviePy / FFmpeg libx264 :", round(ratio, 2))
    (CACHE / "resultats_rendu.json").write_text(json.dumps(resultats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
