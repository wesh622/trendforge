"""Commandes en terminal (V1a : pas encore d'interface graphique, section 9)."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from trendforge.models import Recipe, charger_recette_dict, combiner

app = typer.Typer(help="TrendForge — génération de vidéos à partir de recettes.", no_args_is_help=True)
recette = typer.Typer(help="Recettes (section 6).", no_args_is_help=True)
app.add_typer(recette, name="recette")
console = Console()

RACINE = Path(__file__).resolve().parents[2]
DOSSIER_RECETTES = RACINE / "recettes"


def charger_recette(chemin_ou_id: str) -> Recipe:
    p = Path(chemin_ou_id)
    if not p.exists():
        p = DOSSIER_RECETTES / f"{chemin_ou_id}.json"
    return charger_recette_dict(json.loads(p.read_text(encoding="utf-8")))


def recette_de_generation(contenu: str, visuel: str | None = None) -> Recipe:
    """Recette utilisée pour générer : le contenu d'une recette, le visuel d'une autre si demandé."""
    r = charger_recette(contenu)
    return combiner(r, charger_recette(visuel)) if visuel else r


@recette.command("liste")
def recette_liste() -> None:
    """Liste les recettes du dossier recettes/ et signale celles qui sont invalides."""
    t = Table("id", "type", "durée cible", "mots", "sources", "visuel", "état")
    for f in sorted(DOSSIER_RECETTES.glob("*.json")):
        try:
            r = charger_recette_dict(json.loads(f.read_text(encoding="utf-8")))
            c = r.contenu
            t.add_row(r.recipe_id, r.type_video, f"{c.target_duration_s[0]:.0f}-{c.target_duration_s[1]:.0f} s",
                      str(r.mots_cibles()), ", ".join(s.value for s in c.sources_acceptees),
                      r.visuel.moteur, "[green]valide[/]")
        except (ValidationError, json.JSONDecodeError) as e:
            t.add_row(f.stem, "-", "-", "-", "-", "-", f"[red]invalide[/] ({str(e).splitlines()[0]})")
    console.print(t)


@recette.command("valider")
def recette_valider(fichier: Path) -> None:
    """Valide une recette JSON et affiche les champs en faute."""
    try:
        r = charger_recette_dict(json.loads(fichier.read_text(encoding="utf-8")))
    except ValidationError as e:
        for err in e.errors():
            console.print(f"[red]✗[/] {'.'.join(map(str, err['loc']))} : {err['msg']}")
        raise typer.Exit(1)
    console.print(f"[green]✓[/] {r.recipe_id} : {r.type_video}, {r.mots_cibles()} mots visés")


@recette.command("combiner")
def recette_combiner(
    contenu: str = typer.Argument(..., help="Recette dont on garde le contenu (thèmes, structure, ton)."),
    visuel: str = typer.Argument(..., help="Recette dont on garde le visuel (animations, voix, son)."),
    enregistrer: bool = typer.Option(False, "--enregistrer", help="Écrire la recette mixte dans recettes/."),
) -> None:
    """Montre (et enregistre au besoin) la recette mixte : contenu de l'une, visuel de l'autre."""
    r = recette_de_generation(contenu, visuel)
    console.print(f"[bold]{r.recipe_id}[/] : {r.type_video}, {r.mots_cibles()} mots, "
                  f"sources {', '.join(s.value for s in r.contenu.sources_acceptees)}")
    console.print(f"  contenu : {r.contenu.angle}")
    console.print(f"  visuel  : {r.visuel.ambiance}")
    for p in r.contenu.structure:
        console.print(f"  [dim]{p.part:<10}[/] {r.visuel.scene_pour(p.part)}")
    if enregistrer:
        f = DOSSIER_RECETTES / f"{r.recipe_id}.json"
        f.write_text(r.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        console.print(f"[green]✓[/] enregistrée dans {f.relative_to(RACINE)}")


@app.command("generer")
def generer(
    contenu: str = typer.Argument(..., help="Recette dont on prend le contenu (et le visuel, sauf --visuel)."),
    visuel: str = typer.Option(None, "--visuel", help="Recette dont on prend le visuel."),
    sujet: int = typer.Option(1, "--sujet", help="Numéro de la fiche parmi celles que la recette accepte."),
    graine: int = typer.Option(None, help="Graine du hasard (choix de musique)."),
) -> None:
    """Génère une vidéo : fiche sujet de la réserve + recette (contenu et visuel)."""
    from trendforge.pipeline import generer as lancer
    from trendforge.sujets import Reserve

    r = recette_de_generation(contenu, visuel)
    fiches = [f for f in Reserve(DOSSIER_RESERVE).selection() if r.contenu.accepte(f)]
    if not fiches:
        console.print(f"[red]Aucune fiche en réserve pour les sources {[s.value for s in r.contenu.sources_acceptees]}.[/]")
        raise typer.Exit(1)
    if not 1 <= sujet <= len(fiches):
        console.print(f"[red]--sujet doit être entre 1 et {len(fiches)}.[/]")
        raise typer.Exit(1)
    fiche = fiches[sujet - 1]
    console.print(f"Recette [bold]{r.recipe_id}[/], sujet : {fiche.titre}")
    dossier = lancer(r, fiche, graine=graine)
    j = json.loads((dossier / "journal.json").read_text())
    console.print(f"[green]✓[/] {dossier.relative_to(RACINE)}/video.mp4 — coût LLM {j.get('cout_llm_usd')} $, "
                  f"voix {j['voix'].get('caracteres', '-')} caractères")


@app.command("interface")
def interface(
    sans_fenetre: bool = typer.Option(False, "--sans-fenetre", help="Ne pas ouvrir la fenêtre Chrome."),
    port: int = typer.Option(8765, help="Port local de l'interface."),
) -> None:
    """Ouvre l'interface graphique (recettes, génération, vidéos à publier, sujets)."""
    from trendforge.interface import lancer

    console.print(f"Interface sur http://127.0.0.1:{port} (Ctrl+C pour arrêter)")
    lancer(fenetre=not sans_fenetre, port=port)


