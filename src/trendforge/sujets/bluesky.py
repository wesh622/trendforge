"""Tendances Bluesky via l'API publique, sans compte.

Endpoints vérifiés en réel (novembre 2026) sur https://public.api.bsky.app :
- `app.bsky.unspecced.getTrends` : 200, sans compte. `{"trends": [{topic, displayName,
  description, link, startedAt, postCount, status, category, actors[]}], "recIdStr"}` ;
- `app.bsky.unspecced.getTrendingTopics` : 200, sans compte. `{"topics": [{topic, displayName,
  description, link}], "suggested": [], "recIdStr"}` (pas de date, pas de compteur) ;
- `app.bsky.feed.getFeed?feed=at://<did>/app.bsky.feed.generator/<rkey>` : 200, sans compte.
  Le `link` d'une tendance (`/profile/<did>/feed/<rkey>`) pointe vers ce flux : on y prend
  les posts les plus aimés ;
- `app.bsky.feed.searchPosts` : **403 sur public.api.bsky.app** (cache CDN), mais 200 sur
  https://api.bsky.app (même AppView, non documenté comme public : utilisé en secours seulement).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from trendforge.models import FicheSujet, Reference, SourceType
from trendforge.sujets.base import ErreurSource, SourceSujets, client_http, id_fiche, maintenant

log = logging.getLogger(__name__)

API_PUBLIQUE = "https://public.api.bsky.app/xrpc"
API_SECOURS = "https://api.bsky.app/xrpc"
WEB = "https://bsky.app"
# Modération minimale (section 7) : la politique est écartée d'office ; le reste viendra plus tard.
CATEGORIES_EXCLUES = frozenset({"politics"})


def parser_tendances(donnees: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise getTrends ou getTrendingTopics en une liste de dicts homogènes."""
    brut = donnees.get("trends")
    if brut is None:
        brut = donnees.get("topics")
    if brut is None:
        raise ErreurSource("réponse Bluesky sans 'trends' ni 'topics'")
    out = []
    for t in brut:
        nom = t.get("displayName") or t.get("topic")
        if not nom:
            continue
        started = t.get("startedAt")
        out.append({
            "nom": nom,
            "description": t.get("description") or "",
            "link": t.get("link") or "",
            "started_at": datetime.fromisoformat(started.replace("Z", "+00:00")) if started else None,
            "post_count": t.get("postCount"),
            "status": t.get("status"),
            "category": t.get("category"),
        })
    return out


def uri_flux(link: str) -> str | None:
    """`/profile/<did>/feed/<rkey>` -> `at://<did>/app.bsky.feed.generator/<rkey>`."""
    segs = [s for s in link.split("/") if s]
    if len(segs) == 4 and segs[0] == "profile" and segs[2] == "feed":
        return f"at://{segs[1]}/app.bsky.feed.generator/{segs[3]}"
    return None


def url_post(post: dict[str, Any]) -> str | None:
    uri = post.get("uri", "")
    handle = post.get("author", {}).get("handle")
    if not uri.startswith("at://") or not handle:
        return None
    return f"{WEB}/profile/{handle}/post/{uri.rsplit('/', 1)[-1]}"


def references_depuis_posts(posts: list[dict[str, Any]], n: int = 3) -> list[Reference]:
    """Les n posts les plus aimés -> Reference(titre = « @handle : début du texte »)."""
    tri = sorted(posts, key=lambda p: p.get("likeCount", 0) + 2 * p.get("repostCount", 0), reverse=True)
    refs = []
    for p in tri:
        texte = " ".join((p.get("record", {}).get("text") or "").split())
        url = url_post(p)
        if not texte or not url:
            continue
        handle = p["author"]["handle"]
        refs.append(Reference(titre=f"@{handle} : {texte[:140]}", url=url))
        if len(refs) == n:
            break
    return refs


def posts_depuis_reponse(donnees: dict[str, Any]) -> list[dict[str, Any]]:
    if "feed" in donnees:  # getFeed
        return [x["post"] for x in donnees["feed"] if "post" in x]
    return list(donnees.get("posts", []))  # searchPosts


class SourceBluesky(SourceSujets):
    nom = "bluesky"

    def __init__(self, limite: int = 10, posts_par_sujet: int = 3,
                 categories_exclues: frozenset[str] = CATEGORIES_EXCLUES,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.limite = limite
        self.posts_par_sujet = posts_par_sujet
        self.categories_exclues = categories_exclues
        self.transport = transport
        self.notes: list[str] = []

    def _get(self, client: httpx.Client, base: str, methode: str, **params: Any) -> dict[str, Any]:
        r = client.get(f"{base}/{methode}", params=params)
        r.raise_for_status()
        return r.json()

    def tendances(self, client: httpx.Client) -> list[dict[str, Any]]:
        try:
            return parser_tendances(self._get(client, API_PUBLIQUE, "app.bsky.unspecced.getTrends", limit=self.limite))
        except (httpx.HTTPError, ErreurSource, ValueError) as e:
            self.notes.append(f"getTrends indisponible ({e}), repli sur getTrendingTopics")
            return parser_tendances(
                self._get(client, API_PUBLIQUE, "app.bsky.unspecced.getTrendingTopics", limit=self.limite))

    def posts(self, client: httpx.Client, tendance: dict[str, Any]) -> list[dict[str, Any]]:
        feed = uri_flux(tendance["link"])
        if feed:
            try:
                return posts_depuis_reponse(self._get(client, API_PUBLIQUE, "app.bsky.feed.getFeed", feed=feed, limit=30))
            except httpx.HTTPError as e:
                self.notes.append(f"getFeed {tendance['nom']!r} : {e}")
        for base in (API_PUBLIQUE, API_SECOURS):  # searchPosts : 403 sur l'API publique en 2026
            try:
                return posts_depuis_reponse(
                    self._get(client, base, "app.bsky.feed.searchPosts", q=tendance["nom"], sort="top", limit=25))
            except httpx.HTTPError as e:
                self.notes.append(f"searchPosts {base} : {e}")
        return []

    def collecter(self) -> list[FicheSujet]:
        self.notes = []
        fiches = []
        releve = maintenant()
        with client_http(self.transport) as client:
            for t in self.tendances(client):
                if t["category"] in self.categories_exclues:
                    continue
                refs = references_depuis_posts(self.posts(client, t), self.posts_par_sujet)
                if not refs:
                    self.notes.append(f"{t['nom']!r} : aucun post trouvé, ignoré")
                    continue
                url = f"{WEB}{t['link']}" if t["link"].startswith("/") else None
                details = [x for x in (
                    f"{t['post_count']} posts" if t["post_count"] else None,
                    t["status"], t["category"]) if x]
                resume = t["description"] or t["nom"]
                if details:
                    resume += f" ({', '.join(details)})"
                fiches.append(FicheSujet(
                    id=id_fiche(SourceType.tendance_bluesky, t["nom"]),
                    type=SourceType.tendance_bluesky,
                    url=url,
                    # date de début de la tendance si connue (getTrends), sinon date du relevé
                    date_source=t["started_at"] or releve,
                    ajoutee_le=releve,
                    titre=t["nom"],
                    resume=resume,
                    references=refs,
                ))
        return fiches
