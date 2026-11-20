"""Google Actualités (RSS) et Google Trends (flux RSS des tendances quotidiennes).

Formats observés en réel (novembre 2026), sans compte :
- `https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en` (à la une US) et
  `https://news.google.com/rss/search?q=<mots>&hl=en-US&gl=US&ceid=US:en` : RSS 2.0,
  `<item>` = title (« Titre - Média »), link (redirection news.google.com/rss/articles/…),
  guid, pubDate (GMT), description (HTML `<ol><li><a href=…>titre</a><font>Média</font></li>…`
  = grappe d'articles sur le même sujet), `<source url=…>Média</source>` ;
- `https://trends.google.com/trending/rss?geo=US` : RSS 2.0 avec l'espace de noms `ht:`
  (`ht:approx_traffic` « 2000+ », pubDate en heure du Pacifique, `ht:picture`). Les éléments
  `ht:news_item` (articles liés) des anciennes versions du flux sont **absents** : le contexte
  est donc cherché dans Google Actualités par mot-clé. pytrends n'est pas utilisé.
"""

from __future__ import annotations

import calendar
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote_plus

import feedparser
import httpx

from trendforge.models import FicheSujet, Reference, SourceType
from trendforge.sujets.base import ErreurSource, SourceSujets, client_http, id_fiche, maintenant

URL_UNE = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
URL_RECHERCHE = "https://news.google.com/rss/search?q={q}+when:2d&hl=en-US&gl=US&ceid=US:en"
URL_TRENDS = "https://trends.google.com/trending/rss?geo={geo}"
NS_HT = "https://trends.google.com/trending/rss"
LI_RE = re.compile(r'<a href="([^"]+)"[^>]*>(.*?)</a>(?:&nbsp;|\s|\xa0)*(?:<font[^>]*>(.*?)</font>)?', re.S)


def _date_entree(e: Any) -> datetime:
    t = e.get("published_parsed") or e.get("updated_parsed")
    if t:
        return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return maintenant()


def _sans_media(titre: str, media: str | None) -> str:
    titre = html.unescape(titre).strip()
    if media and titre.endswith(f" - {media}"):
        return titre[: -len(media) - 3].strip()
    return re.sub(r"\s+-\s+[^-]{2,60}$", "", titre)


def parser_actualites(contenu: bytes) -> list[dict[str, Any]]:
    """Flux Google Actualités -> [{titre, media, url, date, grappe: [Reference]}]."""
    d = feedparser.parse(contenu)
    if d.bozo and not d.entries:
        raise ErreurSource(f"flux RSS illisible : {d.bozo_exception}")
    out = []
    for e in d.entries:
        media = (e.get("source") or {}).get("title")
        grappe = []
        for href, t, m in LI_RE.findall(e.get("summary", "")):
            titre = html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
            m = html.unescape(m or "").strip()
            grappe.append(Reference(titre=f"{titre} ({m})" if m else titre, url=html.unescape(href)))
        out.append({
            "titre": _sans_media(e.get("title", ""), media),
            "media": media,
            "url": e.get("link"),
            "date": _date_entree(e),
            "grappe": grappe,
        })
    return out


def parser_trends(contenu: bytes) -> list[dict[str, Any]]:
    """Flux Google Trends -> [{terme, trafic, date, articles: [Reference]}]."""
    try:
        racine = ET.fromstring(contenu)
    except ET.ParseError as e:
        raise ErreurSource(f"flux Trends illisible : {e}") from e
    out = []
    for item in racine.iter("item"):
        terme = (item.findtext("title") or "").strip()
        if not terme:
            continue
        pub = item.findtext("pubDate")
        try:
            date = parsedate_to_datetime(pub).astimezone(timezone.utc) if pub else maintenant()
        except (TypeError, ValueError):
            date = maintenant()
        articles = []
        for n in item.findall(f"{{{NS_HT}}}news_item"):  # absent du flux actuel, gardé si ça revient
            t, u = n.findtext(f"{{{NS_HT}}}news_item_title"), n.findtext(f"{{{NS_HT}}}news_item_url")
            if t and u:
                articles.append(Reference(titre=html.unescape(t), url=u))
        out.append({
            "terme": terme,
            "trafic": item.findtext(f"{{{NS_HT}}}approx_traffic"),
            "date": date,
            "articles": articles,
        })
    return out


