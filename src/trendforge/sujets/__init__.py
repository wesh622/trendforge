"""Sources de sujets (section 7) : chaque vidéo part d'un fait réel.

Plugins : `idees` (dossier synchronisé), `bluesky`, `google` (Actualités + Trends), `x` (API payante,
plafonnée). La réserve (`reserve`) stocke les fiches, dédoublonne et retire les tendances périmées.
"""

from trendforge.sujets.base import ResultatSource, SourceSujets, collecter_toutes
from trendforge.sujets.reserve import Reserve

__all__ = ["ResultatSource", "SourceSujets", "collecter_toutes", "Reserve"]
