# Cahier des charges — TrendForge

Nov 20, 2026 · @lossa

**Version 3.1** : mise à jour le 20 novembre 2026 avec l'état réel du code (interface, publication, coûts mesurés), toujours centrée sur le flux « lien TikTok → recette → vidéo animée en HTML ». Les recettes ont deux blocs, contenu et visuel, mélangeables (voir « Historique des modifications » en fin de document).

TrendForge est une application de bureau Linux, open source autant que possible, qui transforme une vidéo TikTok tendance en « recette » puis génère des vidéos originales, prêtes à publier en quelques gestes. Cible : contenu faceless narratif en anglais, publication semi-automatique.

**Priorité (version 3)** : le cœur de l'outil tient en trois gestes.

1. **Extraire** : tu colles un lien TikTok, le module Recette en tire une recette en deux blocs : le **contenu** (thèmes, sources de sujets acceptées, angle, structure, ton) et le **visuel** (ambiance, animation de chaque partie, rythme, sous-titres, voix, son).
2. **Stocker** : la recette rejoint la bibliothèque `recettes/`.
3. **Générer** : une fiche sujet réelle (histoire collée type Reddit, tendance X, Bluesky ou Google) passe par le bloc contenu, et Claude écrit le script. Le script passe ensuite par le bloc visuel, et Claude écrit une page HTML animée. ElevenLabs fait la voix, Chrome sans fenêtre filme la page, FFmpeg assemble le MP4.

Tendances automatiques, interface graphique et statistiques passent après ce flux (section 12).

**Statut des chiffres.** Les durées de traitement (analyse, rendu) sont **provisoires** tant que la V0 ne les a pas mesurées sur ton PC (section 12). Elles sont signalées par « (provisoire) ».

## 1. Objectifs et contraintes

Le but est de produire 1 à 3 vidéos originales par jour et par compte, d'abord pour faire grandir le compte (section 2), puis pour être payé par le Creator Rewards Program.

**Objectif de coût (un seul chiffre)** : **plafond dur de 0,50 $ de coût variable par vidéo.** La variante par défaut est la variante **Standard**, estimée entre 0,03 et 0,21 $ (détail en section 10). Le logiciel refuse de lancer une vidéo dont l'estimation dépasse 0,50 $.

**Objectifs mesurables**

| Objectif | Valeur | Mesurable à partir de |
| --- | --- | --- |
| Temps humain par vidéo (relecture + validation + publication) | moins de 3 min | V1 (chronométré dans le journal) |
| Durée des vidéos longues | 61 à 90 s, contrôlée automatiquement avant export | V1 |
| Durée des vidéos courtes (phase de croissance) | 21 à 45 s | V1 |
| Analyse d'une vidéo (module Recette) | moins de 6 min (provisoire) | fin de V0 |
| Génération complète d'une vidéo | moins de 15 min (provisoire) | fin de V0 |
| Rétention à 3 s | plus de 50 % | V1, par saisie manuelle des stats ; évaluée sur au moins 20 vidéos publiées |
| Vues complètes | plus de 30 % | idem |

Fonctionnement sur ton PC actuel, sans GPU puissant.

**Contraintes de monétisation**