def _get(client: httpx.Client, url: str) -> bytes:
    r = client.get(url)
    r.raise_for_status()
    return r.content


def rechercher_articles(client: httpx.Client, requete: str, n: int = 3) -> list[Reference]:
    """2-3 articles de contexte récents (< 2 jours) sur un sujet, via la recherche Google Actualités."""
    items = parser_actualites(_get(client, URL_RECHERCHE.format(q=quote_plus(f'"{requete}"'))))
    if not items:  # sans guillemets si la recherche exacte ne donne rien
        items = parser_actualites(_get(client, URL_RECHERCHE.format(q=quote_plus(requete))))
    return [Reference(titre=f"{i['titre']} ({i['media']})" if i["media"] else i["titre"], url=i["url"])
            for i in items[:n]]


class SourceGoogleActualites(SourceSujets):
    """À la une de Google Actualités US : chaque grappe d'articles devient une fiche « actualite »."""

    nom = "google_actualites"

    def __init__(self, limite: int = 10, transport: httpx.BaseTransport | None = None) -> None:
        self.limite = limite
        self.transport = transport

    def collecter(self) -> list[FicheSujet]:
        releve = maintenant()
        with client_http(self.transport) as client:
            items = parser_actualites(_get(client, URL_UNE))
        fiches = []
        for i in items[: self.limite]:
            refs = i["grappe"][:3] or [Reference(titre=i["titre"], url=i["url"])]
            fiches.append(FicheSujet(
                id=id_fiche(SourceType.actualite, i["url"] or i["titre"]),
                type=SourceType.actualite,
                url=i["url"],
                date_source=i["date"],
                ajoutee_le=releve,
                titre=i["titre"],
                resume=i["titre"] + (f" ({i['media']})" if i["media"] else ""),
                references=refs,
            ))
        return fiches


class SourceGoogleTrends(SourceSujets):
    """Recherches qui montent (RSS Trends), chacune enrichie de 2-3 articles Google Actualités."""

    nom = "google_trends"

    def __init__(self, geo: str = "US", limite: int = 10, articles_par_sujet: int = 3,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.geo = geo
        self.limite = limite
        self.articles_par_sujet = articles_par_sujet
        self.transport = transport
        self.notes: list[str] = []

    def collecter(self) -> list[FicheSujet]:
        self.notes = []
        releve = maintenant()
        fiches = []
        with client_http(self.transport) as client:
            for t in parser_trends(_get(client, URL_TRENDS.format(geo=self.geo)))[: self.limite]:
                refs = t["articles"][: self.articles_par_sujet]
                if not refs:
                    try:
                        refs = rechercher_articles(client, t["terme"], self.articles_par_sujet)
                    except (httpx.HTTPError, ErreurSource) as e:
                        self.notes.append(f"{t['terme']!r} : recherche d'articles en échec ({e})")
                if not refs:
                    self.notes.append(f"{t['terme']!r} : aucun article de contexte, ignoré")
                    continue
                trafic = f" ({t['trafic']} recherches)" if t["trafic"] else ""
                fiches.append(FicheSujet(
                    id=id_fiche(SourceType.google_trends, t["terme"]),
                    type=SourceType.google_trends,
                    url=f"https://trends.google.com/trends/explore?geo={self.geo}&q={quote_plus(t['terme'])}",
                    date_source=t["date"],
                    ajoutee_le=releve,
                    titre=t["terme"],
                    resume=f"Recherche en hausse sur Google{trafic} : {refs[0].titre}",
                    references=refs,
                ))
        return fiches
