"""Bibliothèque des vidéos générées (dossier sorties/) : statuts, validation, publication.

Chaque vidéo vit dans sorties/<horodatage>_<recette>/ avec son journal.json. Statuts :
a_valider → validee | rejetee → publiee (une date par plateforme dans journal["publication"]).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
SORTIES = RACINE / "sorties"
RECETTES = RACINE / "recettes"

# Pages d'envoi ouvertes dans Chrome pour la publication semi-automatique (section 8).
PLATEFORMES = {
    "tiktok": ("TikTok", "https://www.tiktok.com/tiktokstudio/upload"),
    "instagram": ("Instagram Reels", "https://www.instagram.com/"),
    "youtube": ("YouTube Shorts", "https://www.youtube.com/upload"),
}


@dataclass
class Video:
    dossier: Path
    journal: dict = field(repr=False)

    @property
    def id(self) -> str:
        return self.dossier.name

    @property
    def statut(self) -> str:
        return self.journal.get("statut", "inconnu")

    @property
    def recette(self) -> str:
        return self.journal.get("recette", {}).get("recipe_id", "?")

    @property
    def fichier(self) -> Path | None:
        f = self.dossier / "video.mp4"
        return f if f.exists() else None

    @property
    def date(self) -> datetime:
        try:
            return datetime.strptime(self.dossier.name[:15], "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.fromtimestamp(self.dossier.stat().st_mtime, tz=timezone.utc)

    @property
    def titre(self) -> str:
        return self.journal.get("fiche_sujet", {}).get("titre", "")

    @property
    def script(self) -> str:
        f = self.dossier / "script.txt"
        return f.read_text(encoding="utf-8") if f.exists() else ""

    @property
    def legende(self) -> str:
        f = self.dossier / "legende.txt"
        return f.read_text(encoding="utf-8") if f.exists() else ""

    @property
    def duree_s(self) -> float | None:
        return self.journal.get("voix", {}).get("duree_s")

    @property
    def cout_usd(self) -> float:
        return self.journal.get("cout_llm_usd") or 0.0

    @property
    def avertissements(self) -> list[str]:
        return self.journal.get("avertissements_page", [])

    @property
    def publication(self) -> dict:
        """{plateforme: date de publication ISO}."""
        return self.journal.get("publication", {})

    @property
    def brouillons(self) -> dict:
        """{plateforme: {"statut", "le", "details"}} : résultat de l'agent de brouillon."""
        return self.journal.get("brouillons", {})

    @property
    def liens(self) -> dict:
        """{plateforme: URL du post publié}."""
        return self.journal.get("liens", {})

    @property
    def stats(self) -> dict:
        """{plateforme: [relevés datés, du plus ancien au plus récent]}."""
        return self.journal.get("stats", {})

    def derniers_stats(self) -> dict:
        return {p: r[-1] for p, r in self.stats.items() if r}


def charger(dossier: Path) -> Video | None:
    f = dossier / "journal.json"
    if not f.exists():
        return None
    try:
        journal = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return Video(dossier, journal) if isinstance(journal, dict) else None


def lister(statuts: set[str] | None = None) -> list[Video]:
    if not SORTIES.is_dir():
        return []
    videos = [v for d in SORTIES.iterdir() if d.is_dir() and (v := charger(d))]
    if statuts:
        videos = [v for v in videos if v.statut in statuts]
    return sorted(videos, key=lambda v: v.date, reverse=True)


def _ecrire(v: Video, **maj) -> Video:
    v.journal.update(maj)
    (v.dossier / "journal.json").write_text(json.dumps(v.journal, indent=2, ensure_ascii=False, default=str),
                                            encoding="utf-8")
    return v


def changer_statut(v: Video, statut: str) -> Video:
    return _ecrire(v, statut=statut, **{f"{statut}_le": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def marquer_publiee(v: Video, plateforme: str) -> Video:
    pub = dict(v.publication)
    pub[plateforme] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return _ecrire(v, publication=pub, statut="publiee")


def supprimer(v: Video) -> None:
    shutil.rmtree(v.dossier)


def ouvrir_publication(v: Video, plateformes: list[str]) -> list[str]:
    """Semi-automatique : ouvre le dossier de la vidéo et les pages d'envoi dans Chrome.
    L'utilisateur glisse le fichier dans chaque page et colle la légende (déjà copiée)."""
    ouverts = []
    subprocess.Popen(["xdg-open", str(v.dossier)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for p in plateformes:
        nom, url = PLATEFORMES[p]
        subprocess.Popen(["google-chrome", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ouverts.append(nom)
    return ouverts


def stats_par_recette() -> dict[str, dict[str, int]]:
    """Nombre de vidéos par recette et par statut (historique des recettes)."""
    stats: dict[str, dict[str, int]] = {}
    for v in lister():
        s = stats.setdefault(v.recette, {"total": 0})
        s["total"] += 1
        s[v.statut] = s.get(v.statut, 0) + 1
    return stats


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def enregistrer_brouillon(v: Video, plateforme: str, statut: str, details: str = "") -> Video:
    b = dict(v.brouillons)
    b[plateforme] = {"statut": statut, "le": _maintenant(), "details": details}
    return _ecrire(v, brouillons=b)


def enregistrer_lien(v: Video, plateforme: str, url: str, publiee_le: str | None = None) -> Video:
    """Lien du post sur un réseau ; marque aussi la vidéo publiée sur ce réseau."""
    liens = dict(v.liens)
    liens[plateforme] = url.strip()
    pub = dict(v.publication)
    pub.setdefault(plateforme, publiee_le or _maintenant())
    return _ecrire(v, liens=liens, publication=pub, statut="publiee")


CHAMPS_STATS = ("views", "likes", "comments", "shares", "saves", "avg_watch_time_s", "retention_pct",
                "followers_gained")


def ajouter_stats(v: Video, plateforme: str, releve: dict) -> Video:
    """Ajoute un relevé daté (on garde tout l'historique pour suivre l'évolution)."""
    r = {k: releve.get(k) for k in CHAMPS_STATS}
    r["captured_at"] = releve.get("captured_at") or _maintenant()
    stats = {k: list(x) for k, x in v.stats.items()}
    stats.setdefault(plateforme, []).append(r)
    return _ecrire(v, stats=stats)


def audience_par_recette() -> dict[str, dict[str, int]]:
    """Somme des derniers relevés (toutes plateformes) par recette : quelles recettes marchent."""
    res: dict[str, dict[str, int]] = {}
    for v in lister():
        for r in v.derniers_stats().values():
            a = res.setdefault(v.recette, {"views": 0, "likes": 0, "comments": 0, "shares": 0})
            for k in a:
                a[k] += int(r.get(k) or 0)
    return res


def cout_moyen(type_video: str | None = None) -> float | None:
    """Coût Claude moyen mesuré sur les vidéos réussies (toutes, ou d'un type courte/longue)."""
    couts = []
    for v in lister():
        if not v.fichier or not v.cout_usd:
            continue
        lo, hi = v.journal.get("recette", {}).get("contenu", {}).get("target_duration_s", (0, 0))
        if type_video and ("courte" if hi <= 45 else "longue") != type_video:
            continue
        couts.append(v.cout_usd)
    return round(sum(couts) / len(couts), 2) if couts else None
