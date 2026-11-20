# Cahier des charges — TrendForge

Nov 19, 2026 · @lossa

TrendForge est une application de bureau Linux, open source autant que possible, qui transforme une vidéo TikTok tendance en « recette » puis génère des vidéos originales de plus de 61 s, prêtes à publier en un clic. Cible : contenu faceless narratif en anglais, publication semi-automatique.

## 1. Objectifs et contraintes

Le but est de produire 1 à 3 vidéos originales par jour et par compte, éligibles au Creator Rewards Program, pour moins de 0,50 $ de coût variable par vidéo.

**Objectifs mesurables**

- Temps humain par vidéo : moins de 3 min (relecture + validation sur téléphone).
- Durée de chaque vidéo : 61 à 90 s, contrôlée automatiquement avant export (marge de sécurité sur le seuil de 60 s).
- Taux de rétention visé : plus de 50 % à 3 s, plus de 30 % de vues complètes.
- Fonctionnement sur ton PC actuel, sans GPU puissant.

**Contraintes de monétisation (à vérifier dans le Creator Center)**

- Compte : 18 ans minimum, 10 000 abonnés, 100 000 vues sur 30 jours, pays éligible.
- Vidéos de plus de 1 min, contenu original : pas de reupload, de duo, de stitch ni de compilation brute.
- Le marché US/UK paie mieux, d'où le choix de l'anglais. Un compte créé depuis la France peut ne pas être rattaché au programme US : point à clarifier (section 12).

**Principe clé : on copie la recette, jamais la vidéo.** L'application extrait la structure d'une tendance (hook, rythme, style de sous-titres, durée des plans, ton), puis régénère tout : script, voix, visuels, musique. La vidéo source n'est jamais réutilisée dans le rendu final. C'est ce qui rend le contenu éligible et évite les réclamations de droits d'auteur.

**Hors périmètre** : publication entièrement robotisée via navigateur, achat de vues, gestion de dizaines de comptes.

## 2. Ce que dit Internet

Le consensus en 2026 : les plateformes pénalisent le contenu produit en masse et peu transformé, pas le faceless ni l'IA en tant que tels. L'application doit donc maximiser la transformation et la variété.

