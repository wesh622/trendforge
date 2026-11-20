"""Interface graphique (section 10) : application web locale NiceGUI, ouverte dans une fenêtre Chrome.

    uv run trendforge interface

Onglets : Recettes (historique, extraction depuis un lien TikTok ou un .mp4), Générer (automatique
ou personnalisé), À publier (lecture, validation, publication semi-automatique), Sujets (réserve).
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from nicegui import app, ui
from pydantic import ValidationError

from trendforge import bibliotheque as bib
from trendforge.models import FicheSujet, Recipe, charger_recette_dict, combiner
from trendforge.taches import FILE, Tache

RACINE = Path(__file__).resolve().parents[2]
RECETTES = RACINE / "recettes"
ARCHIVE_RECETTES = RECETTES / ".archive"
RESERVE = RACINE / "reserve"
IDEES = RACINE / "idees"
IMPORTS = RACINE / ".cache" / "imports"
PORT = 8765

STATUTS = {"a_valider": ("À valider", "orange"), "validee": ("Validée", "green"),
           "publiee": ("Publiée", "blue"), "rejetee": ("Rejetée", "grey"),
           "echec_duree": ("Échec durée", "red"), "echec_page": ("Échec page", "red")}


# --------------------------------------------------------------------------- données


def recettes() -> tuple[list[tuple[Recipe, dict, Path]], list[tuple[Path, str]]]:
    """Recettes valides (recette, données brutes, fichier), plus les fichiers invalides."""
    ok, ko = [], []
    for f in RECETTES.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            ok.append((charger_recette_dict(d), d, f))
        except (ValidationError, json.JSONDecodeError, KeyError) as e:
            ko.append((f, str(e).splitlines()[0]))

    def date(x):
        d = x[1].get("extraite_le")
        return d or datetime.fromtimestamp(x[2].stat().st_mtime, tz=timezone.utc).isoformat()
    return sorted(ok, key=date, reverse=True), ko


def recette(rid: str) -> Recipe:
    return charger_recette_dict(json.loads((RECETTES / f"{rid}.json").read_text(encoding="utf-8")))


def reserve():
    from trendforge.sujets import Reserve

    return Reserve(RESERVE)


def fiches_utilisees() -> set[str]:
    return {v.journal.get("fiche_sujet", {}).get("id") for v in bib.lister()}


def fiches_pour(r: Recipe, seulement_neuves: bool = True) -> list[FicheSujet]:
    utilisees = fiches_utilisees() if seulement_neuves else set()
    return [f for f in reserve().selection() if r.contenu.accepte(f) and f.id not in utilisees]


def estimation(r: Recipe) -> str:
    from trendforge.scripts import mots_cibles

    car = mots_cibles(r) * 6
    mesure = bib.cout_moyen(r.type_video)
    cout = (f"≈ {mesure:.2f} $ de Claude (moyenne mesurée)".replace(".", ",") if mesure
            else "≈ 0,40 $ de Claude (estimation)")
    return f"{cout} et ≈ {car} caractères ElevenLabs ({r.type_video}, {mots_cibles(r)} mots)"


ETATS_BROUILLON = {"draft_saved": ("brouillon enregistré", "green"),
                   "ready_to_publish": ("prêt, à publier", "teal"),
                   "needs_login": ("connexion requise", "orange"),
                   "failed": ("échec", "red"), "en_cours": ("en cours…", "grey")}


def _n(x) -> str:
    return "?" if x is None else f"{int(x):,}".replace(",", " ")


def resume_stats(st: dict) -> str:
    morceaux = [f"{_n(st.get('views'))} vues", f"{_n(st.get('likes'))} likes",
                f"{_n(st.get('comments'))} comm.", f"{_n(st.get('shares'))} partages"]
    if st.get("retention_pct") is not None:
        morceaux.append(f"rétention {st['retention_pct']:.0f} %")
    if st.get("avg_watch_time_s") is not None:
        morceaux.append(f"{st['avg_watch_time_s']:.1f} s vues en moyenne")
    return " · ".join(morceaux)


def raison_sans_video(v: bib.Video) -> str:
    """Explication lisible quand une vidéo n'a pas été montée."""
    if v.statut == "echec_duree":
        cible = v.journal.get("recette", {}).get("contenu", {}).get("target_duration_s") or []
        fourchette = f" (cible {cible[0]:.0f}-{cible[1]:.0f} s)" if len(cible) == 2 else ""
        return f"Voix de {v.duree_s or 0:.0f} s hors de la durée visée{fourchette} : vidéo non montée."
    if v.statut == "echec_page":
        return "La page animée n'a pas passé les contrôles : vidéo non montée."
    return "Pas de fichier video.mp4 dans ce dossier."


# --------------------------------------------------------------------------- tâches


