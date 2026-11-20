# Audit du cahier des charges — TrendForge

Audit fait le 19 novembre 2026 avec le skill `prd-review-challenger`, sur `cahier-des-charges-trendforge.md`.

**Verdict : bon document, mais pas encore prêt pour le développement.** Il est bien structuré et honnête sur les risques. En revanche, il contient trois chiffres incohérents entre eux, plusieurs hypothèses jamais vérifiées (sur l'API TikTok et sur ce que ton PC peut faire), et il ne prévoit rien pour la phase où le compte n'a pas encore 10 000 abonnés.

---

## 1. Points faibles et hypothèses cachées

1. **Les coûts se contredisent.** La section 1 fixe un plafond de 0,50 $ par vidéo. La section 9 annonce « environ 0,10 à 0,40 $ ». Le tableau des coûts, lui, donne 0,25 à 0,75 $ pour la variante qualité. Avec la voix ElevenLabs et 15 images IA, on dépasse donc le plafond de la section 1. Il faut choisir un seul objectif et dire quelle variante est utilisée par défaut.
2. **Le rendu en 2 à 4 min n'a jamais été mesuré.** La section 3 annonce un rendu FFmpeg de 2 à 4 min, mais la section 8 fait le montage avec MoviePy. MoviePy compose les images une par une en Python, ce qui est nettement plus lent que FFmpeg seul, surtout avec des sous-titres mot par mot, des zooms et des bruitages, sur un processeur de portable. L'objectif « vidéo complète en moins de 10 min » repose donc sur un chiffre non mesuré.
3. **Analyser une vidéo en moins de 3 min est trop optimiste.** Il faut enchaîner la transcription (environ 75 s pour une vidéo de 75 s), la séparation voix/musique sur le processeur (souvent plusieurs minutes), l'OCR sur 75 images, la détection des plans, puis deux appels à Claude. Et tout ça avec environ 3 Go de RAM libres.
4. **Le dépôt en brouillon « sans audit » n'est qu'à moitié vrai.** Même sans audit, il faut créer une application développeur TikTok, faire valider le scope `video.upload` et passer par Login Kit. TikTok demande en général un site web et une politique de confidentialité. Le document présente ça comme acquis dès la V1.
5. **Le score de tendance a besoin d'un historique qui n'existe pas.** « Croissance des vues sur 7 jours » suppose qu'on a enregistré les vues jour après jour, ce qu'aucune source ne fournit. Pendant les 7 premiers jours, le score ne peut donc pas être calculé. Il faut une règle de démarrage.
6. **Les histoires Reddit posent un problème de droits.** Le document les traite comme une simple source de sujets. Mais depuis 2023, l'usage commercial de l'API Reddit demande un accord, et réécrire l'histoire d'un utilisateur reste une œuvre dérivée. La section 10 ne mentionne que le risque de copie.
7. **La rétention visée ne peut pas être mesurée en V1.** La section 1 vise plus de 50 % de rétention à 3 s, mais les statistiques n'arrivent qu'en V2 (section 7). Pareil pour la boucle « les statistiques notent la recette » de la section 4 : elle n'existe pas avant la V2.
8. **Trois critères ne sont pas définis.** On ne sait pas comment se calculent :
   - la similarité inférieure à 30 % : sur les mots, sur le sens via des embeddings, ou autrement ?
   - le score de hook ;
   - la vérification « par empreinte » du critère d'acceptation n° 3.

   Tels quels, ces critères ne peuvent pas être testés.
9. **Le gameplay de fond est présenté comme disponible alors qu'il ne l'est pas.** La section 6 parle de « gameplay libre de droits de ta bibliothèque ». Or la section 12 se demande encore quels jeux utiliser et si leur éditeur autorise la monétisation.

## 2. Questions ouvertes (ce que le document ne dit pas)

- **Que faire avant d'avoir 10 000 abonnés ?** La monétisation demande 10 000 abonnés et 100 000 vues sur 30 jours. Pendant des semaines, voire des mois, les vidéos de plus d'une minute ne rapporteront rien. Faut-il une stratégie de croissance, par exemple des formats plus courts au début ?
- **Que se passe-t-il si yt-dlp est bloqué par TikTok, ce qui arrive souvent, ou si la vidéo est privée ou supprimée ?**
- **Que fait le module Recette sur une vidéo sans voix (musique seule, texte à l'écran) ou dans une autre langue que l'anglais ?**
- **Que se passe-t-il si la voix dépasse encore 90 s après un premier resserrement ?** Combien de tentatives, et que fait-on après un échec ?
- **Qui juge la qualité finale ?** Est-ce qu'il y a un score automatique avant la file de validation, ou est-ce toi seul ?
- **Où vont les fichiers ?** Rien n'est dit sur la taille du cache vidéo, la sauvegarde de la base SQLite, ni l'export des recettes.
- **Comment se configure le plafond de budget et que se passe-t-il quand il est atteint en pleine génération ?** La vidéo est-elle perdue ou mise en pause ?

## 3. Risques techniques et d'usage

| Risque | Conséquence si on l'ignore |
|---|---|
| Deux LLM (DeepSeek, puis Claude) pour chaque script | Le pipeline est plus complexe, il y a deux clés et deux pannes possibles, pour quelques centimes d'économie seulement |
| Quatre outils lourds (Demucs, PaddleOCR, faster-whisper, PyTorch) sur un PC avec 3 Go de RAM libres | Plantages par manque de mémoire et installation pénible |
| Fork de MoneyPrinterTurbo | Gagne du temps au début, mais on hérite de son architecture (interface Streamlit, sa propre configuration), qui ne correspond pas à la recette JSON |
| Tirage aléatoire de la police et de la couleur à chaque vidéo | Les vidéos varient, mais la chaîne n'a plus de style reconnaissable, ce qui fait baisser l'engagement |
| Publication faite à la main par copier-coller | Oublier de cocher « AI-generated » une seule fois peut suffire à sanctionner le compte |

## 4. Autres approches possibles

1. **Écrire les recettes à la main au début.** On écrirait 3 ou 4 recettes à la main, et Claude analyserait seulement quelques images de la vidéo collée. Avantage : on teste la valeur du produit dès la semaine 1. Inconvénient : on ne vérifie pas encore le module Recette, qui est censé être la vraie différence du projet.
2. **Monter directement avec FFmpeg, sans MoviePy ni fork.** Avantages : rendu beaucoup plus rapide, sous-titres natifs, moins de dépendances. Inconvénient : les commandes FFmpeg sont plus difficiles à déboguer.
3. **Un seul LLM (Claude Haiku ou Sonnet) au lieu de DeepSeek + Claude.** Avantage : un pipeline plus simple et un seul fournisseur. Inconvénient : quelques centimes de plus par vidéo.
4. **Commencer en ligne de commande, l'interface en V2.** Avantage : le cœur fonctionne plus vite. Inconvénient : moins agréable à utiliser au quotidien.

---

## Grille de complétude

| Élément | État | Commentaire |
|---|---|---|
| Problème et périmètre | ✓ | Clair, avec un « hors périmètre » explicite |
| Utilisateur cible | — | Un seul utilisateur (toi), c'est normal |
| Scénarios d'usage | △ | Le scénario nominal est bien décrit ; il manque les scénarios d'échec |
| Critères d'acceptation | △ | 7 critères, dont 3 non testables tels quels (similarité, empreinte, hook) |
| Cas limites | ✗ | Rien sur une vidéo sans voix, un lien mort, yt-dlp bloqué, un budget épuisé en cours de route |
| Indicateurs de succès | △ | Définis, mais impossibles à mesurer avant la V2 |
| Hors périmètre | ✓ | — |
| Contraintes et dépendances techniques | △ | Très détaillées, mais les performances ne sont pas mesurées sur ton PC |
| Plan B en cas d'échec | ✓ | Syncthing, plugins isolés, LiteLLM |
| Impact sur le reste (compte, juridique) | △ | Les conditions TikTok sont traitées ; Reddit et la phase avant 10 000 abonnés ne le sont pas |

## Les 3 priorités avant de coder

1. **Vérifier la monétisation et prévoir la phase de croissance.** Confirmer l'éligibilité depuis la France et ajouter une section « avant 10 000 abonnés ». Sans ça, tout le projet repose sur une hypothèse non vérifiée.
2. **Mesurer avant de promettre.** Une première version de quelques jours (V0) mesure sur ton PC le temps de rendu (MoviePy contre FFmpeg seul), la durée d'analyse et la mémoire utilisée. On corrige ensuite les objectifs de 3 min et de 10 min, ainsi que les coûts, avec une seule fourchette.
3. **Rendre les critères testables.** Définir la mesure de similarité, la méthode d'empreinte et le score de hook. Ajouter aussi les cas d'échec (lien mort, vidéo sans voix, budget atteint) aux critères d'acceptation.
