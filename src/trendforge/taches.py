"""File des tâches longues lancées depuis l'interface (extraction de recette, génération de vidéo).

Un seul ouvrier traite les tâches l'une après l'autre (profil Léger, section 4 : jamais deux
étapes lourdes en même temps). L'interface lit l'état des tâches toutes les secondes.
"""

from __future__ import annotations

import itertools
import queue
import threading
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

_compteur = itertools.count(1)


@dataclass
class Tache:
    libelle: str
    action: Callable[["Tache"], object]
    id: int = field(default_factory=lambda: next(_compteur))
    etat: str = "en attente"  # en attente | en cours | terminée | échec
    lignes: list[str] = field(default_factory=list)
    resultat: object = None
    erreur: str | None = None
    debut: datetime | None = None
    fin: datetime | None = None

    def noter(self, message: str) -> None:
        self.lignes.append(f"{datetime.now():%H:%M:%S}  {message}")

    @property
    def derniere(self) -> str:
        return self.lignes[-1] if self.lignes else ""


class File:
    def __init__(self) -> None:
        self.taches: list[Tache] = []
        self._q: queue.Queue[Tache] = queue.Queue()
        self._ouvrier = threading.Thread(target=self._boucle, daemon=True)
        self._ouvrier.start()

    def ajouter(self, libelle: str, action: Callable[[Tache], object]) -> Tache:
        t = Tache(libelle, action)
        self.taches.append(t)
        self._q.put(t)
        return t

    def _boucle(self) -> None:
        while True:
            t = self._q.get()
            t.etat, t.debut = "en cours", datetime.now()
            try:
                t.resultat = t.action(t)
                t.etat = "terminée"
            except Exception as e:  # noqa: BLE001 — toute erreur est montrée dans l'interface
                lignes = [x for x in str(e).splitlines() if x.strip()]
                t.etat, t.erreur = "échec", (lignes[0].strip()[:300] if lignes else type(e).__name__)
                t.noter(f"✗ {t.erreur}")
                traceback.print_exc()
            finally:
                t.fin = datetime.now()

    def actives(self) -> list[Tache]:
        return [t for t in self.taches if t.etat in ("en attente", "en cours")]

    def recentes(self, n: int = 8) -> list[Tache]:
        return list(reversed(self.taches[-n:]))


FILE = File()