def tache_generation(r: Recipe, fiche: FicheSujet, consignes: str | None = None,
                     script_impose: str | None = None) -> Tache:
    from trendforge.pipeline import generer

    def action(t: Tache):
        t.noter(f"Sujet : {fiche.titre}")
        d = generer(r, fiche, consignes=consignes or None, script_impose=script_impose or None,
                    progression=t.noter)
        j = json.loads((d / "journal.json").read_text())
        t.noter(f"✓ Vidéo prête ({j.get('cout_llm_usd')} $, {j.get('voix', {}).get('caracteres', '?')} caractères) "
                "— onglet « À publier »")
        return d
    return FILE.ajouter(f"Vidéo « {r.recipe_id} » — {fiche.titre[:50]}", action)


def _sortie(r: dict) -> tuple[dict | None, str | None]:
    """Résultat d'un réseau renvoyé par publication_agent : (sortie structurée, erreur)."""
    if "erreur" in r:
        return None, r["erreur"]
    return r.get("sortie") or {}, None


def tache_brouillons(v: bib.Video, plateformes: list[str]) -> Tache:
    def action(t: Tache):
        from trendforge import publication_agent as pa

        res = pa.mettre_en_brouillon(v.dossier, plateformes, progression=t.noter)
        cout = 0.0
        for p, r in res.items():
            sortie, err = _sortie(r)
            cout += r.get("cout_usd") or 0
            statut = "failed" if err else sortie.get("status", "failed")
            bib.enregistrer_brouillon(bib.charger(v.dossier), p, statut, err or sortie.get("details") or "")
            if sortie and sortie.get("post_url"):
                bib.enregistrer_lien(bib.charger(v.dossier), p, sortie["post_url"])
            t.noter(f"{bib.PLATEFORMES[p][0]} : {ETATS_BROUILLON.get(statut, (statut,))[0]}"
                    + (f" ({err})" if err else ""))
        t.noter(f"Coût estimé de Claude Code : {cout:.2f} $ (sur ton abonnement)")
        return res
    noms = ", ".join(bib.PLATEFORMES[p][0] for p in plateformes)
    return FILE.ajouter(f"Brouillons {noms} — {v.titre[:40]}", action)


def tache_liens(v: bib.Video) -> Tache:
    def action(t: Tache):
        from trendforge import publication_agent as pa

        res = pa.retrouver_liens(v.dossier, list(bib.PLATEFORMES), progression=t.noter)
        for p, r in res.items():
            sortie, err = _sortie(r)
            if sortie and sortie.get("post_url"):
                bib.enregistrer_lien(bib.charger(v.dossier), p, sortie["post_url"], sortie.get("published_at"))
                t.noter(f"{bib.PLATEFORMES[p][0]} : {sortie['post_url']}")
            else:
                t.noter(f"{bib.PLATEFORMES[p][0]} : post non trouvé" + (f" ({err})" if err else ""))
        return res
    return FILE.ajouter(f"Liens des posts — {v.titre[:40]}", action)


def tache_stats(v: bib.Video) -> Tache:
    def action(t: Tache):
        from trendforge import publication_agent as pa

        res = pa.relever_stats(dict(v.liens), progression=t.noter)
        for p, r in res.items():
            sortie, err = _sortie(r)
            if sortie and sortie.get("views") is not None:
                bib.ajouter_stats(bib.charger(v.dossier), p, sortie)
                t.noter(f"{bib.PLATEFORMES[p][0]} : {resume_stats(sortie)}")
            else:
                t.noter(f"{bib.PLATEFORMES[p][0]} : stats non lues" + (f" ({err})" if err else ""))
        return res
    return FILE.ajouter(f"Stats — {v.titre[:40]}", action)


def tache_extraction(source: str) -> Tache:
    from trendforge.synthese import extraire_recette

    def action(t: Tache):
        return extraire_recette(source, progression=t.noter)
    nom = source if source.startswith("http") else Path(source).name
    return FILE.ajouter(f"Recette depuis {nom[:60]}", action)


def tache_tendances() -> Tache:
    def action(t: Tache):
        from trendforge.sujets import collecter_toutes
        from trendforge.sujets.bluesky import SourceBluesky
        from trendforge.sujets.google import SourceGoogleActualites, SourceGoogleTrends
        from trendforge.sujets.moderation import ecarter
        from trendforge.sujets.x import SourceX

        res = reserve()
        retirees = res.purger()
        sources = [SourceBluesky(limite=10), SourceGoogleTrends(limite=10), SourceGoogleActualites(limite=10),
                   SourceX(RESERVE / "x_depenses.json", limite=10)]
        resultats = collecter_toutes(sources)
        for r in resultats:
            t.noter(f"{r.nom} : {r.statut} {r.message}")
        toutes = [f for r in resultats for f in r.fiches]
        gardees = [f for f in toutes if not ecarter(f)]
        stats = res.ajouter(gardees)
        t.noter(f"✓ {stats['ajoutees']} sujet(s) ajouté(s), {len(toutes) - len(gardees)} écarté(s) par la "
                f"modération, {len(retirees)} tendance(s) périmée(s) retirée(s)")
    return FILE.ajouter("Recherche des tendances (Bluesky, Google, X)", action)


