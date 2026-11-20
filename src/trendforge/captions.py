"""Sous-titres animés mot par mot au format ASS (section 7, étape 7)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel


@dataclass
class Mot:
    texte: str
    debut: float
    fin: float


class Charte(BaseModel):
    """Charte fixe de la chaîne (section 7) : police, couleurs, voix."""

    police: str = "Ubuntu"
    taille: int = 92
    couleur: str = "#FFFFFF"
    accent: str = "#FFD400"
    contour: str = "#000000"
    epaisseur_contour: int = 6
    voix: list[str] = ["af_heart", "am_michael"]


def _ass_couleur(hexa: str) -> str:
    """#RRGGBB -> &H00BBGGRR (ordre ASS)."""
    h = hexa.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, reste = divmod(t, 3600)
    m, s = divmod(reste, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _echapper(txt: str) -> str:
    return txt.replace("\\", "").replace("{", "(").replace("}", ")")


def ecrire_ass(
    mots: list[Mot],
    chemin: Path,
    charte: Charte,
    mots_par_ecran: int = 2,
    position: str = "center",
    largeur: int = 1080,
    hauteur: int = 1920,
) -> Path:
    """Un événement par mot : le groupe courant s'affiche, le mot prononcé passe en couleur d'accent.

    Zone sûre TikTok : on évite le bas (légende, boutons) et la colonne de droite.
    """
    # alignement 5 = centre ; 2 = bas centre. Marges : 140 px à droite pour les boutons TikTok.
    align = 5 if position == "center" else 2
    marge_v = 0 if position == "center" else int(hauteur * 0.30)
    entete = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {largeur}
PlayResY: {hauteur}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Mot,{charte.police},{charte.taille},{_ass_couleur(charte.couleur)},{_ass_couleur(charte.accent)},{_ass_couleur(charte.contour)},&H64000000,-1,0,0,0,100,100,0,0,1,{charte.epaisseur_contour},2,{align},80,140,{marge_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    accent = _ass_couleur(charte.accent)
    lignes = []
    for g in range(0, len(mots), mots_par_ecran):
        groupe = mots[g : g + mots_par_ecran]
        for i, mot in enumerate(groupe):
            fin = groupe[i + 1].debut if i + 1 < len(groupe) else mot.fin
            morceaux = []
            for j, autre in enumerate(groupe):
                t = _echapper(autre.texte.upper())
                morceaux.append(f"{{\\c{accent}}}{t}{{\\r}}" if j == i else t)
            # léger « pop » à l'apparition du groupe
            pop = "{\\fscx108\\fscy108\\t(0,80,\\fscx100\\fscy100)}" if i == 0 else ""
            lignes.append(
                f"Dialogue: 0,{_ts(mot.debut)},{_ts(fin)},Mot,,0,0,0,,{pop}{' '.join(morceaux)}"
            )
    chemin.write_text(entete + "\n".join(lignes) + "\n", encoding="utf-8")
    return chemin