- Compte : 18 ans minimum, 10 000 abonnés, 100 000 vues sur 30 jours, compte enregistré dans un pays éligible (voyager dans un pays éligible ne suffit pas).
- **La France figure dans la liste des pays éligibles** selon presque toutes les sources consultées le 19 novembre 2026, qui citent la page Creator Academy de TikTok (avec les États-Unis, le Royaume-Uni, l'Allemagne, le Japon, la Corée du Sud, le Mexique et le Brésil). Ce sont des sources indirectes. **La vérification finale se fait dans TikTok Studio, rubrique Creator Rewards**, avant de coder (V0).
- Vidéos de plus de 1 min, contenu original : pas de reupload, de duo, de stitch ni de compilation brute.
- Le choix de l'anglais vise un public US/UK mieux payé. Reste à vérifier (section 13) : un compte enregistré en France qui publie en anglais est-il bien diffusé auprès du public US, et la rémunération dépend-elle du pays des spectateurs ?

**Principe clé : on copie la recette, jamais la vidéo.** L'application extrait la structure d'une tendance (hook, rythme, style de sous-titres, durée des plans, ton), puis régénère tout : script, voix, visuels, musique. La vidéo source n'est jamais réutilisée dans le rendu final, et c'est vérifié automatiquement (section 7, contrôle 10). C'est ce qui rend le contenu éligible et évite les réclamations de droits d'auteur.

**Hors périmètre** : publication entièrement robotisée via navigateur, achat de vues, gestion de dizaines de comptes, collecte automatique de Reddit, copie de textes de forums (section 7).

**Principe des sujets : toujours partir d'un fait réel.** Un sujet inventé à partir de rien donne un contenu fade. Chaque vidéo part donc d'une source réelle : une histoire lue sur un forum de type Reddit, ou un sujet tendance sur X (Twitter), Bluesky ou Google (section 7, « Sources de sujets »).

## 2. Phase de croissance (avant 10 000 abonnés)

Tant que le compte n'a pas 10 000 abonnés et 100 000 vues sur 30 jours, aucune vidéo ne rapporte d'argent. Cette phase peut durer des semaines ou des mois. L'application la gère comme une phase à part entière, avec ses propres réglages.

**Réglage « Phase du compte »** (dans Réglages, par compte) : `croissance` ou `monétisation`. Il change trois choses :

|  | Phase croissance | Phase monétisation |
| --- | --- | --- |
| Mélange par défaut | 2 courtes (21 à 45 s) pour 1 longue (61 à 90 s), réglable | 100 % longues (61 à 90 s) |
| Rôle des vidéos | Gagner des abonnés et tester des recettes | Être rémunérées |
| Indicateur suivi en priorité | Abonnés gagnés par semaine, vues sur 30 jours | Vues qualifiées, rétention, revenus |

**Hypothèse à tester** : les formats courts accrochent plus facilement de nouveaux abonnés. C'est une idée répandue, pas une certitude ; les stats saisies diront si elle tient. Les vidéos longues publiées pendant la croissance servent à mettre au point les recettes qui retiennent au-delà d'une minute, pour être prêt le jour où le compte devient éligible.

**Passage en monétisation** : quand les deux seuils sont atteints (saisis à la main ou lus dans les stats), l'application propose de changer de phase. Rien n'est automatique.

**Points de contrôle** : à 4 semaines et à 8 semaines, l'écran Tendances affiche un bilan (abonnés, vues, meilleures recettes). Règle de décision proposée : moins de 1 000 abonnés à 8 semaines ⇒ changer de sous-niche ou de recette principale.

## 3. Ce que dit Internet

Le consensus en 2026 : les plateformes pénalisent le contenu produit en masse et peu transformé, pas le faceless ni l'IA en tant que tels. L'application doit donc maximiser la transformation et la variété, tout en gardant un style de chaîne reconnaissable.

| Constat | Conséquence pour TrendForge |
| --- | --- |
| Le Creator Rewards exige plus de 1 min et du contenu original ; les reposts et compilations brutes ne sont pas payés ([timetopost](https://timetopost.co/blog/tiktok-creator-rewards-requirements-2026/), [ttcalculator](https://ttcalculator.net/blog/how-tiktok-creator-rewards-work-2026/)) | Contrôle de durée bloquant ; aucune image de la vidéo source dans le rendu |
| La France apparaît parmi les pays éligibles au Creator Rewards ; la liste exacte varie selon les sources et TikTok Studio fait foi ([ttcalculator](https://ttcalculator.net/learn/creator-fund-countries/), [shortsfast](https://shortsfast.com/blog/tiktok-creator-rewards-eligibility-2026/)) | Vérification dans TikTok Studio en V0, avant tout développement |
| **Reddit ferme son API publique** : plus de nouvelles demandes d'accès depuis le 31 octobre 2026, retrait progressif à partir du 12 janvier 2027, fermeture totale en mars 2027 ([TechCrunch](https://techcrunch.com/?p=3172243), [Decrypt](https://decrypt.co/379892/reddit-killing-rss-feeds-and-public-api-access-to-fight-ai-scrapers)). L'usage commercial demandait déjà un accord écrit ([redditapis](https://www.redditapis.com/blogs/reddit-api-commercial-use-licensing-explained-2026)) | **Aucune collecte automatique de Reddit.** Tu colles toi-même le lien ou le texte d'une histoire lue ; l'IA n'en garde que la situation et réécrit tout (section 7) |
| X (Twitter) n'a plus d'offre gratuite : l'API est payée à l'usage, par crédits prépayés, et la lecture des tendances consomme des crédits ([data365](https://data365.co/guides/twitter-api-limitations-and-pricing), [postproxy](https://www.postproxy.dev/blog/x-api-pricing-2026/)). Bluesky expose ses sujets tendance gratuitement (`app.bsky.unspecced.getTrendingTopics`) | Tendances X par l'API officielle, 1 relevé par jour, plafond de 3 $/mois ; Bluesky et Google en complément gratuit |
| Les histoires Reddit lues mot pour mot sont saturées et déclassées ; les versions avec commentaire, analyse ou sous-niche (travail, relations) marchent encore ([shortsfast](https://shortsfast.com/blog/saturated-faceless-youtube-niches-2026/), [kineclip](https://kineclip.com/blog/tiktok-niches-to-avoid-2026/)) | Le format « histoire à la première personne » reste exploitable, mais avec des histoires réécrites à partir de la situation seulement, un angle propre (twist, verdict, question au public) et des sous-niches |
| TikTok demande d'étiqueter le contenu IA réaliste ([shortsfast](https://shortsfast.com/blog/is-faceless-ai-content-against-youtube-tiktok-tos-2026/), [socialpilot](https://www.socialpilot.co/blog/how-social-media-platforms-handle-ai-slops)) | Confirmation « AI-generated » obligatoire et journalisée pour chaque vidéo publiée (section 8) |
| YouTube a renommé sa règle en « inauthentic content » (juillet 2025) et vise les vidéos répétitives à gabarit fixe ([TNW](https://thenextweb.com/news/youtube-ai-slop-crackdown-faceless-creators-collateral-damage?type=AI)) | Variation du contenu entre vidéos (script, fond, musique, voix), mais charte visuelle fixe par compte |
| API de publication : le mode upload dépose un brouillon dans la boîte de réception TikTok, mais il faut une application développeur, Login Kit, le scope `video.upload` et une revue de l'application (vérification d'URL, vidéo de démonstration) ; un client non audité ne publie en direct qu'en privé ([TikTok Developers](https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content), [App Review Guidelines](https://developers.tiktok.com/docs/en/app-review-guidelines), [bundle.social](https://bundle.social/blog/tiktok-api-approval)) | **V1 sans API** : livraison par Syncthing. Demande d'application développeur lancée dès la V0 en parallèle ; dépôt en brouillon par API en V2 si elle est acceptée |
| Pas d'API officielle des tendances ; le Creative Center se lit par scraping, avec des flux musique instables ([Apify](https://apify.com/eunit/tiktok-trends-scraper)) | Veille multi-sources, tolérante aux pannes |
| MoneyPrinterTurbo, short-video-maker, Pixelle-Video automatisent déjà script + voix + stock + sous-titres ([opensourcealternatives](https://www.opensourcealternatives.to/item/moneyprinterturbo), [short-video-maker](https://www.sourcepulse.org/projects/2566801)) | On s'inspire de leurs idées et on reprend des extraits de code sous licence MIT, sans fork (section 9) ; la valeur ajoutée est le module Recette |
| Kokoro (82M, Apache 2.0) tourne vite sur CPU ; Chatterbox (MIT) clone mieux mais veut un GPU ; F5-TTS a des poids non commerciaux ([localaimaster](https://localaimaster.com/blog/kokoro-vs-xtts-vs-chatterbox), [scriptbyai](https://www.scriptbyai.com/best-open-source-tts-models/)) | Kokoro par défaut ; F5-TTS et XTTS exclus |

Les chiffres de RPM varient beaucoup selon les sources (0,40 à 1 $ pour 1 000 vues qualifiées sur TikTok, non vérifié). Ils ne servent pas de base au planning.

## 4. Machine cible

Ton PC peut faire tourner localement la voix, la transcription, l'analyse vidéo et le montage, mais pas la génération d'images ou de vidéos IA : celle-ci passe par des API. Les performances ci-dessous sont **à mesurer en V0** : aucune n'a encore été chronométrée.

| Élément | Détecté | Impact |
| --- | --- | --- |
| CPU | Intel Comet Lake-U (portable, basse consommation) | Temps de rendu d'une vidéo de 75 s en 1080x1920 : **non mesuré**, objectif fixé en V0 |
| GPU | NVIDIA MX250, 2 Go, pilote non chargé + Intel UHD | Inutilisable pour Flux, Wan ou Chatterbox. La MX250 n'aurait pas d'encodeur vidéo matériel (NVENC) : encodage via QSV Intel, à confirmer en V0 |
| RAM | 15 Go, dont environ 3 Go libres au moment du test | **Contrainte principale.** Un seul modèle lourd chargé à la fois (voir exigence mémoire) ; fermer le navigateur pendant les traitements |
| Disque | 260 Go libres | Largement suffisant ; cache plafonné à 20 Go (section 10) |
| Outils | Python 3.10, FFmpeg, Docker, Node déjà installés | Installation simplifiée |

**Exigence de profil** : l'application détecte le matériel au démarrage et choisit un profil. Profil « Léger » (ton PC) : tout en CPU, sans PyTorch, visuels par API ou banque d'images. Profil « GPU » (RTX 8 Go et plus, ou GPU loué) : ComfyUI local pour images et vidéo IA, Demucs et Chatterbox activables. Changer de machine ne doit demander aucune modification de code.

**Exigence mémoire (profil Léger)** : les étapes lourdes (transcription, OCR, voix, encodage) s'exécutent **l'une après l'autre**, jamais en parallèle, et chaque modèle est déchargé après usage. Objectif de pic de mémoire : moins de 2,5 Go (non mesuré, vérifié en V0). Le profil Léger n'utilise que des moteurs ONNX ou CTranslate2 (faster-whisper, RapidOCR, kokoro-onnx), pas PyTorch, pour réduire la mémoire et simplifier l'installation.

## 5. Architecture

Tout passe par la recette : les trois entrées produisent une recette JSON, et le moteur de génération ne lit que des recettes.

&#91;embedded content: architecture · 3 entrées, recette, génération, publication\]

Les statistiques de chaque vidéo publiée reviennent noter la recette qui l'a produite. En V1 ces stats sont saisies à la main (5 champs recopiés depuis TikTok Studio, voir section 8) ; en V2 elles sont récupérées automatiquement. Le mode un clic privilégie ensuite les recettes les mieux notées. Les appels LLM passent tous par une passerelle unique (LiteLLM).

## 6. Module Recette (reverse engineering)

Tu colles un lien TikTok (ou déposes un fichier .mp4) et tu obtiens en moins de 6 min (provisoire) une fiche recette réutilisable. La vidéo source sert uniquement à l'analyse et est supprimée juste après ; seules les mesures sont gardées (.cache/analyses/).

**Recettes écrites à la main d'abord.** Avant que ce module existe, la V0 fournit 4 recettes écrites à la main (histoire à la première personne, faits étonnants, mystère non résolu, top 5). On peut ainsi tester la génération dès la première semaine. Le module Recette arrive ensuite et doit produire des recettes au moins aussi bonnes que celles écrites à la main.

**Étapes d'analyse** (exécutées l'une après l'autre, voir l'exigence mémoire)

1. Téléchargement : yt-dlp (lien) ou import de fichier ; métadonnées récupérées (durée, vues, likes, date de publication, légende, hashtags, son utilisé).
2. Transcription mot par mot avec horodatage et détection de la langue : faster-whisper (modèle small.en int8 sur CPU, anglais par défaut, avec détection des passages parlés). Le modèle multilingue n'est pas installé.
3. Découpage en plans : PySceneDetect → nombre de plans, durée moyenne, rythme des coupes.
4. Texte à l'écran : RapidOCR sur une image à chaque changement de plan et une image toutes les 2 s (et non plus 1 image par seconde) → police, position, couleur, nombre de mots affichés à la fois.
5. Audio : tempo (librosa), présence de bruitages, et volume de la musique estimé en comparant les passages avec et sans voix (détectés à l'étape 2). La séparation voix / musique par Demucs n'est activée qu'en profil GPU ou à la demande.
6. Analyse visuelle et synthèse en **un seul appel à Claude** : 6 à 10 images clés, la transcription et les mesures des étapes 3 à 5 → type de fond, cadrage, palette, mouvements, puis la recette JSON et un résumé lisible « pourquoi ça marche » (hook, boucle de curiosité, payoff, appel à l'action). Codée : la synthèse est faite par Claude Sonnet 5.5. La sortie est validée, les valeurs sont ramenées dans leurs bornes, et un 2e appel part avec les erreurs si elle reste invalide.

**Cas d'échec et cas particuliers**

| Situation | Comportement attendu |
| --- | --- |
| Lien mort, vidéo privée ou supprimée | Message clair en moins de 30 s (« vidéo inaccessible »), aucune erreur technique affichée, proposition d'importer le fichier .mp4 à la main |
| yt-dlp bloqué par TikTok | 1 nouvelle tentative, puis message « téléchargement bloqué ». yt-dlp utilise l'empreinte TLS de Chrome via curl_cffi (extra `yt-dlp[curl-cffi]`) : c'est ce qui évite le blocage. Si l'empreinte est absente ou incompatible, message clair (`uv sync`) et import du fichier à la main |
| Vidéo sans voix (musique seule, texte à l'écran) | La transcription ne trouve aucun passage parlé : la recette passe en format `texte_ecran`. Le script est reconstruit à partir du texte lu par l'OCR, et la recette propose une voix off en option |
| Vidéo dans une autre langue que l'anglais | La langue source est notée dans la recette. On garde la structure, le rythme et le style ; le script généré reste en anglais (`language: "en"`) |
| Vidéo de moins de 15 s ou de plus de 10 min | Avertissement : la recette est produite mais signalée « peu fiable » |
| Recette JSON invalide (refusée par Pydantic) | 1 nouvel appel à Claude avec l'erreur ; après un deuxième échec, la recette est ouverte dans l'éditeur, avec les champs en faute surlignés |

**Mesures et constat du 20 novembre 2026** : une vidéo de 40 s est analysée de bout en bout pour 0,035 $ d'API. Le blocage TikTok observé le même jour (« Unexpected response from webpage request », puis 403 sur le fichier) venait de yt-dlp sans empreinte de navigateur, pas de TikTok : avec l'extra `yt-dlp[curl-cffi]` et l'impersonation Chrome, le téléchargement d'une vidéo publique a été validé. TikTok peut modifier ses protections à tout moment ; l'import manuel du .mp4 reste le repli, et le message d'erreur explique quoi faire.

**Format de la recette, version 3** (schéma validé par Pydantic, modifiable à la main). Une recette = un bloc **`contenu`** (de quoi on parle et comment on le raconte) + un bloc **`visuel`** (à quoi ça ressemble et comment ça sonne). Le rédacteur du script ne lit que `contenu` ; le générateur d'animations ne lit que `visuel` et le script.

```json
{
  "schema_version": 3,
  "recipe_id": "faits-etonnants",
  "source": {"url": "https://www.tiktok.com/@x/video/123", "views": 2400000, "duration_s": 34, "language": "en"},
  "contenu": {
    "niche": "amazing_facts",
    "themes": ["science", "animaux", "histoire"],
    "sources_acceptees": ["tendance_x", "tendance_bluesky", "google_trends", "actualite"],
    "angle": "3 faits vérifiables qui ont l'air faux",
    "transformation": "tirer 3 faits sourcés du sujet du jour, les reformuler, ajouter un verdict perso",
    "format": "narration",
    "language": "en",
    "target_duration_s": [28, 40],
    "structure": [
      {"part": "hook", "seconds": [0, 3], "pattern": "affirmation surprenante et vérifiable"},
      {"part": "list_item", "seconds": [3, 12]},
      {"part": "cta", "seconds": [30, 34], "pattern": "which one did you know?"}
    ],
    "script_style": {"pov": "narrator", "wpm": 180, "reading_level": "grade_6", "tone": "curieux, rythmé"},
    "posting": {"hashtags": ["#facts", "#didyouknow", "#learnontiktok"], "best_hours_utc": [14, 18, 23]}
  },
  "visuel": {
    "moteur": "html",
    "ambiance": "fond sombre violet animé, particules dorées, accent jaune, emojis en grand",
    "fond": "anime",
    "scene_defaut": "mot-clé en très gros au centre, apparition élastique",
    "scenes": {
      "hook": "gros chiffre qui rebondit, puis le titre quand la voix le dit",
      "list_item": "badge FACT #n, emoji, animation propre au fait déclenchée sur son mot-clé",
      "cta": "la question en grand, rappel des emojis"
    },
    "rythme": {"changement_s": 2.5, "declencheur": "mots_cles", "zoom_punch": true},
    "sous_titres": {"style": "word_by_word", "words_on_screen": 2, "position": "center", "use_channel_charter": true},
    "voix": {"gender": "male", "age": "25-35", "speed": 1.05, "engine_hint": "elevenlabs:<voice_id>"},
    "audio": {"music_mood": "upbeat curious", "music_db": -20, "sfx": ["pop_on_item"]}
  },
  "why_it_works": "Promesse tenue dès la première seconde, trois faits sourcés, question finale pour les commentaires."
}
```

**Qui remplit quoi à l'extraction.** La transcription et la synthèse de Claude remplissent `contenu`, mais seulement le thème, la structure et l'angle : l'histoire de la vidéo source n'est jamais reprise. Les images clés, l'OCR et le découpage en plans remplissent `visuel`.

**Mélange.** On peut générer avec le contenu d'une recette et le visuel d'une autre (`trendforge recette combiner <contenu> <visuel>`). Une partie de la structure que le visuel ne décrit pas reçoit `scene_defaut`. Avec 5 recettes, cela donne 25 combinaisons, ce qui limite l'effet gabarit.

**Filtre des sujets.** `sources_acceptees` dit quelles fiches sujet peuvent nourrir le contenu : une histoire à la première personne ne prend que des histoires collées, un top 5 que des tendances.

Les recettes de la version 2 (champs à plat) sont converties automatiquement au chargement ; les champs nouveaux sont alors marqués « à compléter ».

**Bibliothèque de recettes** : chaque recette est enregistrée (SQLite) et exportée aussi en fichier JSON dans un dossier `recettes/` (facile à sauvegarder ou versionner avec git). Elle est notée par les performances des vidéos qu'elle a produites et peut être dupliquée.

## 7. Génération

Deux entrées, un seul moteur : le mode un clic remplit tout depuis la recette ; le mode personnalisé laisse décrire le format en texte libre, que Claude convertit en recette.

**Mode « Générer » (un clic)**

- Tu choisis une tendance ou une recette, tu règles le nombre de vidéos (1 à 5), tu appuies sur Générer.
- Le sujet est pris dans la **réserve de fiches sujet** (voir « Sources de sujets » ci-dessous). On prend d'abord les tendances du jour qui collent à la recette, puis les histoires que tu as collées, de la plus récente à la plus ancienne.
- Dédoublonnage : un sujet est écarté si son résumé est trop proche d'une vidéo déjà faite (similarité cosinus des embeddings supérieure à 0,85).

**Sources de sujets (le sujet part toujours d'un fait réel)**

Chaque vidéo part d'une **fiche sujet** tirée d'une source réelle, jamais d'une idée inventée à partir de rien. Une fiche contient :

- le type de source, le lien et la date ;
- un résumé neutre ;
- les éléments clés : personnages, conflit, détail marquant, rebondissement ;
- pour une tendance, 2 ou 3 posts ou articles qui expliquent pourquoi on en parle.

Les fiches sont rangées dans une réserve, consultable dans l'écran Créer.

| Source | Ce qu'on en tire | Comment on y accède | Version |
| --- | --- | --- | --- |
| Histoires de forums type Reddit (AITA, relations, travail, petty revenge, histoires d'horreur vécues) | La situation : qui, quel conflit, quel rebondissement | **Tu colles le lien ou le texte** d'un post que tu as lu. Depuis le téléphone, tu le partages vers un dossier `idees/` synchronisé par Syncthing. L'application ne lit jamais Reddit d'elle-même | V1a |
| Tendances X (Twitter) | Les sujets dont on parle aujourd'hui et les posts les plus vus sur chacun | API X officielle, payée à l'usage, 1 relevé par jour. Plafond de 3 $/mois ; au-delà, le relevé saute un jour | V1b |
| Tendances Bluesky | Même chose, gratuitement | API publique `app.bsky.unspecced.getTrendingTopics`, sans compte | V1b |
| Google Trends + Google Actualités | Les recherches qui montent, et des articles pour comprendre le contexte | pytrends, flux RSS de Google Actualités | V1b |
| Hashtags TikTok | Ce qui marche déjà sur TikTok | Veille de la section 8 | V2 |
| Sujet inventé à partir de rien | — | **Désactivé par défaut**. Uniquement si tu l'actives dans Réglages, quand la réserve est vide | — |

**Règles de transformation**

- **Histoires de forum** :
  - un premier appel à Claude réduit le post à une fiche situation. Le script est écrit **à partir de la fiche seulement, jamais à partir du texte du post** ;
  - le script change les prénoms, le lieu et le métier, plus au moins 2 détails, et ajoute un angle propre (verdict, rebondissement, question au public) ;
  - le contrôle de similarité (définitions ci-dessous) s'applique au texte du post, avec les mêmes seuils que pour une source vidéo ;
  - jamais de pseudo, de capture d'écran ni de logo Reddit. La légende ne dit jamais que l'histoire est vraie.
- **Tendances** :
  - formats : explication (« ce qui se passe avec… »), réaction avec un avis, top ou chronologie ;
  - les faits viennent uniquement des 2 ou 3 sources de la fiche, et ces sources sont gardées dans le journal ;
  - une tendance de plus de 48 h est retirée de la réserve ;
  - la modération écarte ce qui est sensible : décès, drames, politique, accusations contre une personne privée, rumeurs non confirmées.

**Mode personnalisé**

- Champ texte libre, par exemple : « Histoire d'horreur courte, voix masculine grave, fond forêt sombre en images IA, 70 s, sous-titres rouges, fin ouverte ».
- Le sujet : une fiche de la réserve, un lien ou un texte collé, ou une tendance précise.
- Options : partir d'une recette existante et ne modifier que certains champs, fournir son propre script, choisir la voix, la musique et les visuels à la main.
- Aperçu de la recette générée avant lancement, avec son coût estimé.

**Pipeline de génération (identique pour les deux modes)**

1. **Estimation du coût** : si elle dépasse 0,50 $ ou le budget restant du jour ou du mois, le lancement est refusé, avec la raison affichée.
2. **Script** : un seul fournisseur, Claude, via LiteLLM. Claude Haiku rédige 3 variantes ; Claude Sonnet choisit et améliore la meilleure (hook, rythme, originalité). Longueur calculée sur le débit mesuré de la voix : ElevenLabs lit environ 140 mots/min à vitesse 1,0 (voix Liam), soit environ 175 mots pour 75 s.
3. **Contrôle qualité du script** (bloquant, définitions ci-dessous) : score de hook, similarité avec la source, similarité avec tes vidéos passées, modération.
4. **Voix** : ElevenLabs par défaut (version 3), qui renvoie aussi l'horodatage de chaque mot ; kokoro-onnx en local en secours, horodaté par faster-whisper.
5. **Contrôle de durée** (boucle bornée) : la cible dépend du type de vidéo (21 à 45 s pour une courte, 61 à 90 s pour une longue).
   - Hors cible : le script est rallongé ou resserré par le LLM, puis la voix est régénérée. **1 réécriture au maximum, car chaque nouvelle voix consomme du quota ElevenLabs.**
   - Toujours hors cible mais à moins de 8 % de la fourchette : ajustement de la vitesse de la voix (±8 % au maximum).
   - Sinon : la vidéo passe en statut « échec durée » dans la file, avec le script et la voix conservés. **Aucun export.**
6. **Visuels** selon le bloc visuel de la recette. Moteur « stock » ci-dessous ; le moteur HTML, par défaut, est décrit après cette liste :
   - Pexels / Pixabay ;
   - images IA (API) animées en Ken Burns : 5 au maximum en variante Standard ;
   - gameplay, **uniquement depuis la liste des jeux validés** (section 13). Tant que cette liste est vide, les recettes « gameplay » utilisent des vidéos « satisfaisantes » de Pexels.
7. **Sous-titres** animés mot par mot (fichier ASS généré depuis les horodatages), avec la police et les couleurs de la charte.
8. **Musique** libre (bibliothèque locale, Pixabay Music) ajustée à -22 dB sous la voix, plus bruitages ; volume global normalisé à -14 LUFS.
9. **Montage et rendu** : FFmpeg piloté directement (graphe de filtres généré depuis la recette), 1080x1920, 30 i/s, H.264 via QSV Intel (ou libx264 en secours), environ 8 Mbit/s. MoviePy n'est gardé que si la V0 montre qu'il n'est pas beaucoup plus lent.
10. **Contrôles automatiques avant validation** (bloquants) : durée, résolution, volume, sous-titres dans la zone visible (hors des boutons TikTok), **absence de contenu de la source** (empreinte, ci-dessous) et coût réel inférieur au plafond.
11. **Métadonnées** : titre, légende, 3 à 5 hashtags, couverture (image clé + texte), et la mention « AI-generated : à cocher » en tête du fichier légende.
12. **File de validation** : la vidéo attend ton accord. Les contrôles 3 et 10 font le tri technique ; **le jugement éditorial (est-ce que c'est bon ?), c'est toi**, en lisant la vidéo dans la file.

**Moteur visuel HTML (par défaut depuis la version 3)** : il remplace les étapes 6, 7 et 9 quand `visuel.moteur` vaut `html`.

1. Claude Opus 5.5, en effort moyen (ton choix), reçoit le bloc visuel, le script découpé par partie et l'horodatage des mots, et écrit une page HTML 1080x1920 (CSS, SVG, canvas, emojis).
2. **Règle de rendu** : tout l'affichage est une fonction pure du temps, `dessiner(t)`. Aucune animation CSS, aucun minuteur : c'est ce qui garantit un rendu identique à chaque fois et calé sur la voix.
3. Les animations se déclenchent sur les mots prononcés (`rythme.declencheur = mots_cles`) : un compteur part quand la voix dit le chiffre, un objet apparaît sur son nom.
4. Chrome sans fenêtre (Playwright, avec le Chrome installé) appelle `dessiner(t)` 30 fois par seconde et capture chaque image ; FFmpeg encode les images avec la voix et la musique.
5. Les sous-titres mot par mot sont dessinés dans la page, avec la police et les couleurs de la charte.

Points forts : texte animé, compteurs, listes, schémas, cartes et chronologies ; rendu unique à chaque vidéo ; aucun risque de reprendre une image de la source. Limite : pas d'images réalistes. Pour un décor réel, la page peut être rendue sur fond transparent et posée sur une vidéo Pexels.

**Mesure du prototype** (20 novembre 2026, `bench/proto_html/`) : 14 s de vidéo, 423 images capturées et encodées en 23 s, soit environ 18 images/s. Une vidéo de 75 s demanderait donc environ 2 min de capture (extrapolation, à confirmer). Le HTML du prototype était écrit à la main.

**Mesure du moteur HTML écrit par Claude** (20 novembre 2026, vidéo de 40 s) : la page écrite par Opus 5.5 en effort moyen coûte 0,38 $. En effort élevé : 0,74 $. Sonnet 5.5 coûte moins cher mais donne un rendu visuellement plus pauvre. Capture : environ 18 images/s, soit 70 s pour une vidéo de 40 s.

**Contrôles de la page** (automatiques, après l'écriture) :

- erreur JavaScript ou page vide : une réécriture par Claude ;
- texte hors de la zone sûre, ou textes qui se chevauchent plus de 0,35 s : avertissements affichés dans l'onglet À publier, sans réécriture payante.

**Définitions des contrôles qualité (rendues testables)**

- **Similarité avec la source** (vidéo d'origine de la recette, ou texte d'un post collé) :
  - recouvrement lexical : moins de 3 % des suites de 5 mots du script se retrouvent dans la source ;
  - recouvrement de sens : moins de 10 % des phrases du script ont une similarité cosinus supérieure à 0,85 avec une phrase de la source (embeddings `bge-small-en-v1.5`, en local, via fastembed) ;
  - si l'un des deux seuils est dépassé, le script est réécrit (2 fois au maximum), puis la vidéo est signalée.
- **Similarité avec tes vidéos passées** : la similarité cosinus entre l'embedding du script complet et celui de chaque script déjà publié doit rester sous un seuil, **0,90 à titre provisoire**. Au-delà, le script est réécrit. Deux scripts de la même recette ont la même structure, donc une similarité élevée même s'ils racontent autre chose : le seuil est étalonné en V0 (section 12).
- **Score de hook** (0 à 10), noté par Claude Haiku selon une grille fixe de 5 critères à 2 points : il ouvre une question sans y répondre ; il contient un détail concret (chiffre, lieu, objet) ; il tient en 10 mots au plus et se lit en 3,5 s au plus au débit de la recette (à 175 mots/min, 10 mots prennent environ 3,4 s) ; il annonce un enjeu ou un conflit ; sa promesse est tenue plus loin dans le script (pas de piège à clics). Le critère de longueur est aussi vérifié par calcul. Seuil : 7/10, sinon le hook seul est régénéré (2 fois au maximum). Étalonnage en V0 : tu notes 20 hooks toi-même, et la note de Claude doit être à 2 points ou moins de la tienne pour au moins 16 d'entre eux. Sinon, on ajuste la grille.
- **Empreinte (absence de la source dans le rendu)** :
  - images : une image du rendu par seconde est comparée à deux images de la source par seconde, par hash perceptuel (pHash 64 bits). Échec si une distance de Hamming est inférieure ou égale à 10 ;
  - son : l'empreinte Chromaprint du rendu est comparée à celle de la source ;
  - les seuils sont validés en V0 par un **témoin positif** : un rendu volontairement truqué, qui contient 5 s de la source, doit être détecté à chaque fois.
- **Modération** : filtre de modération du LLM avant la voix ; un sujet refusé est remplacé par le suivant.

**Charte de chaîne et variation** : chaque compte a une **charte fixe** (une police, une couleur d'accent, un style de sous-titres, 2 ou 3 voix), pour que la chaîne soit reconnaissable. La variation porte sur le **contenu** : script, angle, forme du hook, fond, musique, et la voix choisie parmi celles de la charte. C'est ce qui évite l'effet gabarit sans perdre l'identité visuelle.

## 8. Veille des tendances et publication

La veille propose chaque matin 10 tendances classées par potentiel ; en V1 l'application ouvre les pages d'envoi de TikTok, Instagram Reels et YouTube Shorts, et tu publies en quelques gestes.

**Veille (tâche planifiée, 1 fois par jour)** — V2

- Sources vidéo : TikTok Creative Center (hashtags et vidéos du marché US, lecture de la page) et recherche par hashtag via yt-dlp. Les tendances X, Bluesky et Google alimentent déjà la réserve de sujets dès la V1b (section 7) ; la veille V2 les croise avec les vidéos TikTok qui marchent sur le même sujet.
- **Historique** : chaque passage enregistre les vues de chaque vidéo et de chaque hashtag suivis. C'est cet historique qui permet de calculer la croissance.
- **Score de tendance** (0 à 1) = 0,5 × vitesse + 0,3 × adéquation à la niche faceless + 0,2 × facilité de reproduction.
  - Vitesse : vues ÷ heures depuis la publication, convertie en rang (percentile) parmi les vidéos du jour.
  - Adéquation et facilité : notées de 0 à 1 par le LLM.
  - **Règle de démarrage** : tant qu'il y a moins de 3 relevés pour une vidéo, la vitesse est calculée depuis la date de publication fournie par yt-dlp. À partir de 3 relevés, on utilise la croissance mesurée entre les relevés. Le score est donc calculable dès le premier jour.
- Pour les 3 meilleures, la recette est extraite automatiquement en tâche de fond : au réveil, tu n'as plus qu'à appuyer sur Générer.
- Chaque source est un plugin isolé : si TikTok change sa page, seule cette source tombe, l'application continue.

**Publication semi-automatique**

V1 (sans API, en place depuis le 20 novembre 2026) : publication semi-automatique vers TikTok, Instagram Reels et YouTube Shorts.

1. Tu valides la vidéo dans l'onglet À publier (lecture, légende modifiable).
2. Le bouton « Ouvrir les pages d'envoi » ouvre dans ton Chrome la page d'envoi de chaque plateforme cochée (TikTok Studio upload, instagram.com, youtube.com/upload). Il ouvre aussi le dossier de la vidéo et copie la légende.
3. Sur chaque page : tu glisses video.mp4, tu colles la légende, tu **coches l'étiquette « contenu généré par IA »** et tu enregistres en brouillon.
4. **Confirmation** : un bouton par plateforme marque la vidéo publiée ; la date est gardée dans le journal.

La publication entièrement robotisée reste hors périmètre. À vérifier : l'enregistrement en brouillon depuis le web sur TikTok et Instagram. YouTube garde la vidéo en brouillon tant qu'elle n'est pas publiée.

V2 (si l'application développeur TikTok est acceptée) : dépôt en brouillon via la Content Posting API (mode upload, scope `video.upload`) ; la vidéo arrive dans ta boîte de réception TikTok. L'étiquette IA et la confirmation restent identiques. Si l'API permet de marquer le contenu comme généré par IA, ce marquage est activé à chaque envoi (à vérifier dans la documentation). Les pages d'envoi web restent le plan B.

**Démarche développeur TikTok** (lancée en V0, car la revue prend du temps) : créer l'application, préparer une page web simple avec politique de confidentialité et conditions d'utilisation, vérifier l'URL, enregistrer la vidéo de démonstration demandée par la revue. Une demande refusée ne bloque rien : la V1 fonctionne sans.

**Calendrier** : créneaux recommandés pour le public US (environ 14 h, 18 h et 23 h UTC, à ajuster selon tes statistiques), avec rappels par notification.

**Statistiques**

- V1 : formulaire de saisie manuelle par vidéo, à remplir environ 48 h après publication, à partir de TikTok Studio. 5 champs : vues, rétention à 3 s, % de vues complètes, likes, abonnés gagnés. C'est facultatif, mais c'est nécessaire pour noter les recettes et mesurer les objectifs de la section 1.
- V2 : récupération automatique (API Display ou export), même schéma de données.

## 9. Stack technique

Tout est en Python, local, et open source sauf le LLM et les images IA, branchés par API et interchangeables.

| Fonction | Choix principal | Licence / coût | Alternative |
| --- | --- | --- | --- |
| Interface | Interface web locale NiceGUI (uv run trendforge interface), ouverte dans une fenêtre Chrome sans barre d'adresse (mode --app) ; pywebview n'est pas utilisé | MIT, gratuit | Tauri + React (V3) |
| Back-end, file de tâches | FastAPI + Huey + SQLite | MIT, gratuit | RQ ; Celery + Redis |
| Téléchargement vidéo | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense, gratuit | Import manuel du fichier |
| Transcription | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) small.en int8 (CTranslate2, sans PyTorch) | MIT, gratuit | whisper.cpp |
| Détection des plans | PySceneDetect | BSD, gratuit | OpenCV maison |
| OCR | RapidOCR (ONNX) | Apache 2.0, gratuit | Tesseract (PaddleOCR retiré : trop lourd) |
| Analyse audio | librosa ; Demucs seulement en profil GPU ou à la demande | ISC / MIT, gratuit | — |
| Analyse visuelle et recette | Claude Sonnet 5.5 (vision), un seul appel par vidéo | API payante, 0,035 $ mesuré pour une vidéo de 40 s | Qwen2.5-VL local en profil GPU |
| Rédaction des scripts | Claude Haiku (variantes) + Claude Sonnet (version finale) : un seul fournisseur, une seule clé | API payante, quelques centimes par vidéo | DeepSeek ou Ollama + Qwen local, via LiteLLM |
| Embeddings (similarité, dédoublonnage) | [fastembed](https://github.com/qdrant/fastembed) + bge-small-en-v1.5 (ONNX, CPU) | Apache 2.0 / MIT, gratuit | sentence-transformers (profil GPU) |
| Empreintes (contrôle anti-source) | imagehash (pHash) + Chromaprint (`fpcalc`) | BSD / LGPL, gratuit | — |
| Voix | ElevenLabs (API), qui renvoie l'horodatage des mots | Environ 570 caractères par vidéo courte de 40 s (mesuré) ; offre gratuite de 10 000 caractères/mois, abonnement payant pour monétiser | Kokoro-82M via kokoro-onnx, local et gratuit (secours) ; Piper (MIT) |
| Clonage de voix (profil GPU) | Chatterbox | MIT, gratuit | — |
| Images IA | API (Higgsfield, déjà connecté, ou fal.ai/Replicate) | Payant à l'image | ComfyUI + Flux schnell en profil GPU |
| Vidéos de fond | Pexels et Pixabay (API gratuites) + bibliothèque locale de jeux validés | Gratuit, licence libre d'usage | Gameplay enregistré par toi |
| Sous-titres | Fichier ASS généré + libass dans FFmpeg | Gratuit | pycaps |
| Montage, rendu | FFmpeg piloté directement (graphe de filtres généré en Python) | LGPL, gratuit | MoviePy 2, si la V0 le justifie |
| Animations (moteur HTML) | Page HTML écrite par Claude Opus 5.5 (effort moyen), filmée image par image par Chrome sans fenêtre (Playwright), encodée par FFmpeg | Apache 2.0, gratuit (hors appel à Claude) | Remotion (React), Motion Canvas |
| Sources de sujets | API X officielle (tendances), API publique Bluesky, pytrends, flux RSS Google Actualités (feedparser), dossier `idees/` synchronisé | X : payé à l'usage, plafonné à 3 $/mois ; le reste gratuit | Fournisseur tiers de données X (twitterapi.io, Apify) |
| Veille vidéo | yt-dlp, lecture du Creative Center | Gratuit | Apify (payant) |
| Publication | V1 : pages d'envoi web de TikTok, Instagram et YouTube ouvertes dans Chrome ; V2 : Content Posting API TikTok (brouillon) | Gratuit | — |
| Notifications | ntfy | Apache 2.0, gratuit | Telegram bot |
| Installation | Script install.sh + uv | Gratuit | Docker Compose ; AppImage (V3) |

**Réutilisation (décision)** : **pas de fork de MoneyPrinterTurbo.** Son architecture (interface Streamlit, configuration propre, montage MoviePy) ne correspond pas au modèle « tout passe par une recette JSON ». On lit son code pour s'en inspirer et on reprend des fonctions précises (sous-titres, recherche Pexels) en citant la licence MIT.

**Couche LLM** : une interface unique (LiteLLM) pour appeler Claude, ou un autre modèle en secours, avec la même fonction ; le modèle est choisi par tâche dans les réglages. Les clés API sont stockées dans le trousseau du système (keyring), jamais dans le code.

## 10. Interface, exigences non fonctionnelles, coûts

L'interface existe : une application NiceGUI locale en 4 onglets, lancée par `uv run trendforge interface`. Une vidéo complète doit sortir en moins de 15 min (provisoire) sur ton PC ; une vidéo courte de 40 s coûte environ 0,39 $ de Claude en variante Standard (mesuré), plus la voix ElevenLabs.

**Écrans** (en place au 20 novembre 2026) : l'application s'ouvre dans une fenêtre Chrome sans barre d'adresse (mode --app). Le quota ElevenLabs du mois s'affiche en haut.

1. **Recettes** : historique des recettes avec date d'extraction, nombre de vidéos produites et publiées, détails contenu et visuel, archivage. Nouvelle recette depuis un lien TikTok ou un fichier .mp4.
2. **Générer** :
   - Automatique : une recette ou « au hasard », 1 à 5 vidéos ; les sujets neufs sont pris dans la réserve.
   - Personnalisé : contenu d'une recette × visuel d'une autre ; sujet de la réserve ou texte collé, réduit en fiche par Claude ; consignes libres transmises au rédacteur et à l'animateur ; script imposé en option ; estimation du coût.
3. **À publier** : lecteur vidéo, avertissements de mise en page, script, légende modifiable et copiable, boutons Valider, Rejeter et Supprimer, filtres Non publiées, Publiées et Rejetées.
4. **Sujets** : chercher les tendances, coller une histoire, retirer un sujet.

En bas de page, une file de tâches traite les tâches longues une par une (profil Léger) et affiche leur journal. Encore à faire : Réglages (clés API, profil matériel, phase du compte, charte, budgets, comptes) et Tendances (V2). NiceGUI dans Chrome remplace la séquence prévue « Typer puis NiceGUI + pywebview ».

**Exigences non fonctionnelles**

- Installation en une commande sur Ubuntu 22.04 ; fonctionne hors ligne sauf pour les appels API.
- Reprise après erreur : chaque étape du pipeline est mise en cache, une regénération ne refait que l'étape modifiée.
- Mémoire : objectif de pic inférieur à 2,5 Go en profil Léger, vérifié en V0 (section 4).
- **Budget** :
  - Plafonds réglables dans Réglages : par vidéo (0,50 $, maximum autorisé), par jour et par mois.
  - Compteur de dépenses API par jour et par mois. Alerte ntfy à 80 % du plafond mensuel.
  - Avant chaque appel payant, le coût estimé est comparé au budget restant.
  - **Plafond atteint en pleine génération** : la vidéo passe en statut « en pause — budget » à l'étape en cours. Rien n'est perdu : les étapes déjà payées sont en cache. Elle reprend automatiquement le lendemain (plafond journalier) ou le mois suivant (plafond mensuel), ou tout de suite si tu relèves le plafond.
- **Fichiers et stockage** :
  - cache plafonné à 20 Go, les fichiers les plus anciens sont purgés en premier ;
  - vidéos sources supprimées juste après l'analyse, seules les mesures sont gardées ;
  - vidéos rendues supprimées 30 jours après publication, en gardant les métadonnées, le script et la recette ;
  - sauvegarde automatique quotidienne de la base SQLite (7 copies gardées) ;
  - recettes exportées en JSON dans `recettes/`.
- Journal : chaque vidéo garde sa recette, sa fiche sujet, ses prompts, ses modèles, ses sources factuelles, le résultat des contrôles, son coût, le temps humain passé et la confirmation de l'étiquette IA (traçabilité et preuve d'originalité).
- Code modulaire : chaque brique (voix, visuels, LLM, source de sujets ou de tendances, publication) est un plugin remplaçable.

**Coûts par vidéo** (vidéo courte de 40 s mesurée le 20 novembre 2026 ; vidéo longue de 75 s estimée ; prix des API à revérifier)

| Poste | Gratuite | **Standard (défaut), courte de 40 s** | **Standard (défaut), longue de 75 s** | Premium (sur demande) |
| --- | --- | --- | --- | --- |
| Script (Claude) | environ 0,01 $ (Haiku seul) | environ 0,01 $ (mesuré) | 0,01 à 0,05 $ (estimé) | comme Standard |
| Analyse de recette (amortie sur 10 vidéos) | 0 $ (recette écrite à la main) | environ 0,004 $ (0,035 $ mesuré par analyse) | environ 0,004 $ | environ 0,004 $ |
| Animations HTML (Claude Opus 5.5, effort moyen) | — (moteur stock) | environ 0,38 $ (mesuré) | page plus longue : peut dépasser 0,50 $ à elle seule (à mesurer) | comme Standard |
| Voix | 0 $ (Kokoro) | environ 570 caractères ElevenLabs (mesuré) | environ 1 100 caractères ElevenLabs (estimé) | comme Standard |
| Visuels | 0 $ (Pexels) | 0 $ (tout est dessiné en HTML) | 0 $ | environ 0,10 $ (quelques images IA en fond) |
| Musique, montage, publication | 0 $ | 0 $ | 0 $ | 0 $ |
| **Total** | **environ 0,01 $** | **environ 0,39 $ de Claude + 570 caractères (mesuré)** | **risque de dépasser 0,50 $ (à mesurer)** | **Standard + environ 0,10 $** |

Le plafond de 0,50 $ s'applique à toutes les variantes. La vidéo courte mesurée reste dessous ; la vidéo longue a une page plus longue et peut dépasser le plafond : à mesurer avant de la proposer par défaut. ElevenLabs : l'offre gratuite donne 10 000 caractères/mois (environ 17 vidéos courtes) et n'autorise pas l'usage commercial, à ma connaissance : un abonnement payant est nécessaire pour monétiser. À 3 vidéos courtes par jour, compter environ 35 $ de Claude par mois et environ 51 000 caractères ElevenLabs, plus 3 $ au maximum pour les tendances X.

## 11. Risques et conformité

Le risque principal n'est pas technique : c'est un compte jugé « non original » ou « spam ». Les règles ci-dessous sont des exigences bloquantes du logiciel.

| Risque | Probabilité | Parade intégrée |
| --- | --- | --- |
| Vidéos classées non originales, donc non rémunérées | Élevée | Aucun extrait de la source (vérifié par empreinte) ; script réécrit avec un angle propre ; contrôles de similarité chiffrés (section 7) |
| Monétisation inaccessible ou mal rémunérée depuis un compte français | Moyenne | Vérification dans TikTok Studio en V0 ; phase de croissance utile dans tous les cas ; question de la diffusion US suivie en section 13 |
| Croissance trop lente pour atteindre 10 000 abonnés | Élevée | Phase de croissance avec formats courts, points de contrôle à 4 et 8 semaines, règle de changement de niche |
| Droits d'auteur (vidéo, musique, texte) | Moyenne | Musique et stock libres de droits uniquement ; histoires de forum réduites à une fiche situation puis réécrites, avec un contrôle de similarité contre le texte du post ; gameplay limité aux jeux validés |
| Accès Reddit (fermeture de l'API, conditions commerciales) | Certaine | Aucune collecte automatique : tu colles toi-même les histoires lues ; aucune marque ni apparence Reddit à l'écran |
| Tendance mal comprise ou fausse (rumeur, sujet déformé) | Moyenne | Faits tirés uniquement des 2 ou 3 sources de la fiche ; rumeurs non confirmées écartées ; sources gardées dans le journal |
| Sujet tendance sensible (décès, drame, accusation contre une personne) | Moyenne | Filtre de modération dédié aux tendances ; tu valides dans la file |
| Hausse des prix de l'API X | Moyenne | Plafond de 3 $/mois ; Bluesky et Google suffisent si X est coupé ; fournisseur tiers en secours |
| Sanction pour automatisation | Moyenne | Pas de robot de navigateur ; publication à la main (V1) ou par l'API officielle (V2) ; 1 à 3 vidéos par jour maximum |
| Contenu IA non étiqueté | Faible si respecté | Rappel dans la notification et dans la légende ; confirmation obligatoire et journalisée ; rappel si non confirmé sous 24 h |
| Application développeur TikTok refusée ou lente à valider | Moyenne | La V1 n'en dépend pas (Syncthing) |
| Plantage par manque de mémoire | Élevée sans parade | Étapes lourdes l'une après l'autre, moteurs ONNX sans PyTorch, pic mesuré en V0 |
| Style de chaîne non reconnaissable | Moyenne | Charte fixe par compte ; la variation porte sur le contenu |
| Panne d'une source de tendances, yt-dlp bloqué | Élevée | Sources en plugins indépendants ; import manuel du fichier ; mise à jour de yt-dlp en un clic |
| Niche saturée (histoires « Reddit ») | Élevée | Sous-niches, commentaire ajouté, tests A/B de recettes |
| Conditions d'utilisation : télécharger des vidéos TikTok pour analyse est contraire aux conditions de TikTok | Certaine | Usage personnel d'analyse uniquement, suppression sous 7 jours, jamais de réutilisation. À assumer en connaissance de cause |
| Hausse de prix d'une API | Moyenne | Couche LiteLLM : on bascule de modèle dans les réglages |
| Faits inventés présentés comme vrais (formats « faits étonnants », « mystères ») | Moyenne | Source citée et enregistrée dans le journal pour chaque fait ; les histoires réécrites ne sont jamais présentées comme vraies dans la légende |
| Contenu interdit (violence, désinformation) | Faible | Filtre de modération du LLM avant la voix |

## 12. Planning, V0 et critères d'acceptation

On mesure d'abord (V0, 1 à 2 semaines), puis une première vidéo publiable sort en semaine 3. L'outil complet, où l'on colle un lien puis appuie sur Générer, est prêt en semaine 7. Les durées sont des estimations pour un développeur seul aidé de Claude Code.

| Version | Semaines | Contenu | Livrable |
| --- | --- | --- | --- |
| **V0 — mesures** | 1-2 | Mesures sur ton PC, vérifications externes, 4 recettes écrites à la main, prototype du moteur HTML | Fichier `mesures-v0.md` et objectifs chiffrés définitifs |
| **V1a — flux prioritaire** | 3-4 | Module Recette (lien TikTok → recette v3 en deux blocs), bibliothèque et mélange des recettes, moteur HTML écrit par Claude, voix ElevenLabs, fiches sujet à partir d'histoires collées (dossier `idees/`), contrôle anti-copie léger (suites de 5 mots), livraison Syncthing + ntfy | Première vidéo publiable à partir d'un lien TikTok |
| V1b — tendances et interface | 5-7 | Tendances X, Bluesky et Google filtrées par `sources_acceptees`, autres contrôles qualité (hook, similarité de sens, empreinte), file de validation puis autres écrans NiceGUI, saisie des stats, budget | Critères d'acceptation V1 ci-dessous |
| V2 | après | Veille des tendances, dépôt en brouillon par API, stats automatiques, notation des recettes et des combinaisons contenu × visuel | — |
| V3 | après | Profil GPU (local ou loué), Tauri, AppImage | — |

**V0 — ce qu'on mesure et vérifie avant de coder le reste**

1. **Vérifications externes** :
   - éligibilité au Creator Rewards dans TikTok Studio ;
   - lancement de la demande d'application développeur TikTok ;
   - liste des jeux dont l'éditeur autorise la monétisation de vidéos de gameplay.
2. **Rendu** : la même vidéo de 75 s montée avec FFmpeg seul puis avec MoviePy (sous-titres mot par mot, zooms, bruitages), et encodée avec QSV puis avec libx264. Décision : on garde FFmpeg seul, sauf si MoviePy est moins de 1,5 fois plus lent.
3. **Analyse** : durée de chaque étape du module Recette sur 3 vidéos de test.
4. **Mémoire** : pic de mémoire de chaque étape (objectif : moins de 2,5 Go).
5. **Coûts** : coût réel d'un script, d'une analyse et d'une image IA, relevé sur les factures des API.
6. **Étalonnage** :
   - score de hook (20 hooks notés par toi) ;
   - seuils d'empreinte (témoin positif) ;
   - seuil de similarité entre scripts : 10 paires de scripts de la même recette sur des sujets différents, plus 5 paires sur le même sujet. Le seuil retenu doit laisser passer les premières et bloquer les secondes ;
   - si la V0 déborde, l'étalonnage du hook et celui de la similarité passent au début de la V1a.
7. **Règle de mise à jour** : les objectifs de durée deviennent la médiane mesurée × 1,2, arrondie. Ils remplacent les valeurs « (provisoire) » de ce document, et la section 10 est corrigée avec les coûts réels.

**Critères d'acceptation de la V1** (chacun vérifiable par un test ou une mesure)

- [ ] **Recette** : sur un jeu de 10 vidéos de test (dont 1 sans voix et 1 dans une autre langue que l'anglais), au moins 9 recettes JSON valides. Durée médiane d'analyse et pic de mémoire inférieurs aux objectifs de la V0.
- [ ] **Génération** : un clic produit une vidéo 1080x1920 à 30 i/s, dont la durée est dans la fourchette de son type (21 à 45 s ou 61 à 90 s). Durée médiane de génération inférieure à l'objectif de la V0.
- [ ] **Empreinte** : aucune image du rendu n'est à une distance pHash inférieure ou égale à 10 d'une image de la source, et l'empreinte Chromaprint ne trouve aucune correspondance. Le témoin positif est détecté à chaque fois.
- [ ] **Similarité du script** : moins de 3 % de suites de 5 mots communes avec la source, moins de 10 % de phrases au-dessus de 0,85 de similarité cosinus.
- [ ] **Hook** : chaque vidéo exportée a un score de hook d'au moins 7/10, ou elle est signalée après 2 régénérations.
- [ ] **Mode personnalisé** : une description libre devient une recette valide, modifiable avant le lancement.
- [ ] **Sujets réels** : 100 % des vidéos exportées sont liées à une fiche sujet avec une source et une date. Un script tiré d'une histoire collée passe le contrôle de similarité contre le texte du post. Aucune tendance de plus de 48 h n'est utilisée.
- [ ] **Variation** : deux vidéos de la même recette ont une similarité de script inférieure au seuil étalonné en V0, un fond et une musique différents, et respectent la même charte.
- [ ] **Budget** : le coût estimé puis réel de chaque vidéo est affiché ; un lancement qui dépasserait le plafond est refusé ; une vidéo interrompue par le plafond reprend sans repayer les étapes déjà faites.
- [ ] **Cas d'échec** : lien mort, vidéo privée, yt-dlp bloqué et durée hors fourchette après 3 tentatives produisent chacun le comportement prévu (sections 6 et 7), sans erreur non gérée.
- [ ] **Livraison** : la vidéo validée arrive dans le dossier Syncthing du téléphone avec sa légende, et la notification ntfy part dans les 2 min.
- [ ] **Étiquette IA** : 100 % des vidéos marquées « Publié » ont la confirmation « étiquette IA cochée » dans le journal.
- [ ] **Moteur HTML** : sur 10 vidéos générées par Claude, au moins 9 pages s'affichent sans erreur JavaScript ni texte qui déborde de l'écran, et la capture d'une vidéo de 75 s prend moins de 4 min.

## 13. Questions ouvertes

**À trancher en V0**

- [ ] Creator Rewards : l'éligibilité apparaît-elle dans TikTok Studio pour ton compte ?
- [ ] Un compte enregistré en France qui publie en anglais est-il diffusé auprès du public US, et la rémunération dépend-elle du pays des spectateurs ? Faut-il plutôt viser le public francophone ?
- [ ] Gameplay de fond : quels jeux, enregistrés par toi, et leur éditeur autorise-t-il la monétisation ? Tant qu'aucun jeu n'est validé, on utilise des vidéos Pexels.
- [ ] Quel abonnement ElevenLabs, et quelle voix par recette ? Le coût réel par vidéo est à relever sur la première facture.
- [x] Le HTML écrit par l'API Claude est-il aussi propre que celui du prototype ? À tester sur les 4 recettes dès que la clé Anthropic est en place.
- [x] Blocage TikTok du 20 novembre 2026 résolu : la cause était l'absence d'empreinte TLS de navigateur dans yt-dlp. `yt-dlp[curl-cffi]` + impersonation Chrome téléchargent à nouveau une vidéo publique ; l'import manuel du .mp4 reste le repli (section 6).
- [ ] L'enregistrement en brouillon depuis le web fonctionne-t-il sur TikTok et Instagram ? YouTube garde la vidéo en brouillon tant qu'elle n'est pas publiée (section 8).

**À trancher avant la V1b**

- [ ] Un ou plusieurs comptes (une niche par compte) ?
- [ ] Sous-niche de départ : drame relationnel, travail, horreur, mystères, faits étonnants, ou réaction aux tendances ?
- [ ] Tendances X : API officielle (crédits prépayés) ou fournisseur tiers ? Quelle région suivre : États-Unis, Royaume-Uni ou monde ?
- [ ] Quels forums, en plus de Reddit, lis-tu pour trouver des histoires ?

**Déjà tranchées**

- Fork de MoneyPrinterTurbo : **non**, on s'en inspire et on reprend des fonctions précises (section 9).
- API TikTok dès la V1 ou publication à la main : **pages d'envoi web en V1**, demande d'application lancée en V0, API en V2 (section 8).
- Un ou deux LLM : **un seul fournisseur (Claude)**, d'autres modèles restent possibles via LiteLLM (section 9).
- MoviePy ou FFmpeg : **FFmpeg seul par défaut**, confirmé ou non par la mesure de la V0 (section 12).
- Pilote NVIDIA : **inutile**. La MX250 est trop faible pour l'IA et n'aurait pas d'encodeur matériel ; l'encodage passe par QSV Intel. À reconsidérer seulement si la V0 montre que QSV ne fonctionne pas.
- Reddit comme source : **oui, mais à la main**. Tu colles les histoires lues, l'IA n'en garde que la situation, et l'application ne collecte rien automatiquement (API fermée, droits sur les textes).
- Sujets inventés à partir de rien : **non par défaut**. Chaque vidéo part d'une fiche sujet réelle (section 7).
- Visuels : **animations HTML écrites par Claude** par défaut (moteur HTML), Pexels en moteur « stock » ; pas de vidéo entièrement générée par IA, trop chère pour le plafond de 0,50 $ (section 7).
- Recette : **un fichier, deux blocs** (contenu + visuel), mélangeables à la génération plutôt que deux bibliothèques séparées (section 6).
- Voix : **ElevenLabs par défaut**, Kokoro en secours (section 9).
- Animations : **Claude Opus 5.5 en effort moyen**, 0,38 $ mesuré pour 40 s ; l'effort élevé coûte le double, Sonnet 5.5 donne un rendu plus pauvre (section 7).
- Interface : **NiceGUI dans une fenêtre Chrome** (mode --app), sans pywebview (section 10).

## Historique des modifications

### Version 3.1

Mise à jour du 20 novembre 2026 avec l'état réel du code, mesuré le jour même.

| Changement | Où |
| --- | --- |
| Interface en place : application NiceGUI en 4 onglets (Recettes, Générer, À publier, Sujets) dans une fenêtre Chrome, file de tâches et quota ElevenLabs affiché ; pywebview abandonné | Sections 9 et 10 |
| Publication semi-automatique vers TikTok, Instagram Reels et YouTube Shorts par les pages d'envoi web ; un bouton « publiée » par plateforme | Sections 8 et 9 |
| Étape 6 du module Recette codée (Claude Sonnet 5.5), 0,035 $ par analyse ; vidéo source supprimée après l'analyse ; transcription small.en ; téléchargement TikTok réparé (`yt-dlp[curl-cffi]` + impersonation Chrome), import du .mp4 en repli | Sections 6 et 10 |
| Débit mesuré de la voix (140 mots/min) ; 1 réécriture du script au maximum ; animations par Opus 5.5 en effort moyen (0,38 $ pour 40 s) ; contrôles de la page ; capture en 70 s pour 40 s | Section 7 |
| Coûts : vidéo courte mesurée à environ 0,39 $ de Claude + 570 caractères ElevenLabs ; risque de dépasser 0,50 $ en vidéo longue ; offre gratuite ElevenLabs insuffisante pour monétiser | Section 10 |
| Nouvelles questions ouvertes (brouillons web) et nouvelles décisions (Opus 5.5 effort moyen, NiceGUI dans Chrome) ; blocage yt-dlp résolu | Section 13 |

### Version 3

Recentrage du 20 novembre 2026 sur le flux « lien TikTok → recette → vidéo ».

| Changement | Où |
| --- | --- |
| Flux prioritaire en trois gestes : extraire, stocker, générer | En-tête |
| Recette version 3 en deux blocs, `contenu` et `visuel`, mélangeables ; filtre des sujets par `sources_acceptees` ; conversion automatique des recettes v2 | Section 6 |
| Moteur visuel HTML par défaut : Claude écrit une page animée `dessiner(t)`, filmée par Chrome sans fenêtre ; prototype mesuré à environ 18 images/s | Section 7 |
| Voix ElevenLabs par défaut, Kokoro en secours | Sections 7, 9 et 10 |
| Variante Standard réévaluée à environ 0,26 à 0,36 $ par vidéo longue | Section 10 |
| V1a recentrée sur le module Recette, le moteur HTML et ElevenLabs ; tendances et interface en V1b ; nouveau critère d'acceptation « moteur HTML » | Section 12 |

### Version 2.1

| Changement | Où |
| --- | --- |
| Les sujets partent toujours d'un fait réel : histoires de forums type Reddit collées à la main, tendances X, Bluesky et Google, réserve de fiches sujet ; sujet inventé désactivé par défaut | Sections 1, 3 et 7 |
| Règles de transformation : fiche situation, prénoms et détails changés, contrôle de similarité contre le post, tendances de moins de 48 h, modération des sujets sensibles | Section 7 |
| Hook : 10 mots au plus en 3,5 s (15 mots en 3 s étaient impossibles à 175 mots/min) | Section 7 |
| Variante Premium ramenée à 0,43-0,46 $ (6 images IA), pour rester sous le plafond de 0,50 $ ; plafond de 3 $/mois pour les tendances X | Section 10 |
| Pic de mémoire de 2,5 Go présenté comme un objectif, plus comme une mesure | Sections 4 et 10 |
| Seuil de similarité entre scripts rendu provisoire, étalonné en V0 | Sections 7 et 12 |
| V0 passée à 1-2 semaines ; première vidéo en semaine 3, outil complet en semaine 7. Le schéma du planning est remplacé par un tableau à jour | Section 12 |
| Nouveaux risques (tendance fausse, sujet sensible, prix de l'API X) et nouveau critère d'acceptation « sujets réels » | Sections 11 et 12 |

### Version 2 (après l'audit)

Correspondance entre les points de `audit-cahier-des-charges.md` et la version 2.

| Point de l'audit | Correction |
| --- | --- |
| Coûts contradictoires (0,50 $ / 0,10-0,40 $ / 0,25-0,75 $) | Un seul plafond de 0,50 $, appliqué par le logiciel ; trois variantes dont Standard par défaut (sections 1 et 10) |
| Rendu en 2 à 4 min jamais mesuré ; MoviePy lent | FFmpeg seul par défaut ; durées marquées « (provisoire) » et fixées par la V0 (sections 4, 7 et 12) |
| Analyse en moins de 3 min trop optimiste | Objectif provisoire de 6 min ; Demucs retiré du profil Léger ; OCR allégé ; un seul appel à Claude ; étapes l'une après l'autre (sections 4 et 6) |
| Brouillon « sans audit » à moitié vrai | Démarche développeur décrite et lancée en V0 ; V1 sans API (Syncthing) ; API en V2 (sections 3 et 8) |
| Score de tendance sans historique | Relevés quotidiens enregistrés ; règle de démarrage par la vitesse depuis la publication (section 8) |
| Droits sur les histoires Reddit | Reddit retiré : API fermée en mars 2027 et accord commercial nécessaire ; histoires inventées (sections 3 et 7). Remplacé en version 2.1 par les histoires collées à la main |
| Rétention non mesurable en V1 | Saisie manuelle des stats en V1 ; objectifs évalués sur au moins 20 vidéos (sections 1 et 8) |
| Similarité, score de hook et empreinte non définis | Définitions chiffrées, étalonnage et témoin positif (sections 7 et 12) |
| Gameplay présenté comme disponible | Limité aux jeux validés ; Pexels en attendant (sections 7 et 13) |
| Rien sur la phase avant 10 000 abonnés | Nouvelle section 2 : phase de croissance |
| Cas d'échec absents | Tableau des cas d'échec (section 6), boucle de durée bornée (section 7), budget atteint en cours de route (section 10), critère d'acceptation dédié (section 12) |
| Qui juge la qualité finale ? | Contrôles automatiques bloquants + jugement éditorial par toi dans la file (section 7) |
| Où vont les fichiers ? | Règles de cache, de purge, de sauvegarde et d'export (section 10) |
| Deux LLM | Un seul fournisseur (section 9) |
| Quatre outils lourds avec 3 Go de RAM libres | Profil Léger sans PyTorch, exigence mémoire de 2,5 Go (section 4) |
| Fork de MoneyPrinterTurbo | Pas de fork (section 9) |
| Tirage aléatoire de la police et des couleurs | Charte fixe par compte, variation du contenu (section 7) |
| Oubli de l'étiquette « AI-generated » | Confirmation obligatoire et journalisée, rappel sous 24 h (section 8) |
| Autres approches proposées | Recettes écrites à la main en V0 (section 6), FFmpeg seul (section 7), un seul LLM (section 9), ligne de commande d'abord (section 9) |

## Sources

Consultées le 19 novembre 2026 ; la plupart sont des blogs tiers, les règles officielles sont à revérifier dans TikTok Studio, sur developers.tiktok.com et sur redditinc.com.

- [TikTok Developers — Content Posting API, Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post)
- [TikTok Developers — Content Posting API, Upload content](https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content)
- [TikTok Developers — App Review Guidelines](https://developers.tiktok.com/docs/en/app-review-guidelines)
- [TikTok Developers — Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines)
- [bundle.social — TikTok API approval](https://bundle.social/blog/tiktok-api-approval)
- [timetopost — Creator Rewards requirements 2026](https://timetopost.co/blog/tiktok-creator-rewards-requirements-2026/)
- [ttcalculator — How Creator Rewards work 2026](https://ttcalculator.net/blog/how-tiktok-creator-rewards-work-2026/)
- [ttcalculator — Creator Fund countries 2026](https://ttcalculator.net/learn/creator-fund-countries/)
- [shortsfast — Creator Rewards eligibility 2026](https://shortsfast.com/blog/tiktok-creator-rewards-eligibility-2026/)
- [shortsfast — Faceless AI content and ToS 2026](https://shortsfast.com/blog/is-faceless-ai-content-against-youtube-tiktok-tos-2026/)
- [shortsfast — Saturated faceless niches 2026](https://shortsfast.com/blog/saturated-faceless-youtube-niches-2026/)
- [kineclip — TikTok niches to avoid 2026](https://kineclip.com/blog/tiktok-niches-to-avoid-2026/)
- [TechCrunch — Reddit is killing RSS feeds, ending public API access](https://techcrunch.com/?p=3172243)
- [Decrypt — Reddit killing RSS feeds and public API access](https://decrypt.co/379892/reddit-killing-rss-feeds-and-public-api-access-to-fight-ai-scrapers)
- [TechRepublic — Reddit is killing RSS and public API access](https://www.techrepublic.com/article/news-reddit-rss-public-api-shutdown/)
- [ppc.land — Reddit to halt public data API access in March 2027](https://ppc.land/reddit-to-halt-public-data-api-access-in-march-2027-as-14-000-apps-register/)
- [redditapis — Reddit API commercial use explained 2026](https://www.redditapis.com/blogs/reddit-api-commercial-use-licensing-explained-2026)
- [data365 — X API pricing 2026](https://data365.co/guides/twitter-api-limitations-and-pricing)
- [postproxy — X API pricing 2026](https://www.postproxy.dev/blog/x-api-pricing-2026/)
- [Bluesky — getTrendingTopics (client Dart)](https://pub.dev/documentation/bluesky/1.4.1/app_bsky_services/appBskyUnspeccedGetTrendingTopics.html)
- [TechCrunch — Bluesky trending topics](https://techcrunch.com/2024/12/25/bluesky-starts-testing-a-trending-topics-feature)
- [SocialPilot — How platforms downrank AI slop](https://www.socialpilot.co/blog/how-social-media-platforms-handle-ai-slops)
- [The Next Web — YouTube AI slop crackdown](https://thenextweb.com/news/youtube-ai-slop-crackdown-faceless-creators-collateral-damage?type=AI)
- [Apify — TikTok Trends Scraper](https://apify.com/eunit/tiktok-trends-scraper)
- [MoneyPrinterTurbo](https://www.opensourcealternatives.to/item/moneyprinterturbo) · [short-video-maker](https://www.sourcepulse.org/projects/2566801) · [Pixelle-Video](https://www.opensourcealternatives.to/item/pixelle-video)
- [localaimaster — Kokoro vs XTTS vs Chatterbox](https://localaimaster.com/blog/kokoro-vs-xtts-vs-chatterbox) · [scriptbyai — Best open-source TTS 2026](https://www.scriptbyai.com/best-open-source-tts-models/)
- [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) · [fastembed](https://github.com/qdrant/fastembed)