def tache_histoire(texte: str) -> Tache:
    def action(t: Tache):
        from trendforge.scripts import reducteur_claude
        from trendforge.sujets.idees import SourceIdees
        from trendforge.sujets.moderation import ecarter, raisons

        IDEES.mkdir(parents=True, exist_ok=True)
        f = IDEES / f"colle-{datetime.now():%Y%m%d-%H%M%S}.txt"
        f.write_text(texte, encoding="utf-8")
        t.noter("Réduction en fiche situation (Claude)…")
        src = SourceIdees(IDEES, reducteur_claude)
        fiches = [x for x in src.collecter() if x.id]
        for x, err in src.erreurs:
            t.noter(f"✗ {x.name} : {err}")
        refusees = [x for x in fiches if ecarter(x)]
        for x in refusees:
            t.noter(f"⚠ écartée par la modération ({', '.join(raisons(x))}) : {x.titre}")
        stats = reserve().ajouter([x for x in fiches if not ecarter(x)])
        src.archiver()
        t.noter(f"✓ {stats['ajoutees']} fiche(s) ajoutée(s) à la réserve")
    return FILE.ajouter("Histoire collée → fiche sujet", action)


# --------------------------------------------------------------------------- page


@ui.page("/")
def index() -> None:
    ui.colors(primary="#6d28d9", secondary="#f59e0b", accent="#0ea5e9")
    ui.add_css("""
      .tf-carte { width: 100%; }
      .tf-mono { font-family: ui-monospace, monospace; font-size: 12px; white-space: pre-wrap; }
      video { border-radius: 10px; background: #000; }
      .tf-details pre, .tf-details code { white-space: pre-wrap !important; word-break: break-word; }
      .tf-details .tf-json { max-height: 62vh; overflow: auto; }
      .tf-upload .q-uploader__list { min-height: 0; padding: 0; }
      .tf-upload .q-uploader__subtitle { display: none; }
    """)

    with ui.header().classes("items-center justify-between bg-primary"):
        ui.label("TrendForge").classes("text-xl font-bold")
        quota_label = ui.label("").classes("text-sm opacity-90")

    async def maj_quota():
        from nicegui import run

        from trendforge.voix_elevenlabs import quota
        q = await run.io_bound(quota)
        quota_label.text = (f"ElevenLabs : {q[0]:,} / {q[1]:,} caractères ce mois-ci".replace(",", " ")
                            if q else "ElevenLabs : quota indisponible")
    ui.timer(0.5, maj_quota, once=True)

    with ui.tabs().classes("w-full") as onglets:
        o_rec = ui.tab("Recettes", icon="menu_book")
        o_gen = ui.tab("Générer", icon="auto_awesome")
        o_pub = ui.tab("À publier", icon="video_library")
        o_suj = ui.tab("Sujets", icon="lightbulb")

    etat = {"recette_choisie": None}

    with ui.tab_panels(onglets, value=o_pub).classes("w-full"):
        # ================================================================ RECETTES
        with ui.tab_panel(o_rec):
            with ui.card().classes("tf-carte"):
                ui.label("Nouvelle recette depuis une vidéo").classes("text-lg font-bold")
                ui.label("Colle un lien TikTok. Si TikTok bloque le téléchargement, importe le fichier .mp4.") \
                    .classes("text-sm text-grey-7")
                with ui.row().classes("w-full items-center"):
                    url = ui.input("Lien TikTok").classes("grow")

                    def extraire():
                        if not url.value.strip().startswith("http"):
                            ui.notify("Colle un lien qui commence par http", type="warning")
                            return
                        tache_extraction(url.value.strip())
                        url.value = ""
                        ui.notify("Extraction lancée (2 à 6 min) : suivi dans « Tâches » en bas", type="info")
                    ui.button("Extraire la recette", icon="science", on_click=extraire)

                async def televerse(e):
                    IMPORTS.mkdir(parents=True, exist_ok=True)
                    cible = IMPORTS / f"{datetime.now():%Y%m%d-%H%M%S}_{Path(e.file.name).name}"
                    await e.file.save(cible)
                    tache_extraction(str(cible))
                    ui.notify(f"{e.file.name} importé, extraction lancée", type="info")
                ui.upload(label="…ou importer un fichier vidéo (.mp4, .mov, .webm)", on_upload=televerse,
                          auto_upload=True) \
                    .props('accept=".mp4,.mov,.webm" flat bordered color=grey-2 text-color=grey-9') \
                    .classes("w-full tf-upload")

            @ui.refreshable
            def liste_recettes():
                ok, ko = recettes()
                stats = bib.stats_par_recette()
                audience = bib.audience_par_recette()
                ui.label(f"{len(ok)} recette(s)").classes("text-lg font-bold mt-4")
                for r, d, f in ok:
                    s = stats.get(r.recipe_id, {})
                    with ui.card().classes("tf-carte"):
                        with ui.row().classes("w-full items-start justify-between no-wrap"):
                            with ui.column().classes("gap-1 grow").style("min-width: 0"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label(r.recipe_id).classes("text-base font-bold")
                                    ui.badge(r.type_video, color="purple")
                                    ui.badge(f"{r.contenu.target_duration_s[0]:.0f}-{r.contenu.target_duration_s[1]:.0f} s",
                                             color="grey")
                                    if d.get("extraite_le"):
                                        ui.badge("extraite " + d["extraite_le"][:10], color="teal")
                                ui.label("Contenu : " + r.contenu.angle).classes("text-sm")
                                ui.label("Visuel : " + r.visuel.ambiance).classes("text-sm text-grey-7")
                                ui.label("Sujets : " + ", ".join(x.value for x in r.contenu.sources_acceptees)
                                         + f" · {len(fiches_pour(r))} sujet(s) neuf(s) en réserve").classes("text-xs text-grey-7")
                                if r.source and r.source.url:
                                    ui.link("vidéo d'origine", str(r.source.url), new_tab=True).classes("text-xs")
                            with ui.column().classes("items-end gap-1").style("flex: none"):
                                ui.label(f"{s.get('total', 0)} vidéo(s) · {s.get('publiee', 0)} publiée(s)") \
                                    .classes("text-sm")
                                if a := audience.get(r.recipe_id):
                                    ui.label(f"{_n(a['views'])} vues · {_n(a['likes'])} likes · {_n(a['comments'])} comm.") \
                                        .classes("text-sm text-blue-8")
                                with ui.row().classes("gap-1 no-wrap items-center"):
                                    ui.button("Détails", icon="visibility",
                                              on_click=lambda r=r, d=d: details_recette(r, d)).props("flat dense")

                                    def utiliser(r=r):
                                        etat["recette_choisie"] = r.recipe_id
                                        panneau_generer.refresh()
                                        onglets.value = o_gen
                                    ui.button("Générer avec", icon="play_arrow", on_click=utiliser).props("dense")

                                    def archiver(f=f):
                                        ARCHIVE_RECETTES.mkdir(exist_ok=True)
                                        shutil.move(str(f), ARCHIVE_RECETTES / f.name)
                                        ui.notify(f"{f.stem} archivée (recettes/.archive)")
                                        liste_recettes.refresh()
                                    ui.button(icon="archive", on_click=archiver).props("flat dense title=Archiver")
                for f, err in ko:
                    ui.label(f"⚠ {f.name} invalide : {err}").classes("text-sm text-red")

            def details_recette(r: Recipe, d: dict):
                with ui.dialog() as dlg, ui.card().classes("tf-details").style("max-width: 1100px; width: 92vw"):
                    ui.label(r.recipe_id).classes("text-lg font-bold")
                    ui.label(r.why_it_works).classes("text-sm italic")
                    with ui.row().classes("w-full no-wrap gap-4"):
                        with ui.column().classes("col").style("min-width: 0"):
                            ui.label("Contenu").classes("font-bold")
                            ui.code(json.dumps(r.contenu.model_dump(mode="json", exclude_none=True),
                                               ensure_ascii=False, indent=2), language="json") \
                                .classes("w-full tf-json")
                        with ui.column().classes("col").style("min-width: 0"):
                            ui.label("Visuel").classes("font-bold")
                            ui.code(json.dumps(r.visuel.model_dump(mode="json", exclude_none=True),
                                               ensure_ascii=False, indent=2), language="json") \
                                .classes("w-full tf-json")
                    with ui.row().classes("w-full justify-end"):
                        ui.button("Fermer", on_click=dlg.close).props("flat")
                dlg.open()

            liste_recettes()

        # ================================================================ GÉNÉRER
        with ui.tab_panel(o_gen):
            @ui.refreshable
            def panneau_generer():
                ok, _ = recettes()
                ids = [r.recipe_id for r, _, _ in ok]
                if not ids:
                    ui.label("Aucune recette : ajoute-en une dans l'onglet Recettes.")
                    return
                choisie = etat["recette_choisie"] if etat["recette_choisie"] in ids else ids[0]
                mode = ui.toggle({"auto": "Automatique", "perso": "Personnalisé"}, value="auto")

                # ---- automatique
                with ui.card().classes("tf-carte").bind_visibility_from(mode, "value", value="auto"):
                    ui.label("La recette choisie + les sujets neufs de la réserve, sans rien d'autre à faire.") \
                        .classes("text-sm text-grey-7")
                    with ui.row().classes("items-end"):
                        sel_auto = ui.select({"__hasard__": "Au hasard", **{i: i for i in ids}},
                                             value=choisie, label="Recette").classes("w-80")
                        nb = ui.number("Nombre de vidéos", value=1, min=1, max=5, step=1).classes("w-40")
                    est_auto = ui.label("").classes("text-sm")

                    def maj_est_auto():
                        est_auto.text = ("" if sel_auto.value == "__hasard__"
                                         else "Par vidéo : " + estimation(recette(sel_auto.value)))
                    sel_auto.on_value_change(lambda _: maj_est_auto())
                    maj_est_auto()

                    def lancer_auto():
                        n = int(nb.value or 1)
                        lancees, pris = 0, set()
                        for _ in range(n):
                            rid = random.choice(ids) if sel_auto.value == "__hasard__" else sel_auto.value
                            r = recette(rid)
                            fiches = [f for f in fiches_pour(r) if f.id not in pris]
                            if not fiches:
                                ui.notify(f"Plus de sujet neuf pour « {rid} » : onglet Sujets → chercher les "
                                          "tendances ou coller une histoire.", type="warning", timeout=8000)
                                break
                            pris.add(fiches[0].id)
                            tache_generation(r, fiches[0])
                            lancees += 1
                        if lancees:
                            ui.notify(f"{lancees} vidéo(s) en file : suivi dans « Tâches » en bas", type="positive")
                    ui.button("Générer", icon="auto_awesome", on_click=lancer_auto).props("size=lg")

                # ---- personnalisé
                with ui.card().classes("tf-carte").bind_visibility_from(mode, "value", value="perso"):
                    with ui.row().classes("w-full"):
                        sel_c = ui.select(ids, value=choisie, label="Contenu de la recette…").classes("w-72")
                        sel_v = ui.select(ids, value=choisie, label="…avec le visuel de la recette").classes("w-72")
                    source = ui.radio({"reserve": "Sujet de la réserve", "texte": "Coller une histoire ou un texte"},
                                      value="reserve").props("inline")
                    sel_fiche = ui.select({}, label="Sujet").classes("w-full")
                    aucun_sujet = ui.label("Aucun sujet compatible avec cette recette dans la réserve : onglet "
                                           "Sujets (tendances ou histoire collée), ou coche « déjà utilisés ».") \
                        .classes("text-sm text-orange-9")
                    toutes = ui.checkbox("Montrer aussi les sujets déjà utilisés", value=False)
                    texte_libre = ui.textarea("Histoire / texte source (sera réduit en fiche, jamais recopié)") \
                        .classes("w-full")
                    texte_libre.bind_visibility_from(source, "value", value="texte")
                    sel_fiche.bind_visibility_from(source, "value", value="reserve")
                    toutes.bind_visibility_from(source, "value", value="reserve")
                    consignes = ui.textarea("Consignes libres (ex. « ton plus drôle », « fond bleu nuit », "
                                            "« termine par une question sur les chats »)").classes("w-full")
                    with ui.expansion("Script imposé (optionnel)").classes("w-full"):
                        script_impose = ui.textarea("Texte exact à lire (remplace l'écriture par Claude)") \
                            .classes("w-full")
                    est_perso = ui.label("").classes("text-sm")

                    def maj_perso():
                        r = combiner(recette(sel_c.value), recette(sel_v.value))
                        fiches = fiches_pour(r, seulement_neuves=not toutes.value)
                        sel_fiche.options = {f.id: f"[{f.type.value}] {f.titre}" for f in fiches}
                        sel_fiche.value = fiches[0].id if fiches else None
                        sel_fiche.update()
                        aucun_sujet.visible = source.value == "reserve" and not fiches
                        est_perso.text = "Estimation : " + estimation(r)
                    for w in (sel_c, sel_v, toutes, source):
                        w.on_value_change(lambda _: maj_perso())
                    maj_perso()

                    async def lancer_perso():
                        r = combiner(recette(sel_c.value), recette(sel_v.value))
                        if source.value == "texte":
                            if len((texte_libre.value or "").strip()) < 80:
                                ui.notify("Colle un texte d'au moins quelques phrases", type="warning")
                                return
                            from nicegui import run

                            from trendforge.scripts import reducteur_claude
                            from trendforge.sujets.idees import fiche_depuis_fichier
                            IMPORTS.mkdir(parents=True, exist_ok=True)
                            f = IMPORTS / f"perso-{datetime.now():%Y%m%d-%H%M%S}.txt"
                            f.write_text(texte_libre.value, encoding="utf-8")
                            ui.notify("Réduction du texte en fiche situation…")
                            from trendforge.sujets.moderation import ecarter, raisons
                            fiche = await run.io_bound(lambda: reducteur_claude(fiche_depuis_fichier(f)))
                            if ecarter(fiche):
                                ui.notify(f"Texte écarté par la modération ({', '.join(raisons(fiche))})",
                                          type="warning", timeout=8000)
                                return
                            reserve().ajouter([fiche])
                        else:
                            fiche = next((x for x in reserve().charger() if x.id == sel_fiche.value), None)
                            if fiche is None:
                                ui.notify("Choisis un sujet (ou va dans l'onglet Sujets pour en ajouter)",
                                          type="warning")
                                return
                        tache_generation(r, fiche, consignes.value, script_impose.value)
                        ui.notify("Vidéo en file : suivi dans « Tâches » en bas", type="positive")
                    ui.button("Générer cette vidéo", icon="tune", on_click=lancer_perso).props("size=lg")

            panneau_generer()

        # ================================================================ À PUBLIER
        with ui.tab_panel(o_pub):
            filtre = ui.toggle({"attente": "Non publiées", "publiee": "Publiées", "rejetee": "Rejetées",
                                "toutes": "Toutes"}, value="attente",
                               on_change=lambda _: liste_videos.refresh())

            @ui.refreshable
            def liste_videos():
                choix = {"attente": {"a_valider", "validee"}, "publiee": {"publiee"},
                         "rejetee": {"rejetee", "echec_duree", "echec_page"}, "toutes": None}[filtre.value]
                videos = bib.lister(choix)
                if not videos:
                    ui.label("Aucune vidéo ici.").classes("text-grey-7 mt-4")
                for v in videos:
                    carte_video(v)

            def carte_video(v: bib.Video):
                nom, couleur = STATUTS.get(v.statut, (v.statut, "grey"))
                with ui.card().classes("tf-carte"):
                    with ui.row().classes("w-full no-wrap items-start gap-6"):
                        if v.fichier:
                            ui.video(f"/medias/{v.id}/video.mp4", autoplay=False, muted=False) \
                                .style("width: 260px; height: 462px; flex: none")
                        else:
                            with ui.column().classes("items-center justify-center bg-grey-2 text-grey-7 "
                                                     "rounded-borders q-pa-md text-center") \
                                    .style("width: 260px; height: 200px; flex: none"):
                                ui.icon("videocam_off", size="40px")
                                ui.label("Pas de vidéo").classes("text-sm")
                        with ui.column().classes("grow gap-2"):
                            with ui.row().classes("items-center gap-2"):
                                ui.badge(nom, color=couleur)
                                ui.label(v.titre or v.id).classes("text-base font-bold")
                            ui.label(f"Recette {v.recette} · {v.date:%d/%m %H:%M} · "
                                     f"{v.duree_s or 0:.0f} s · {v.cout_usd:.2f} $ de Claude").classes("text-sm text-grey-7")
                            for a in v.avertissements:
                                ui.label("⚠ " + a).classes("text-xs text-orange-8")
                            if v.publication:
                                ui.label("Publiée sur : " + ", ".join(
                                    f"{bib.PLATEFORMES[p][0]} ({d[:10]})" for p, d in v.publication.items()
                                    if p in bib.PLATEFORMES)).classes("text-sm text-blue-8")
                            if not v.fichier:
                                ui.label(raison_sans_video(v)).classes("text-sm text-red-8")
                            with ui.expansion("Script").classes("w-full"):
                                ui.label(v.script).classes("text-sm")
                            leg = ui.textarea("Légende (titre, texte, hashtags)", value=v.legende) \
                                .classes("w-full").props("autogrow")

                            def sauver_leg(v=v, leg=leg):
                                (v.dossier / "legende.txt").write_text(leg.value, encoding="utf-8")
                                ui.notify("Légende enregistrée")
                            with ui.row().classes("gap-2"):
                                ui.button("Enregistrer la légende", icon="save", on_click=sauver_leg).props("flat dense")
                                ui.button("Copier la légende", icon="content_copy",
                                          on_click=lambda leg=leg: (ui.clipboard.write(leg.value),
                                                                    ui.notify("Légende copiée")))\
                                    .props("flat dense")
                            ui.separator()
                            with ui.row().classes("items-center gap-2"):
                                if v.statut in ("a_valider", "rejetee"):
                                    ui.button("Valider", icon="check", color="green",
                                              on_click=lambda v=v: (bib.changer_statut(v, "validee"),
                                                                    liste_videos.refresh()))
                                if v.statut in ("a_valider", "validee"):
                                    ui.button("Rejeter", icon="close", color="grey",
                                              on_click=lambda v=v: (bib.changer_statut(v, "rejetee"),
                                                                    liste_videos.refresh())).props("flat")

                                def supprimer(v=v):
                                    with ui.dialog() as dlg, ui.card():
                                        ui.label(f"Supprimer définitivement {v.id} (vidéo, script, journal) ?")
                                        with ui.row():
                                            ui.button("Annuler", on_click=dlg.close).props("flat")

                                            def ok():
                                                bib.supprimer(v)
                                                dlg.close()
                                                liste_videos.refresh()
                                            ui.button("Supprimer", color="red", on_click=ok)
                                    dlg.open()
                                ui.button(icon="delete", on_click=supprimer).props("flat dense title=Supprimer")
                            if v.fichier and v.statut in ("validee", "publiee", "a_valider"):
                                carte_reseaux(v, leg)

            def carte_reseaux(v: bib.Video, leg):
                """Suivi par réseau : brouillon (Claude Code), lien du post, statistiques."""
                with ui.card().classes("w-full bg-grey-1"):
                    ui.label("Réseaux sociaux").classes("font-bold")
                    with ui.grid(columns="150px 150px 1fr 1.3fr").classes("w-full items-center gap-x-4 gap-y-2"):
                        for t in ("Réseau", "Brouillon", "Lien du post", "Dernières stats"):
                            ui.label(t).classes("text-xs text-grey-7 font-bold")
                        for p, (nom, _) in bib.PLATEFORMES.items():
                            ui.label(nom).classes("text-sm font-bold")
                            b = v.brouillons.get(p)
                            if b:
                                lib, coul = ETATS_BROUILLON.get(b["statut"], (b["statut"], "grey"))
                                ui.badge(lib, color=coul).props(f'title="{b.get("details", "")[:200]}"')
                            else:
                                ui.label("—").classes("text-grey-6")
                            if p in v.liens:
                                ui.link(v.liens[p][:60], v.liens[p], new_tab=True).classes("text-sm")
                            else:
                                with ui.row().classes("items-center no-wrap gap-1"):
                                    champ = ui.input(placeholder="coller le lien une fois publié").props("dense") \
                                        .classes("grow")

                                    def sauver_lien(v=v, p=p, champ=champ):
                                        if not (champ.value or "").startswith("http"):
                                            ui.notify("Colle un lien qui commence par http", type="warning")
                                            return
                                        bib.enregistrer_lien(v, p, champ.value)
                                        liste_videos.refresh()
                                    ui.button(icon="link", on_click=sauver_lien).props("flat dense title=Enregistrer")
                            st = v.derniers_stats().get(p)
                            if st:
                                with ui.column().classes("gap-0"):
                                    ui.label(resume_stats(st)).classes("text-sm")
                                    ui.label(f"relevé le {st['captured_at'][:16].replace('T', ' ')} · "
                                             f"{len(v.stats[p])} relevé(s)").classes("text-xs text-grey-7")
                            else:
                                ui.label("—").classes("text-grey-6")

                    ui.separator()
                    with ui.row().classes("gap-4 items-center"):
                        cases = {p: ui.checkbox(n, value=(p not in v.publication and p not in v.brouillons))
                                 for p, (n, _) in bib.PLATEFORMES.items()}

                    def choisies():
                        c = [p for p, x in cases.items() if x.value]
                        if not c:
                            ui.notify("Coche au moins un réseau", type="warning")
                        return c

                    def brouillons(v=v):
                        if c := choisies():
                            tache_brouillons(v, c)
                            ui.notify("Claude Code prépare les brouillons dans ton Chrome : suivi dans « Tâches ». "
                                      "Il ne publie jamais.", type="info", timeout=7000)

                    def manuel(v=v, leg=leg):
                        if not (c := choisies()):
                            return
                        ui.clipboard.write(leg.value)
                        try:
                            ouverts = bib.ouvrir_publication(v, c)
                        except FileNotFoundError as e:
                            ui.notify(f"Impossible d'ouvrir : {e.filename} introuvable. Légende copiée.",
                                      type="negative", timeout=8000)
                            return
                        ui.notify(f"Ouvert : {', '.join(ouverts)} + dossier. Légende copiée.", type="positive")
                    with ui.row().classes("gap-2 items-center"):
                        ui.button("Mettre en brouillon (Claude Code)", icon="smart_toy", on_click=brouillons)
                        ui.button("Ouvrir les pages d'envoi (à la main)", icon="open_in_new", on_click=manuel) \
                            .props("flat")
                        ui.button("Retrouver les liens", icon="travel_explore",
                                  on_click=lambda v=v: (tache_liens(v), ui.notify("Recherche des liens lancée"))) \
                            .props("flat")
                        ui.button("Relever les stats", icon="insights",
                                  on_click=lambda v=v: (tache_stats(v) if v.liens else
                                                        ui.notify("Aucun lien de post : publie puis retrouve ou "
                                                                  "colle les liens d'abord", type="warning"))) \
                            .props("flat")
                    ui.label("Claude Code pilote ton Chrome (extension Claude in Chrome) : il envoie la vidéo, "
                             "colle la légende, coche l'étiquette IA et s'arrête au brouillon. Tu publies "
                             "toi-même, puis colle le lien ou clique « Retrouver les liens ».") \
                        .classes("text-xs text-grey-7")

            liste_videos()

        # ================================================================ SUJETS
        with ui.tab_panel(o_suj):
            with ui.row().classes("w-full gap-4 no-wrap items-start"):
                with ui.card().classes("w-1/3"):
                    ui.label("Ajouter des sujets réels").classes("text-lg font-bold")
                    ui.button("Chercher les tendances du jour", icon="trending_up",
                              on_click=lambda: (tache_tendances(),
                                                ui.notify("Recherche lancée : suivi dans « Tâches »"))) \
                        .classes("w-full")
                    ui.separator()
                    histoire = ui.textarea("Coller une histoire (Reddit, forum…)").classes("w-full") \
                        .props("autogrow")

                    def ajouter_histoire():
                        if len((histoire.value or "").strip()) < 80:
                            ui.notify("Colle le texte complet du post (quelques phrases au moins)", type="warning")
                            return
                        tache_histoire(histoire.value)
                        histoire.value = ""
                        ui.notify("Réduction en fiche lancée (Claude) : suivi dans « Tâches »")
                    ui.button("Ajouter à la réserve", icon="add", on_click=ajouter_histoire).classes("w-full")
                    ui.label("Le texte n'est jamais recopié : Claude le réduit en fiche situation (rôles, "
                             "conflit, rebondissement) et le script part de la fiche.").classes("text-xs text-grey-7")

                with ui.column().classes("grow"):
                    @ui.refreshable
                    def liste_sujets():
                        utilisees = fiches_utilisees()
                        fiches = reserve().selection()
                        ui.label(f"{len(fiches)} sujet(s) en réserve").classes("text-lg font-bold")
                        for f in fiches:
                            with ui.card().classes("tf-carte"):
                                with ui.row().classes("w-full no-wrap items-start justify-between"):
                                    with ui.column().classes("gap-0"):
                                        with ui.row().classes("items-center gap-2"):
                                            ui.badge(f.type.value, color="teal")
                                            if f.id in utilisees:
                                                ui.badge("déjà utilisé", color="grey")
                                            ui.label(f.titre).classes("font-bold")
                                        ui.label(f.resume).classes("text-sm text-grey-8")
                                        for ref in f.references[:3]:
                                            ui.link(ref.titre, str(ref.url) if ref.url else "#", new_tab=True) \
                                                .classes("text-xs")

                                    def retirer(f=f):
                                        reserve().retirer(f.id)
                                        liste_sujets.refresh()
                                    ui.button(icon="delete", on_click=retirer).props('flat dense title="Retirer de la réserve"')
                    liste_sujets()

    # ---------------------------------------------------------------- tâches (bas de page)
    with ui.footer().classes("bg-white text-black shadow-up-2").style("max-height: 34vh; overflow-y: auto"):
        @ui.refreshable
        def panneau_taches():
            taches = FILE.recentes()
            if not taches:
                ui.label("Tâches : aucune pour l'instant.").classes("text-sm text-grey-7")
                return
            ui.label("Tâches").classes("font-bold text-sm")
            for t in taches:
                couleur = {"en cours": "text-primary", "terminée": "text-green-8", "échec": "text-red-8"} \
                    .get(t.etat, "text-grey-7")
                msg = t.derniere[10:]
                msg = msg if len(msg) <= 120 else msg[:119] + "…"
                with ui.expansion(f"{t.libelle} — {t.etat} · {msg}",
                                  value=False).classes(f"w-full text-sm {couleur}"):
                    ui.label("\n".join(t.lignes)).classes("tf-mono")

        def signature_generer():
            return ([r.recipe_id for r, _, _ in recettes()[0]], [f.id for f in reserve().selection()])

        signature = {"v": None, "gen": signature_generer()}

        def rafraichir():
            sig = [(t.id, t.etat, len(t.lignes)) for t in FILE.recentes()]
            if sig != signature["v"]:
                fini = signature["v"] is not None and any(
                    e in ("terminée", "échec") and (i, e) not in {(a, b) for a, b, _ in signature["v"]}
                    for i, e, _ in sig)
                signature["v"] = sig
                panneau_taches.refresh()
                if fini:  # une tâche vient de finir : les listes ont pu changer
                    liste_videos.refresh()
                    liste_recettes.refresh()
                    liste_sujets.refresh()
                    # le panneau Générer n'est reconstruit que si ses choix ont changé (sinon on
                    # effacerait le formulaire en cours de saisie)
                    if signature_generer() != signature["gen"]:
                        signature["gen"] = signature_generer()
                        panneau_generer.refresh()
        panneau_taches()
        ui.timer(1.0, rafraichir)


# --------------------------------------------------------------------------- lancement


def lancer(fenetre: bool = True, port: int = PORT) -> None:
    from trendforge.bibliotheque import SORTIES

    SORTIES.mkdir(exist_ok=True)
    app.add_media_files("/medias", SORTIES)
    if fenetre:
        def ouvrir():
            subprocess.Popen(["google-chrome", f"--app=http://127.0.0.1:{port}", "--window-size=1400,950"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        app.on_startup(ouvrir)
    ui.run(host="127.0.0.1", port=port, title="TrendForge", show=False, reload=False, favicon="🎬",
           language="fr")