# --- Sources de sujets (section 7) ----------------------------------------------------

sujets = typer.Typer(help="Sources de sujets et réserve de fiches (section 7).", no_args_is_help=True)
app.add_typer(sujets, name="sujets")
DOSSIER_IDEES = RACINE / "idees"
DOSSIER_RESERVE = RACINE / "reserve"


def _afficher_resultats(resultats: list, stats: dict | None = None) -> None:
    t = Table("source", "état", "détail")
    couleurs = {"ok": "green", "desactivee": "yellow", "erreur": "red"}
    for r in resultats:
        t.add_row(r.nom, f"[{couleurs[r.statut]}]{r.statut}[/]", r.message)
    console.print(t)
    if stats is not None:
        console.print(f"Réserve : {stats['ajoutees']} ajoutée(s), {stats['doublons']} doublon(s), "
                      f"{stats['perimees']} périmée(s) écartée(s).")


@sujets.command("importer")
def sujets_importer(dossier: Path = typer.Option(DOSSIER_IDEES, help="Dossier idees/ synchronisé.")) -> None:
    """Lit idees/ (liens, textes collés, raccourcis .url) et range les fiches dans la réserve."""
    from trendforge.sujets import Reserve, collecter_toutes
    from trendforge.sujets.idees import SourceIdees

    dossier.mkdir(parents=True, exist_ok=True)
    source = SourceIdees(dossier)
    resultats = collecter_toutes([source])
    fiches = [f for r in resultats for f in r.fiches]
    stats = Reserve(DOSSIER_RESERVE).ajouter(fiches)
    deplaces = source.archiver()
    _afficher_resultats(resultats, stats)
    for f, err in source.erreurs:
        console.print(f"[red]✗[/] {f.name} : {err} (laissé dans {dossier.name}/)")
    console.print(f"{len(deplaces)} fichier(s) déplacé(s) dans {dossier.name}/traitees/.")


@sujets.command("tendances")
def sujets_tendances(
    limite: int = typer.Option(10, help="Nombre maximum de sujets par source."),
    sans_x: bool = typer.Option(False, "--sans-x", help="Ne pas interroger X même si un jeton est présent."),
) -> None:
    """Interroge Bluesky et Google (Trends + Actualités), et X si X_BEARER_TOKEN est défini."""
    from trendforge.sujets import Reserve, collecter_toutes
    from trendforge.sujets.bluesky import SourceBluesky
    from trendforge.sujets.google import SourceGoogleActualites, SourceGoogleTrends
    from trendforge.sujets.x import SourceX

    sources = [SourceBluesky(limite=limite), SourceGoogleTrends(limite=limite),
               SourceGoogleActualites(limite=limite)]
    if not sans_x:
        sources.append(SourceX(DOSSIER_RESERVE / "x_depenses.json", limite=limite))
    reserve = Reserve(DOSSIER_RESERVE)
    retirees = reserve.purger()
    from trendforge.sujets.moderation import ecarter, raisons

    resultats = collecter_toutes(sources)
    toutes = [f for r in resultats for f in r.fiches]
    gardees = [f for f in toutes if not ecarter(f)]
    stats = reserve.ajouter(gardees)
    _afficher_resultats(resultats, stats)
    ecartees = [f for f in toutes if ecarter(f)]
    if ecartees:
        console.print(f"[yellow]{len(ecartees)} sujet(s) sensible(s) écarté(s) par la modération :[/]")
        for f in ecartees:
            console.print(f"[dim]  • {f.titre} ({', '.join(raisons(f))})[/]")
    for s in sources:
        for note in getattr(s, "notes", []):
            console.print(f"[dim]{s.nom} : {note}[/]")
    if retirees:
        console.print(f"{len(retirees)} tendance(s) de plus de 48 h retirée(s) au passage.")


@sujets.command("liste")
def sujets_liste(
    references: bool = typer.Option(False, "--references", "-r", help="Afficher aussi les sources citées."),
) -> None:
    """Affiche la réserve dans l'ordre de sélection (tendances fraîches, puis histoires collées)."""
    from trendforge.sujets import Reserve
    from trendforge.sujets.base import maintenant

    fiches = Reserve(DOSSIER_RESERVE).selection()
    t = Table("#", "type", "date source", "âge", "titre", "réf.", show_lines=references)
    now = maintenant()
    for i, f in enumerate(fiches, 1):
        age_h = (now - f.date_source).total_seconds() / 3600
        titre = f.titre if not references else "\n".join(
            [f"[bold]{f.titre}[/]", f.resume] + [f"  • {r.titre} {r.url or ''}" for r in f.references])
        t.add_row(str(i), f.type.value, f.date_source.strftime("%Y-%m-%d %H:%M"),
                  f"{age_h:.0f} h" if age_h < 72 else f"{age_h / 24:.0f} j", titre, str(len(f.references)))
    console.print(t)
    console.print(f"{len(fiches)} fiche(s) en réserve.")


@sujets.command("purger")
def sujets_purger() -> None:
    """Retire de la réserve les tendances de plus de 48 h (les histoires collées restent)."""
    from trendforge.sujets import Reserve

    retirees = Reserve(DOSSIER_RESERVE).purger()
    for f in retirees:
        console.print(f"[dim]retirée[/] {f.type.value} : {f.titre}")
    console.print(f"{len(retirees)} fiche(s) retirée(s).")


if __name__ == "__main__":
    app()
