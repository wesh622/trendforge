"""Modèles de données : recette v3 (section 6 : blocs contenu + visuel) et fiche sujet (section 7)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

SCHEMA_VERSION = 3


class Part(BaseModel):
    part: Literal["hook", "setup", "escalation", "twist", "payoff", "list_item", "cta"]
    seconds: tuple[float, float]
    pattern: str | None = None
    example: str | None = None
    beats: int | None = None

    @model_validator(mode="after")
    def _ordre(self) -> "Part":
        if self.seconds[0] >= self.seconds[1]:
            raise ValueError(f"{self.part}: début >= fin ({self.seconds})")
        return self


class Source(BaseModel):
    url: HttpUrl | None = None
    views: int | None = None
    duration_s: float | None = None
    language: str = "en"


class ScriptStyle(BaseModel):
    pov: Literal["1st_person", "2nd_person", "3rd_person", "narrator"]
    wpm: int = Field(ge=120, le=220)
    reading_level: str = "grade_6"
    tone: str


class Voice(BaseModel):
    gender: Literal["female", "male"]
    age: str
    speed: float = Field(1.0, ge=0.8, le=1.3)
    engine_hint: str | None = None


class Captions(BaseModel):
    style: Literal["word_by_word", "phrase"] = "word_by_word"
    words_on_screen: int = Field(2, ge=1, le=6)
    position: Literal["center", "lower_third"] = "center"
    use_channel_charter: bool = True


class Audio(BaseModel):
    music_mood: str
    music_db: float = Field(-22, le=-10)
    sfx: list[str] = []


class Posting(BaseModel):
    hashtags: list[str] = Field(min_length=3, max_length=5)
    best_hours_utc: list[int] = []


# --------------------------------------------------------------------------- recette v3
# Une recette = un bloc « contenu » (de quoi on parle et comment on le raconte) + un bloc
# « visuel » (à quoi ça ressemble et comment ça sonne). Les deux blocs sont indépendants :
# on peut générer avec le contenu d'une recette et le visuel d'une autre (combiner()).


class Contenu(BaseModel):
    niche: str
    themes: list[str] = Field(min_length=1)
    sources_acceptees: list["SourceType"] = Field(min_length=1)
    angle: str = Field(description="Ce que la vidéo promet au spectateur")
    transformation: str = Field(description="Comment la source réelle est modifiée pour rester originale")
    format: Literal["narration", "texte_ecran"] = "narration"
    language: str = "en"
    target_duration_s: tuple[float, float]
    structure: list[Part] = Field(min_length=2)
    script_style: ScriptStyle
    posting: Posting

    @model_validator(mode="after")
    def _coherence(self) -> "Contenu":
        lo, hi = self.target_duration_s
        if lo >= hi:
            raise ValueError("target_duration_s : min >= max")
        courte = 21 <= lo and hi <= 45
        longue = 61 <= lo and hi <= 90
        if not (courte or longue):
            raise ValueError(
                f"target_duration_s {self.target_duration_s} hors des fourchettes "
                "21-45 s (courte) ou 61-90 s (longue)"
            )
        if self.structure[0].part != "hook":
            raise ValueError("la structure doit commencer par le hook")
        fin = max(p.seconds[1] for p in self.structure)
        if fin > hi:
            raise ValueError(f"la structure finit à {fin} s, après la durée max {hi} s")
        return self

    @property
    def type_video(self) -> Literal["courte", "longue"]:
        return "courte" if self.target_duration_s[1] <= 45 else "longue"

    def mots_cibles(self) -> int:
        """Longueur du script : durée cible médiane × débit (section 7, étape 2)."""
        lo, hi = self.target_duration_s
        return round((lo + hi) / 2 / 60 * self.script_style.wpm)

    def accepte(self, fiche: "FicheSujet") -> bool:
        """Cette fiche sujet peut-elle alimenter ce contenu ?"""
        return fiche.type in self.sources_acceptees


class Rythme(BaseModel):
    changement_s: float = Field(ge=0.8, le=10, description="Un changement visuel toutes les n secondes")
    declencheur: Literal["mots_cles", "temps"] = "mots_cles"
    zoom_punch: bool = False


class Visuel(BaseModel):
    moteur: Literal["html", "stock"] = "html"
    ambiance: str = Field(description="Fond, couleurs, matières, mouvement général")
    fond: str = Field("anime", description="html : 'anime' ; stock : type de fond Pexels (visuels.REQUETES)")
    scene_defaut: str = Field(description="Animation d'une partie que `scenes` ne décrit pas")
    scenes: dict[str, str] = Field(default_factory=dict, description="Animation par partie de la structure")
    rythme: Rythme
    sous_titres: Captions = Captions()
    voix: Voice
    audio: Audio

    @model_validator(mode="after")
    def _parties_connues(self) -> "Visuel":
        connues = set(Part.model_fields["part"].annotation.__args__)
        inconnues = set(self.scenes) - connues
        if inconnues:
            raise ValueError(f"scenes : parties inconnues {sorted(inconnues)} (connues : {sorted(connues)})")
        return self

    def scene_pour(self, part: str) -> str:
        return self.scenes.get(part, self.scene_defaut)


class Recipe(BaseModel):
    schema_version: Literal[3] = SCHEMA_VERSION
    recipe_id: str = Field(pattern=r"^[a-z0-9-]+$")
    source: Source | None = None
    contenu: Contenu
    visuel: Visuel
    why_it_works: str

    @property
    def type_video(self) -> Literal["courte", "longue"]:
        return self.contenu.type_video

    def mots_cibles(self) -> int:
        return self.contenu.mots_cibles()


def combiner(contenu_de: Recipe, visuel_de: Recipe) -> Recipe:
    """Recette mixte : le contenu de l'une, le visuel de l'autre."""
    if contenu_de.recipe_id == visuel_de.recipe_id:
        return contenu_de
    return Recipe(
        recipe_id=f"{contenu_de.recipe_id}--{visuel_de.recipe_id}",
        source=contenu_de.source,
        contenu=contenu_de.contenu,
        visuel=visuel_de.visuel,
        why_it_works=f"Contenu : {contenu_de.why_it_works} Visuel repris de « {visuel_de.recipe_id} ».",
    )


def migrer_v2(d: dict) -> dict:
    """Convertit une recette v2 (champs à plat) en v3. Les champs nouveaux reçoivent des valeurs
    neutres à compléter à la main (themes, angle, transformation, scènes)."""
    if d.get("schema_version") != 2:
        return d
    vis = d["visuals"]
    stock = vis["background"] != "anime"
    return {
        "schema_version": 3,
        "recipe_id": d["recipe_id"],
        "source": d.get("source"),
        "contenu": {
            "niche": d["niche"],
            "themes": [d["niche"]],
            "sources_acceptees": ["forum", "tendance_x", "tendance_bluesky", "google_trends", "actualite"],
            "angle": "à compléter",
            "transformation": "à compléter",
            "format": d.get("format", "narration"),
            "language": d.get("language", "en"),
            "target_duration_s": d["target_duration_s"],
            "structure": d["structure"],
            "script_style": d["script_style"],
            "posting": d["posting"],
        },
        "visuel": {
            "moteur": "stock" if stock else "html",
            "ambiance": "à compléter",
            "fond": vis["background"],
            "scene_defaut": vis.get("overlay") or "à compléter",
            "rythme": {"changement_s": vis["cut_every_s"], "declencheur": "temps",
                       "zoom_punch": vis.get("zoom_punch", False)},
            "sous_titres": d.get("captions", {}),
            "voix": d["voice"],
            "audio": d["audio"],
        },
        "why_it_works": d["why_it_works"],
    }


def charger_recette_dict(d: dict) -> Recipe:
    return Recipe.model_validate(migrer_v2(d))


class SourceType(str, Enum):
    forum = "forum"  # histoire collée à la main (type Reddit)
    tendance_x = "tendance_x"
    tendance_bluesky = "tendance_bluesky"
    google_trends = "google_trends"
    actualite = "actualite"
    tiktok = "tiktok"
    invente = "invente"  # désactivé par défaut


class Reference(BaseModel):
    titre: str
    url: HttpUrl | None = None


class FicheSujet(BaseModel):
    """Point de départ réel d'une vidéo (section 7, « Sources de sujets »)."""

    id: str
    type: SourceType
    url: HttpUrl | None = None
    date_source: datetime
    ajoutee_le: datetime
    titre: str
    resume: str
    personnages: list[str] = []
    conflit: str | None = None
    detail_marquant: str | None = None
    rebondissement: str | None = None
    references: list[Reference] = []  # 2-3 posts ou articles pour une tendance
    texte_source: str | None = None  # gardé pour le contrôle de similarité, jamais envoyé au rédacteur

    @model_validator(mode="after")
    def _regles(self) -> "FicheSujet":
        tendance = self.type in {
            SourceType.tendance_x,
            SourceType.tendance_bluesky,
            SourceType.google_trends,
            SourceType.actualite,
        }
        if tendance and not self.references:
            raise ValueError("une tendance doit citer au moins une source")
        return self

    def est_perimee(self, maintenant: datetime, heures: int = 48) -> bool:
        tendance = self.type not in {SourceType.forum, SourceType.invente}
        return tendance and (maintenant - self.date_source).total_seconds() > heures * 3600


Contenu.model_rebuild()
