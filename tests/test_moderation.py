from datetime import datetime, timezone

from trendforge.models import FicheSujet, Reference, SourceType
from trendforge.sujets.moderation import ecarter, raisons

NOW = datetime.now(timezone.utc)


def fiche(titre, type_=SourceType.actualite, resume="r"):
    return FicheSujet(id=titre, type=type_, date_source=NOW, ajoutee_le=NOW, titre=titre, resume=resume,
                      references=[Reference(titre="ref")])


def test_ecarte_politique_et_deces():
    assert "politique" in raisons(fiche("Trump says something"))
    assert "deces" in raisons(fiche("Death of Fiona the hippo"))
    assert ecarter(fiche("Senate votes on war powers"))


def test_garde_sujet_leger():
    assert not ecarter(fiche("Nintendo Wii turns 20"))
    assert not ecarter(fiche("Names parents almost chose", SourceType.tendance_bluesky))


def test_histoire_collee_non_filtree():
    f = FicheSujet(id="h", type=SourceType.forum, date_source=NOW, ajoutee_le=NOW,
                   titre="My sister died laughing at my cake", resume="r")
    assert not ecarter(f)
