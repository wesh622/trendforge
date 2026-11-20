"""Source « idées » : le dossier `idees/` synchronisé par Syncthing depuis le téléphone.

Formats acceptés :
- `.txt` / `.md` : un lien seul, un texte collé, ou un lien + texte ;
- `.url` : raccourci Windows/Internet (`[InternetShortcut]` / `URL=...`).

L'application ne télécharge JAMAIS la page pointée (Reddit ou autre forum) : on garde
l'URL et le texte collé par l'utilisateur. Les fichiers traités vont dans `idees/traitees/`.
"""

from __future__ import annotations

import configparser
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from trendforge.models import FicheSujet, SourceType
from trendforge.sujets.base import (
    ReducteurFiche,
    SourceSujets,
    id_fiche,
    maintenant,
    phrases,
    reducteur_identite,
)

log = logging.getLogger(__name__)

EXTENSIONS = {".txt", ".md", ".url"}
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
DATE_ISO_RE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)(?:[ T](\d\d):(\d\d))?")
DATE_FR_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b")
MOIS_EN = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_EN_RE = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2}),? (20\d\d)\b", re.I)


def _ignorer(p: Path) -> bool:
    # fichiers temporaires Syncthing, fichiers cachés, conflits en cours d'écriture
    n = p.name
    return n.startswith(".") or n.startswith("~") or ".syncthing." in n or n.endswith(".tmp")


def lire_raccourci_url(texte: str) -> str | None:
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(texte)
        return cp.get("InternetShortcut", "URL", fallback=None)
    except configparser.Error:
        m = URL_RE.search(texte)
        return m.group(0) if m else None


def separer_lien_texte(contenu: str) -> tuple[str | None, str]:
    """Premier lien trouvé + texte collé (contenu sans les lignes qui ne sont qu'un lien)."""
    urls = URL_RE.findall(contenu)
    url = urls[0].rstrip(".,;") if urls else None
    lignes = [l for l in contenu.splitlines() if not URL_RE.fullmatch(l.strip().strip("<>"))]
    texte = "\n".join(lignes).strip()
    return url, texte


def date_dans_texte(texte: str) -> datetime | None:
    """Date explicite écrite dans le texte collé (ISO, JJ/MM/AAAA, « Nov 3, 2026 »)."""
    try:
        if m := DATE_ISO_RE.search(texte):
            a, mo, j, h, mi = m.groups()
            return datetime(int(a), int(mo), int(j), int(h or 0), int(mi or 0), tzinfo=timezone.utc)
        if m := DATE_FR_RE.search(texte):
            j, mo, a = m.groups()
            return datetime(int(a), int(mo), int(j), tzinfo=timezone.utc)
        if m := DATE_EN_RE.search(texte):
            mo, j, a = m.groups()
            return datetime(int(a), MOIS_EN[mo[:3].lower()], int(j), tzinfo=timezone.utc)
    except ValueError:
        return None
    return None


def titre_depuis_url(url: str) -> str:
    """Titre provisoire tiré du lien (slug Reddit `/comments/<id>/<slug>/`, sinon dernier segment)."""
    u = urlparse(url)
    segs = [s for s in u.path.split("/") if s]
    if "comments" in segs and len(segs) > segs.index("comments") + 2:
        slug = segs[segs.index("comments") + 2]
    else:
        slug = segs[-1] if segs else u.netloc
    slug = re.sub(r"\.\w{2,5}$", "", unquote(slug))
    mots = re.sub(r"[_\-+]+", " ", slug).strip()
    return (mots[:1].upper() + mots[1:]) if mots else u.netloc


def titre_depuis_texte(texte: str) -> str:
    premiere = next((l.strip() for l in texte.splitlines() if l.strip()), "")
    premiere = re.sub(r"^[#>*\-\s]+", "", premiere).strip()  # markdown
    return phrases(premiere or texte, n=1, max_car=120)


def fiche_depuis_fichier(chemin: Path, ajoutee_le: datetime | None = None) -> FicheSujet:
    brut = chemin.read_text(encoding="utf-8", errors="replace").lstrip("﻿")
    if chemin.suffix.lower() == ".url":
        url, texte = lire_raccourci_url(brut), ""
    else:
        url, texte = separer_lien_texte(brut)
    if not url and not texte:
        raise ValueError("fichier vide")

    mtime = datetime.fromtimestamp(chemin.stat().st_mtime, tz=timezone.utc)
    date_source = date_dans_texte(texte) or mtime
    titre = titre_depuis_texte(texte) if texte else titre_depuis_url(url or "")
    resume = phrases(re.sub(r"(?m)^[#>]+\s*", "", texte), n=2) if texte else f"Lien seul, texte à coller : {url}"
    return FicheSujet(
        id=id_fiche(SourceType.forum, url or texte[:500]),
        type=SourceType.forum,
        url=url,
        date_source=date_source,
        ajoutee_le=ajoutee_le or maintenant(),
        titre=titre,
        resume=resume,
        texte_source=texte or None,
    )


def _destination_libre(dossier: Path, nom: str) -> Path:
    cible = dossier / nom
    i = 1
    while cible.exists():
        cible = dossier / f"{Path(nom).stem}-{i}{Path(nom).suffix}"
        i += 1
    return cible


class SourceIdees(SourceSujets):
    nom = "idees"

    def __init__(self, dossier: Path, reducteur: ReducteurFiche = reducteur_identite) -> None:
        self.dossier = Path(dossier)
        self.reducteur = reducteur
        self.erreurs: list[tuple[Path, str]] = []
        self.lus: list[Path] = []

    @property
    def traitees(self) -> Path:
        return self.dossier / "traitees"

    def disponible(self) -> tuple[bool, str]:
        if not self.dossier.is_dir():
            return False, f"dossier {self.dossier} absent"
        return True, ""

    def fichiers(self) -> list[Path]:
        return sorted(p for p in self.dossier.iterdir()
                      if p.is_file() and p.suffix.lower() in EXTENSIONS and not _ignorer(p))

    def collecter(self) -> list[FicheSujet]:
        """Lit les fichiers sans les déplacer : appeler `archiver()` une fois la réserve enregistrée."""
        fiches = []
        self.erreurs, self.lus = [], []
        for f in self.fichiers():
            try:
                fiche = self.reducteur(fiche_depuis_fichier(f))
            except (ValueError, ValidationError, OSError) as e:
                # le fichier reste dans idees/ pour correction à la main
                self.erreurs.append((f, str(e).splitlines()[0]))
                log.warning("idée %s ignorée : %s", f.name, e)
                continue
            fiches.append(fiche)
            self.lus.append(f)
        return fiches

    def archiver(self) -> list[Path]:
        """Déplace les fichiers lus avec succès vers idees/traitees/."""
        deplaces = []
        if self.lus:
            self.traitees.mkdir(exist_ok=True)
        for f in self.lus:
            if f.exists():
                cible = _destination_libre(self.traitees, f.name)
                shutil.move(str(f), cible)
                deplaces.append(cible)
        self.lus = []
        return deplaces
