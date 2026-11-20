"""V0, point 6 « Étalonnage » : témoin positif des seuils d'empreinte (section 7).

Fabrique avec ffmpeg :
- une « source » de 30 s (1280x720, images et son variés) ;
- des rendus « propres » 1080x1920 (autre contenu, sous-titres, voix et musique synthétiques) ;
- des rendus « truqués » : le même rendu, avec au milieu 5 s de la source (image + son),
  recadrée en 1080x1920 (recadrage central, bandes floues ou zoom), sous-titres et musique
  par-dessus, volume de la source variable.

Vérifie : chaque truqué est détecté (images ET son), aucun propre n'est signalé, puis
affiche les distances observées et la marge par rapport aux seuils.

    uv run python bench/temoin_positif.py            # variantes complètes
    uv run python bench/temoin_positif.py --garder   # garde les vidéos dans .cache/temoin/
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from trendforge import empreinte as E

RACINE = Path(__file__).resolve().parents[1]
DOSSIER = RACINE / ".cache" / "temoin"
POLICE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H, FPS = 1080, 1920, 30
ENC = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "128k", "-threads", "2"]


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-nostdin", *args], check=True)


# --------------------------------------------------------------------------- sons synthétiques
# Hauteurs quasi aléatoires (résidus quadratiques) pour que l'empreinte varie sans se répéter.

def melodie(graine: int, tempo: float, base: float, d: float) -> str:
    n = f"floor(t*{tempo})"
    f = f"{base}*pow(2,mod({n}*{n}*{graine}+{n}*3,19)/12)"
    return f"aevalsrc='0.5*sin(2*PI*t*{f})+0.25*sin(4*PI*t*{f})':s=44100:d={d}"


def son_source(d: float) -> str:
    # mélodie + bruit rose modulé (respiration, « ambiance »)
    return (f"{melodie(7, 4, 220, d)}[m];anoisesrc=d={d}:c=pink:a=0.25:seed=11,"
            f"tremolo=f=0.7:d=0.8[n];[m][n]amix=inputs=2:normalize=0")


def voix(graine: int, d: float) -> str:
    # « voix » : syllabes rapides en hauteur variable, hachées par une enveloppe
    n = "floor(t*6)"
    f = f"(140+12*mod({n}*{n}*{graine},17))"
    return (f"aevalsrc='0.6*sin(2*PI*t*{f})*sin(2*PI*t*{f}*2.01)*gt(sin(2*PI*t*3+{graine}),-0.3)'"
            f":s=44100:d={d}")


# --------------------------------------------------------------------------- vidéos

def fabriquer_source(chemin: Path, d: float = 30.0) -> None:
    t = d / 3
    v = (f"testsrc2=s=1280x720:r={FPS}:d={t}[a];"
         f"mandelbrot=s=320x180:r={FPS}:maxiter=256,trim=duration={t},"
         "scale=1280:720:flags=bicubic,format=yuv420p[b];"
         f"cellauto=s=320x180:r={FPS}:rule=30:random_seed=5,trim=duration={t},scale=1280:720,"
         f"format=yuv420p,hue=h=t*40:s=3[c];"
         "[a][b][c]concat=n=3:v=1:a=0,format=yuv420p[v]")
    ff("-filter_complex", f"{v};{son_source(d)}[s]", "-map", "[v]", "-map", "[s]",
       "-t", str(d), *ENC, str(chemin))


def fond_propre(graine: int, d: float) -> str:
    """Fond « stock » : jeu de la vie coloré + bandes de couleur mobiles (jamais la source)."""
    return (f"life=s=270x480:r={FPS}:mold=10:ratio=0.3:seed={graine}:"
            f"life_color=#ffcc33:death_color=#202040,scale={W}:{H}:flags=neighbor,"
            f"hue=h=t*{15 + graine % 20},trim=duration={d},format=yuv420p")


def sous_titres() -> str:
    mots = ["SHE", "SAID", "NO", "THEN", "THE", "DOOR", "OPENED", "AGAIN"]
    filtres = []
    for i, m in enumerate(mots):
        filtres.append(
            f"drawtext=fontfile={POLICE}:text='{m}':fontsize=120:fontcolor=white:borderw=10:"
            f"bordercolor=black:x=(w-tw)/2:y=h*0.58:enable='eq(mod(floor(t*2),{len(mots)}),{i})'")
    return ",".join(filtres)


@dataclass
class Variante:
    nom: str
    debut_source: float = 12.0  # début de l'extrait dans la source (s)
    position: float = 7.5  # position de l'extrait dans le rendu (s)
    duree: float = 5.0  # durée de l'extrait
    recadrage: str = "crop"  # crop | flou | zoom
    volume_db: float = 0.0  # volume de la source dans le mix
    voix_dessus: bool = False  # la voix continue par-dessus l'extrait
    longueur: float = 20.0  # durée du rendu
    graine: int = 1


def recadrer(mode: str) -> str:
    if mode == "crop":  # recadrage central au format 9:16
        return f"crop=ih*9/16:ih,scale={W}:{H}"
    if mode == "zoom":  # recadrage décentré + zoom 115 %
        return f"crop=ih*9/16/1.15:ih/1.15:iw*0.3:ih*0.05,scale={W}:{H}"
    if mode == "flou":  # source entière au centre, fond flou de la même source
        return (f"split[f][p];[f]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"gblur=sigma=30[f2];[p]scale={W}:-2[p2];[f2][p2]overlay=(W-w)/2:(H-h)/2")
    raise ValueError(mode)


def fabriquer_rendu(chemin: Path, source: Path | None, v: Variante) -> None:
    """Rendu propre (source=None) ou truqué (extrait de la source au milieu)."""
    d, p0, p1 = v.longueur, v.position, v.position + v.duree
    musique = melodie(13 + v.graine, 2, 330, d)
    entrees = ["-f", "lavfi", "-i", fond_propre(v.graine, d),
               "-f", "lavfi", "-i", voix(3 + v.graine, d),
               "-f", "lavfi", "-i", musique]
    if source is None:
        g = (f"[0:v]{sous_titres()}[v];"
             "[1:a]volume=1.0[va];[2:a]volume=0.2[mu];[va][mu]amix=inputs=2:normalize=0[a]")
    else:
        entrees += ["-ss", str(v.debut_source), "-t", str(v.duree), "-i", str(source)]
        couper_voix = "" if v.voix_dessus else f",volume=0:enable='between(t,{p0},{p1})'"
        g = (f"[3:v]{recadrer(v.recadrage)},setpts=PTS-STARTPTS+{p0}/TB[x];"
             f"[0:v][x]overlay=0:0:eof_action=pass:enable='between(t,{p0},{p1})',{sous_titres()}[v];"
             f"[1:a]volume=1.0{couper_voix}[va];[2:a]volume=0.2[mu];"
             f"[3:a]volume={v.volume_db}dB,adelay={int(p0 * 1000)}:all=1,apad[sa];"
             "[va][mu][sa]amix=inputs=3:normalize=0:duration=first[a]")
    ff(*entrees, "-filter_complex", g, "-map", "[v]", "-map", "[a]", "-t", str(d), *ENC, str(chemin))


# --------------------------------------------------------------------------- étalonnage

VARIANTES = [
    Variante("crop-milieu"),
    Variante("crop-debut-source", debut_source=1.0),
    Variante("crop-fin-source", debut_source=24.0),
    Variante("crop-extrait-tot", position=2.0),
    Variante("crop-extrait-tard", position=14.0),
    Variante("flou", recadrage="flou"),
    Variante("zoom", recadrage="zoom", debut_source=6.0),
    Variante("vol-6dB", volume_db=-6),
    Variante("vol-12dB", volume_db=-12, debut_source=17.0),
    Variante("voix-dessus", voix_dessus=True),
    Variante("voix-dessus-vol-6dB-zoom", voix_dessus=True, volume_db=-6, recadrage="zoom"),
    Variante("flou-vol-12dB-voix", recadrage="flou", volume_db=-12, voix_dessus=True, debut_source=20.0),
]
# informatif : limite de détection du son selon la durée de l'extrait
LIMITES = [Variante(f"extrait-{x}s", duree=x, debut_source=8.0) for x in (2.0, 3.0, 4.0)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--garder", action="store_true", help="garder les vidéos dans .cache/temoin/")
    ap.add_argument("--sans-75s", action="store_true", help="sauter la mesure de temps sur 75 s")
    args = ap.parse_args()
    DOSSIER.mkdir(parents=True, exist_ok=True)
    source = DOSSIER / "source.mp4"
    fabriquer_source(source)

    lignes, ok_global = [], True
    propres = [Variante(f"propre-{g}", graine=g) for g in (1, 2, 3)]
    for v in propres:
        f = DOSSIER / f"{v.nom}.mp4"
        fabriquer_rendu(f, None, v)
        r = E.controle_empreinte(f, source)
        lignes.append(("propre", v.nom, r))
        ok_global &= r.ok
    for v in VARIANTES + LIMITES:
        f = DOSSIER / f"truque-{v.nom}.mp4"
        fabriquer_rendu(f, source, v)
        r = E.controle_empreinte(f, source)
        lignes.append(("limite" if v in LIMITES else "truque", v.nom, r))
        if v not in LIMITES:
            ok_global &= (not r.images.ok) and (not r.son.ok)

    print(f"\nSeuils : Hamming <= {E.SEUIL_HAMMING} ; BER <= {E.SEUIL_BER} sur {E.FENETRE_SON} items\n")
    print(f"{'type':7} {'variante':28} {'img dmin':>8} {'n img':>5} {'son BER':>8}  verdict")
    for t, nom, r in lignes:
        attendu = r.ok if t == "propre" else (not r.images.ok and not r.son.ok)
        print(f"{t:7} {nom:28} {str(r.images.distance_min):>8} {len(r.images.correspondances):>5} "
              f"{str(r.son.ber_min):>8}  {'OK' if r.ok else 'ECHEC'}"
              f"{'' if attendu or t == 'limite' else '   <-- inattendu'}")

    tru = [r for t, _, r in lignes if t == "truque"]
    pro = [r for t, _, r in lignes if t == "propre"]
    det_img = sum(not r.images.ok for r in tru)
    det_son = sum(not r.son.ok for r in tru)
    print(f"\nDétection truqués : images {det_img}/{len(tru)}, son {det_son}/{len(tru)} ; "
          f"faux positifs propres : {sum(not r.ok for r in pro)}/{len(pro)}")
    d_tru = max(r.images.distance_min for r in tru)
    d_pro = min(r.images.distance_min for r in pro if r.images.distance_min is not None)
    b_tru = max(r.son.ber_min for r in tru)
    b_pro = min(r.son.ber_min for r in pro if r.son.ber_min is not None)
    print(f"Images : pire truqué dmin={d_tru}, meilleur propre dmin={d_pro} "
          f"(seuil {E.SEUIL_HAMMING} : marge {E.SEUIL_HAMMING - d_tru} / {d_pro - E.SEUIL_HAMMING})")
    print(f"Son    : pire truqué BER={b_tru}, meilleur propre BER={b_pro} "
          f"(seuil {E.SEUIL_BER} : marge {E.SEUIL_BER - b_tru:.3f} / {b_pro - E.SEUIL_BER:.3f})")

    if not args.sans_75s:
        long_ = DOSSIER / "propre-75s.mp4"
        fabriquer_rendu(long_, None, Variante("propre-75s", longueur=75.0, graine=4))
        src75 = DOSSIER / "source-75s.mp4"
        fabriquer_source(src75, 75.0)
        for s in (source, src75):
            t0 = time.perf_counter()
            r = E.controle_empreinte(long_, s)
            print(f"Temps controle_empreinte(rendu 75 s, {s.name}) : {time.perf_counter() - t0:.2f} s "
                  f"(ok={r.ok}, dmin={r.images.distance_min}, BER={r.son.ber_min})")

    if not args.garder:
        shutil.rmtree(DOSSIER)
    print("\nTÉMOIN POSITIF :", "RÉUSSI" if ok_global else "ÉCHOUÉ")
    return 0 if ok_global else 1


if __name__ == "__main__":
    sys.exit(main())
