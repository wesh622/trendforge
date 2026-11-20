"""V0, points 3 et 4 : vitesse et mémoire de la voix (Kokoro int8) et de l'horodatage (faster-whisper).

Usage : uv run python bench/bench_voix.py
Chaque étape tourne dans un processus séparé, pour mesurer son propre pic de mémoire.
"""

from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CACHE = RACINE / ".cache" / "bench"

SCRIPT = (
    "My sister banned me from her wedding over a cake. I know how that sounds. "
    "Let me explain. Six months ago, she asked me to bake her wedding cake because I run a small bakery. "
    "I said yes, and I did it for free. Three tiers, lemon and raspberry, exactly what she picked. "
    "Two weeks before the wedding, her fiance's mother called me. She said the cake was too simple "
    "and that a real bakery would be making it instead. Nobody told me. "
    "Then my sister texted me a photo of the new cake. It was my design, copied line by line, "
    "and they wanted me to pay half because it was my idea. I said no. "
    "So she uninvited me from the wedding, and the whole family took her side. "
    "Here's the twist. The bakery they hired called me the day before the wedding. "
    "They couldn't make it in time, and they asked if I could help. "
    "I said I'd do it for my normal price. My sister paid it. "
    "I wasn't at the wedding, but my cake was. So, who's wrong here?"
)


def _etape_voix(q: mp.Queue) -> None:
    import time

    from trendforge.voix import synthetiser
    from trendforge.mesure import mesurer_fonction

    t0 = time.perf_counter()
    duree, m = mesurer_fonction(synthetiser, SCRIPT, CACHE / "voix_kokoro.wav", "af_heart", 1.05)
    q.put({"etape": "voix", "audio_s": round(duree, 1), "secondes": round(m.secondes, 1),
           "temps_reel": round(m.secondes / duree, 2), "pic_mo": round(m.pic_mo),
           "total_avec_import_s": round(time.perf_counter() - t0, 1)})


def _etape_horodatage(q: mp.Queue) -> None:
    from trendforge.voix import horodater
    from trendforge.mesure import mesurer_fonction

    mots, m = mesurer_fonction(horodater, CACHE / "voix_kokoro.wav", SCRIPT)
    attendus = len(SCRIPT.split())
    (CACHE / "mots_kokoro.json").write_text(json.dumps([m_.__dict__ for m_ in mots], ensure_ascii=False))
    q.put({"etape": "horodatage", "mots": len(mots), "mots_attendus": attendus,
           "secondes": round(m.secondes, 1), "pic_mo": round(m.pic_mo)})


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    ctx = mp.get_context("spawn")
    res = []
    for cible in (_etape_voix, _etape_horodatage):
        q = ctx.Queue()
        p = ctx.Process(target=cible, args=(q,))
        p.start()
        p.join()
        r = q.get() if not q.empty() else {"etape": cible.__name__, "erreur": f"code {p.exitcode}"}
        print(json.dumps(r, ensure_ascii=False))
        res.append(r)
    (CACHE / "resultats_voix.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