| Constat | Conséquence pour TrendForge |
| --- | --- |
| Le Creator Rewards exige plus de 1 min et du contenu original ; les reposts et compilations brutes ne sont pas payés ([timetopost](https://timetopost.co/blog/tiktok-creator-rewards-requirements-2026/), [ttcalculator](https://ttcalculator.net/blog/how-tiktok-creator-rewards-work-2026/)) | Contrôle de durée bloquant ; aucune image de la vidéo source dans le rendu |
| Les histoires Reddit lues mot pour mot sont saturées et déclassées ; les versions avec commentaire, analyse ou sous-niche (travail, relations) marchent encore ([shortsfast](https://shortsfast.com/blog/saturated-faceless-youtube-niches-2026/), [kineclip](https://kineclip.com/blog/tiktok-niches-to-avoid-2026/)) | Le LLM réécrit et ajoute un angle (twist, verdict, question au public) ; sous-niches configurables |
| TikTok demande d'étiqueter le contenu IA réaliste ([shortsfast](https://shortsfast.com/blog/is-faceless-ai-content-against-youtube-tiktok-tos-2026/), [socialpilot](https://www.socialpilot.co/blog/how-social-media-platforms-handle-ai-slops)) | Case « AI-generated » rappelée à chaque publication |
| YouTube a renommé sa règle en « inauthentic content » (juillet 2025) et vise les vidéos répétitives à gabarit fixe ([TNW](https://thenextweb.com/news/youtube-ai-slop-crackdown-faceless-creators-collateral-damage?type=AI)) | Variation automatique des gabarits, voix et visuels entre vidéos |
| API de publication : un client non audité ne publie qu'en privé ; l'envoi en brouillon dans la boîte TikTok fonctionne sans audit ([TikTok Developers](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post), [bundle.social](https://bundle.social/blog/tiktok-api-approval)) | Mode semi-auto par brouillon dès la V1 ; audit demandé plus tard |
| Pas d'API officielle des tendances ; le Creative Center se lit par scraping, avec des flux musique instables ([Apify](https://apify.com/eunit/tiktok-trends-scraper)) | Veille multi-sources, tolérante aux pannes |
| MoneyPrinterTurbo, short-video-maker, Pixelle-Video automatisent déjà script + voix + stock + sous-titres ([opensourcealternatives](https://www.opensourcealternatives.to/item/moneyprinterturbo), [short-video-maker](https://www.sourcepulse.org/projects/2566801)) | On réutilise leurs idées et briques ; la valeur ajoutée est le module Recette |
| Kokoro (82M, Apache 2.0) tourne vite sur CPU ; Chatterbox (MIT) clone mieux mais veut un GPU ; F5-TTS a des poids non commerciaux ([localaimaster](https://localaimaster.com/blog/kokoro-vs-xtts-vs-chatterbox), [scriptbyai](https://www.scriptbyai.com/best-open-source-tts-models/)) | Kokoro par défaut ; F5-TTS et XTTS exclus |

Les chiffres de RPM varient beaucoup selon les sources (0,40 à 1 $ pour 1 000 vues qualifiées sur TikTok, non vérifié). Ils ne servent pas de base au planning.

## 3. Machine cible

Ton PC peut faire tourner localement la voix, la transcription, l'analyse vidéo et le montage, mais pas la génération d'images ou de vidéos IA : celle-ci passe par des API.

| Élément | Détecté | Impact |
| --- | --- | --- |
| CPU | Intel Comet Lake-U (portable, basse consommation) | Rendu FFmpeg d'une vidéo de 75 s en 1080x1920 : environ 2 à 4 min |
| GPU | NVIDIA MX250, 2 Go, pilote non chargé + Intel UHD | Inutilisable pour Flux, Wan ou Chatterbox ; QSV Intel utilisable pour encoder |
| RAM | 15 Go, dont environ 3 Go libres au moment du test | Whisper « small » ou « medium » en int8 OK ; fermer le navigateur pendant les rendus |
| Disque | 260 Go libres | Largement suffisant (prévoir 20 Go de cache) |
| Outils | Python 3.10, FFmpeg, Docker, Node déjà installés | Installation simplifiée |

**Exigence** : l'application détecte le matériel au démarrage et choisit un profil. Profil « Léger » (ton PC) : tout en CPU, visuels par API ou banque d'images. Profil « GPU » (RTX 8 Go et plus, ou GPU loué) : ComfyUI local pour images et vidéo IA. Changer de machine ne doit demander aucune modification de code.

## 4. Architecture

Tout passe par la recette : les trois entrées produisent une recette JSON, et le moteur de génération ne lit que des recettes.

&#91;embedded content: architecture · 3 entrées, recette, génération, publication\]

Les statistiques de chaque vidéo publiée reviennent noter la recette qui l'a produite, ce qui fait progresser le mode un clic avec le temps. Les appels LLM passent tous par une passerelle unique (LiteLLM).

## 5. Module Recette (reverse engineering)

Tu colles un lien TikTok (ou déposes un fichier .mp4) et tu obtiens en 1 à 3 min une fiche recette réutilisable. La vidéo téléchargée sert uniquement à l'analyse et est supprimée du cache après 7 jours.

**Étapes d'analyse**

1. Téléchargement : yt-dlp (lien) ou import de fichier ; métadonnées récupérées (durée, vues, likes, légende, hashtags, son utilisé).
2. Transcription mot par mot avec horodatage : faster-whisper (small int8 sur CPU, environ 1x temps réel).
3. Découpage en plans : PySceneDetect → nombre de plans, durée moyenne, rythme des coupes.
4. Texte à l'écran : OCR (RapidOCR ou PaddleOCR) sur 1 image par seconde → police, position, couleur, nombre de mots affichés à la fois.
5. Audio : séparation voix / musique (Demucs), tempo (librosa), volume relatif de la musique, présence de bruitages.
6. Visuel : 6 à 10 images clés envoyées à Claude (vision) → type de fond (gameplay, stock, images IA, captures Reddit), cadrage, palette, mouvements (zoom, Ken Burns).
7. Synthèse : Claude produit la recette JSON et un résumé lisible « pourquoi ça marche » (hook, boucle de curiosité, payoff, appel à l'action).

**Format de la recette** (schéma validé par Pydantic, modifiable à la main dans l'interface)

```json
{
  "recipe_id": "aita-wedding-twist-v1",
  "source": {"url": "https://www.tiktok.com/@x/video/123", "views": 2400000, "duration_s": 74},
  "niche": "reddit_relationship_drama",
  "language": "en",
  "target_duration_s": [65, 85],
  "structure": [
    {"part": "hook", "seconds": [0, 3], "pattern": "question choc + chiffre", "example": "My sister banned me from her wedding for one reason..."},
    {"part": "setup", "seconds": [3, 20]},
    {"part": "escalation", "seconds": [20, 55], "beats": 3},
    {"part": "twist", "seconds": [55, 68]},
    {"part": "cta", "seconds": [68, 75], "pattern": "question au public pour les commentaires"}
  ],
  "script_style": {"pov": "1st_person", "wpm": 175, "reading_level": "grade_6", "tone": "indigné puis satisfait"},
  "voice": {"gender": "female", "age": "25-35", "speed": 1.1, "engine_hint": "kokoro:af_heart"},
  "visuals": {"background": "satisfying_gameplay", "cut_every_s": 2.5, "zoom_punch": true, "overlay": "reddit_card_first_3s"},
  "captions": {"style": "word_by_word", "words_on_screen": 2, "font": "Montserrat ExtraBold", "color": "#FFFFFF", "highlight": "#FFD400", "position": "center"},
  "audio": {"music_mood": "suspense lo-fi", "music_db": -22, "sfx": ["whoosh_on_cut", "ding_on_twist"]},
  "posting": {"hashtags": ["#aita", "#redditstories", "#storytime"], "best_hours_utc": [14, 18, 23]},
  "why_it_works": "Hook sous forme de question en 2 s, 3 escalades, twist à 75 % de la durée."
}
```

**Bibliothèque de recettes** : chaque recette est enregistrée (SQLite), notable par les performances des vidéos qu'elle a produites, et duplicable. Une dizaine de recettes de départ sont fournies (histoire Reddit, faits étonnants, mystère non résolu, « what would you do », top 5).

## 6. Génération

Deux entrées, un seul moteur : le mode un clic remplit tout depuis la recette ; le mode personnalisé laisse décrire le format en texte libre, que Claude convertit en recette.

**Mode « Générer » (un clic)**

- Tu choisis une tendance ou une recette, tu règles le nombre de vidéos (1 à 10), tu appuies sur Générer.
- Le sujet est trouvé automatiquement : nouveaux posts Reddit populaires de la sous-niche (API Reddit), actualité ou idée générée par le LLM, avec dédoublonnage par rapport aux vidéos déjà faites.

**Mode personnalisé**

- Champ texte libre, par exemple : « Histoire d'horreur courte, voix masculine grave, fond forêt sombre en images IA, 70 s, sous-titres rouges, fin ouverte ».
- Options : partir d'une recette existante et ne modifier que certains champs, fournir son propre script, choisir la voix, la musique et les visuels à la main.
- Aperçu de la recette générée avant lancement.

**Pipeline de génération (identique pour les deux modes)**

1. Script : DeepSeek rédige 3 variantes (pas cher) ; Claude choisit et améliore la meilleure (hook, rythme, originalité). Longueur calculée : durée cible × débit de mots (par ex. 75 s × 175 mots/min = 220 mots).
2. Contrôle qualité du script : score de hook, pas de copie de la source (similarité inférieure à 30 %), pas de contenu interdit.
3. Voix : Kokoro en local, horodatage des mots via faster-whisper.
4. Durée : si l'audio fait moins de 61 s, le script est rallongé automatiquement ; s'il dépasse 90 s, il est resserré.
5. Visuels selon la recette : gameplay libre de droits de ta bibliothèque, vidéos Pexels/Pixabay, ou images IA (API) animées en Ken Burns.
6. Sous-titres animés mot par mot (fichier ASS généré depuis les horodatages).
7. Musique libre (bibliothèque locale, Pixabay Music) ajustée à -22 dB sous la voix, plus bruitages.
8. Montage et rendu : FFmpeg via MoviePy, 1080x1920, 30 i/s, H.264, environ 8 Mbit/s.
9. Métadonnées : titre, légende, 3 à 5 hashtags, couverture (image clé + texte).
10. File de validation : la vidéo attend ton accord avant publication.

**Anti-répétition** : à chaque vidéo, tirage aléatoire contrôlé de la voix (parmi 3), de la police, de la couleur d'accent, du fond et de la musique, pour éviter l'effet gabarit sanctionné par les plateformes.

## 7. Veille des tendances et publication

La veille propose chaque matin 10 tendances classées par potentiel ; la publication dépose la vidéo en brouillon dans ton appli TikTok, et tu publies en 2 taps.

**Veille (tâche planifiée, 1 fois par jour)**

- Sources : TikTok Creative Center (hashtags et vidéos du marché US, lecture de la page), recherche par hashtag via yt-dlp, Reddit (subreddits de ta niche), Google Trends (pytrends).
- Score de tendance = croissance des vues sur 7 jours × adéquation à la niche faceless × facilité de reproduction (calculée par le LLM).
- Pour les 3 meilleures, la recette est extraite automatiquement en tâche de fond : au réveil, tu n'as plus qu'à appuyer sur Générer.
- Chaque source est un plugin isolé : si TikTok change sa page, seule cette source tombe, l'application continue.

**Publication semi-automatique**

1. Tu valides la vidéo dans la file (lecture, modifier la légende, regénérer un élément).
2. Envoi en brouillon via la Content Posting API (mode upload, sans audit) : la vidéo arrive dans ta boîte de réception TikTok.
3. Notification sur ton téléphone (ntfy, gratuit) avec la légende et les hashtags à copier.
4. Dans l'appli TikTok : coller la légende, cocher « AI-generated content », choisir un son si pertinent, publier.
5. Plan B si l'API n'est pas disponible : export du fichier vers un dossier synchronisé avec le téléphone (Syncthing) avec un fichier texte de légende.

**Calendrier** : créneaux recommandés pour le public US (environ 14 h, 18 h et 23 h UTC, à ajuster selon tes statistiques), avec rappels par notification.

**Statistiques (V2)** : récupération des vues, de la rétention et des likes par vidéo (API Display, ou saisie manuelle). Les performances réévaluent chaque recette, et le mode un clic privilégie les recettes gagnantes.

## 8. Stack technique

Tout est en Python, local, et open source sauf les LLM et les images IA, branchés par API et interchangeables.

| Fonction | Choix principal | Licence / coût | Alternative |
| --- | --- | --- | --- |
| Interface | Application web locale NiceGUI (ou Gradio), ouverte dans une fenêtre pywebview | MIT, gratuit | Tauri + React (V3) |
| Back-end, file de tâches | FastAPI + Huey (ou RQ) + SQLite | MIT, gratuit | Celery + Redis |
| Téléchargement vidéo | [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense, gratuit | gallery-dl |
| Transcription | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) small/medium int8 | MIT, gratuit | whisper.cpp |
| Détection des plans | PySceneDetect | BSD, gratuit | OpenCV maison |
| OCR | RapidOCR | Apache 2.0, gratuit | PaddleOCR, Tesseract |
| Analyse audio | Demucs + librosa | MIT / ISC, gratuit | Spleeter |
| Analyse visuelle et recette | Claude (vision) | API payante, quelques centimes par analyse | Qwen2.5-VL local en profil GPU |
| Rédaction des scripts | DeepSeek (brouillons) + Claude (version finale) | API, environ 0,3 $ par million de tokens côté DeepSeek | Ollama + Qwen local, plus lent |
| Voix | [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | Apache 2.0, gratuit, CPU | Piper (MIT) ; ElevenLabs en option premium |
| Clonage de voix (profil GPU) | Chatterbox | MIT, gratuit | — |
| Images IA | API (Higgsfield, déjà connecté, ou fal.ai/Replicate) | Payant à l'image | ComfyUI + Flux schnell en profil GPU |
| Vidéos de fond | Pexels et Pixabay (API gratuites) + bibliothèque locale | Gratuit, licence libre d'usage | Gameplay enregistré par toi |
| Sous-titres | Fichier ASS généré + libass dans FFmpeg | Gratuit | pycaps |
| Montage, rendu | MoviePy 2 + FFmpeg | MIT / LGPL, gratuit | Remotion (licence payante en entreprise) |
| Veille Reddit / Google | PRAW, pytrends | Gratuit | — |
| Publication | Content Posting API TikTok (brouillon) | Gratuit | Syncthing vers le téléphone |
| Notifications | ntfy | Apache 2.0, gratuit | Telegram bot |
| Installation | Script install.sh + uv, ou Docker Compose | Gratuit | AppImage (V3) |

**Réutilisation** : partir d'un fork de [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (MIT) pour le montage, les sous-titres et la gestion du stock est l'option la plus rapide. On y ajoute le module Recette, la veille et la file de validation. À trancher en V0 après lecture de son code.

**Couche LLM** : une interface unique (LiteLLM) pour appeler Claude, DeepSeek ou un modèle local avec la même fonction, et choisir le modèle par tâche dans les réglages. Les clés API sont stockées dans le trousseau du système (keyring), jamais dans le code.

## 9. Interface, exigences non fonctionnelles, coûts

L'interface tient en 5 écrans ; une vidéo complète doit sortir en moins de 10 min sur ton PC pour environ 0,10 à 0,40 $.

**Écrans**

1. Tendances : liste du jour avec score, aperçu, bouton « Extraire la recette ».
2. Recettes : bibliothèque, édition de la fiche, zone « coller un lien ».
3. Créer : gros bouton Générer, nombre de vidéos, onglet Personnalisé avec le champ texte libre.
4. File de validation : lecteur vidéo, légende modifiable, boutons Regénérer (script, voix, visuels), Approuver, Rejeter.
5. Réglages : clés API, profil matériel, voix, polices, budget mensuel, comptes TikTok.

**Exigences non fonctionnelles**

- Installation en une commande sur Ubuntu 22.04 ; fonctionne hors ligne sauf pour les appels API.
- Reprise après erreur : chaque étape du pipeline est mise en cache, une regénération ne refait que l'étape modifiée.
- Plafond de budget : compteur de dépenses API par jour et par mois, arrêt automatique au plafond fixé.
- Journal : chaque vidéo garde sa recette, ses prompts, ses modèles et son coût (traçabilité et preuve d'originalité).
- Code modulaire : chaque brique (voix, visuels, LLM, source de tendances) est un plugin remplaçable.

**Coûts estimés par vidéo de 75 s** (prix des API à vérifier au moment de l'implémentation)

| Poste | Variante gratuite | Variante qualité |
| --- | --- | --- |
| Script (DeepSeek + Claude) | environ 0,01 $ (DeepSeek seul) | environ 0,05 $ |
| Analyse de recette (amortie sur 10 vidéos) | 0 $ (réglages manuels) | environ 0,01 $ |
| Voix | 0 $ (Kokoro) | environ 0,20 $ (ElevenLabs) |
| Visuels | 0 $ (Pexels, gameplay) | 0,10 à 0,50 $ (8 à 15 images IA) |
| Musique, montage, publication | 0 $ | 0 $ |
| **Total** | **environ 0,01 $** | **environ 0,25 à 0,75 $** |

À 3 vidéos par jour en variante qualité, compter 25 à 70 $ par mois. Le budget libre permet aussi de louer un GPU à l'heure pour générer des clips vidéo IA par lots (profil GPU distant, V3).

## 10. Risques et conformité

Le risque principal n'est pas technique : c'est un compte jugé « non original » ou « spam ». Les règles ci-dessous sont des exigences bloquantes du logiciel.

| Risque | Probabilité | Parade intégrée |
| --- | --- | --- |
| Vidéos classées non originales, donc non rémunérées | Élevée | Aucun extrait de la source ; script réécrit avec un angle propre ; variation des gabarits ; contrôle de similarité |
| Droits d'auteur (vidéo, musique, texte Reddit) | Moyenne | Musique et stock libres de droits uniquement ; histoires Reddit réécrites et non copiées ; gameplay de jeux autorisant la monétisation |
| Sanction pour automatisation | Moyenne | Pas de robot de navigateur ; publication par l'API officielle ou à la main ; 1 à 3 vidéos par jour maximum |
| Contenu IA non étiqueté | Faible si respecté | Rappel « AI-generated » à chaque publication |
| Panne d'une source de tendances | Élevée | Sources en plugins indépendants ; mode manuel par collage de lien |
| Niche saturée (Reddit stories) | Élevée | Sous-niches, commentaire ajouté, tests A/B de recettes |
| Conditions d'utilisation : télécharger des vidéos TikTok pour analyse est contraire aux conditions de TikTok | Certaine | Usage personnel d'analyse uniquement, suppression sous 7 jours, jamais de réutilisation. À assumer en connaissance de cause |
| Hausse de prix d'une API | Moyenne | Couche LiteLLM : on bascule de modèle dans les réglages |
| Contenu interdit (violence, désinformation) | Faible | Filtre de modération du LLM avant rendu |

## 11. Planning et critères d'acceptation

Une première vidéo publiable sort en semaine 2 ; l'outil complet « coller un lien, appuyer sur Générer » est prêt en semaine 6. Les durées sont des estimations.

&#91;embedded content: planning · 4 versions, durées estimées pour un développeur seul aidé de Claude Code\]

**Critères d'acceptation de la V1**

- [ ] Coller un lien TikTok produit une recette JSON valide en moins de 3 min sur ton PC.
- [ ] Un clic sur Générer produit une vidéo 1080x1920 de 61 à 90 s en moins de 10 min.
- [ ] Aucune image ni aucun son de la vidéo source n'apparaît dans le rendu (vérifié par empreinte).
- [ ] Le mode personnalisé transforme une description libre en recette, modifiable avant lancement.
- [ ] Deux vidéos de la même recette diffèrent par la voix, le fond, la musique et le script.
- [ ] Le coût de chaque vidéo est affiché et le plafond mensuel bloque les appels.
- [ ] La vidéo validée arrive sur ton téléphone (brouillon TikTok ou Syncthing) avec sa légende.

## 12. Questions ouvertes

- [ ] Pays du compte : le Creator Rewards est-il accessible depuis la France pour un compte qui vise le public US ? Faut-il un compte US distinct (et est-ce permis) ?
- [ ] Un ou plusieurs comptes (une niche par compte) ?
- [ ] Sous-niche de départ : drame relationnel, travail, horreur, mystères, faits étonnants ?
- [ ] Gameplay de fond : quels jeux, enregistrés par toi, et leur éditeur autorise-t-il la monétisation ?
- [ ] Partir d'un fork de MoneyPrinterTurbo ou écrire de zéro ?
- [ ] Créer une application développeur TikTok pour l'API dès la V1, ou commencer par Syncthing ?
- [ ] Installer le pilote NVIDIA ? La MX250 reste trop faible pour l'IA, ce n'est utile que pour l'encodage.

## Sources

Consultées le 19 novembre 2026 ; la plupart sont des blogs tiers, les règles officielles sont à revérifier dans le Creator Center et sur developers.tiktok.com.

- [TikTok Developers — Content Posting API, Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post)
- [TikTok Developers — Content Sharing Guidelines](https://developers.tiktok.com/docs/en/content-sharing-guidelines)
- [bundle.social — TikTok API approval](https://bundle.social/blog/tiktok-api-approval)
- [timetopost — Creator Rewards requirements 2026](https://timetopost.co/blog/tiktok-creator-rewards-requirements-2026/)
- [ttcalculator — How Creator Rewards work 2026](https://ttcalculator.net/blog/how-tiktok-creator-rewards-work-2026/)
- [shortsfast — Faceless AI content and ToS 2026](https://shortsfast.com/blog/is-faceless-ai-content-against-youtube-tiktok-tos-2026/)
- [shortsfast — Saturated faceless niches 2026](https://shortsfast.com/blog/saturated-faceless-youtube-niches-2026/)
- [kineclip — TikTok niches to avoid 2026](https://kineclip.com/blog/tiktok-niches-to-avoid-2026/)
- [SocialPilot — How platforms downrank AI slop](https://www.socialpilot.co/blog/how-social-media-platforms-handle-ai-slops)
- [The Next Web — YouTube AI slop crackdown](https://thenextweb.com/news/youtube-ai-slop-crackdown-faceless-creators-collateral-damage?type=AI)
- [Apify — TikTok Trends Scraper](https://apify.com/eunit/tiktok-trends-scraper)
- [MoneyPrinterTurbo](https://www.opensourcealternatives.to/item/moneyprinterturbo) · [short-video-maker](https://www.sourcepulse.org/projects/2566801) · [Pixelle-Video](https://www.opensourcealternatives.to/item/pixelle-video)
- [localaimaster — Kokoro vs XTTS vs Chatterbox](https://localaimaster.com/blog/kokoro-vs-xtts-vs-chatterbox) · [scriptbyai — Best open-source TTS 2026](https://www.scriptbyai.com/best-open-source-tts-models/)
- [nxcode — DeepSeek API pricing 2026](https://www.nxcode.io/resources/news/deepseek-api-pricing-complete-guide-2026)
