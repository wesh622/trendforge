# Mesures V0 — TrendForge

Mesures faites le 19 novembre 2026 sur ton PC (Intel Comet Lake-U, 8 threads, 15 Go de RAM, Ubuntu 22.04, FFmpeg 4.4.2). Elles remplacent les valeurs « (provisoire) » du cahier des charges, selon la règle de la section 12 : objectif = médiane mesurée × 1,2.

## 1. Rendu (point 2)

Vidéo de 75 s en 1080x1920 et 30 i/s : 19 plans de 4 s avec panoramique, sous-titres mot par mot (ASS), voix et musique mixées, puis normalisées à -14 LUFS. Script : `bench/bench_rendu.py`.

| Méthode | Temps | Pic mémoire | Remarque |
| --- | --- | --- | --- |
| FFmpeg + VAAPI (Intel), 1 thread de décodage par plan | **47,5 s** | **946 Mo** | **Retenu par défaut** |
| FFmpeg + VAAPI, décodage automatique | 36,8 à 40,4 s | 1 947 Mo | Plus rapide, mais 2 fois plus de mémoire |
| FFmpeg + libx264 (veryfast, 8 Mbit/s), 1 thread de décodage | 56,6 s | 1 350 Mo | Secours si VAAPI tombe en panne |
| FFmpeg + libx264, décodage automatique | 43,3 à 46,0 s | 2 352 Mo | Trop près de la limite de 2,5 Go |
| FFmpeg + QSV (Intel) | — | — | **Ne marche pas**, ni avec le pilote i965 ni avec iHD (formats refusés) |
| MoviePy 2 | 975,5 s | 8 429 Mo | **22,5 fois plus lent** que FFmpeg, et 3,5 fois la limite de mémoire |

**Décisions**

- **On garde FFmpeg seul.** La règle était de prendre MoviePy s'il était moins de 1,5 fois plus lent ; il l'est 22,5 fois. MoviePy est donc retiré.
- **L'encodeur par défaut est VAAPI** avec 1 thread de décodage par plan, et **libx264 sert de secours**.
- **VAAPI n'accepte que la qualité constante sur ce PC** (mode CQP, `-qp 22`), avec les deux pilotes. On obtient environ 10,7 Mbit/s sur une vidéo de test très chargée en détails, au lieu des 8 Mbit/s visés. C'est acceptable, puisque TikTok réencode de toute façon.
- **Le pilote NVIDIA est inutile**, ce qui confirme la section 13 : l'encodage passe par l'Intel.

## 2. Voix et horodatage (point 3, en partie)

Script de 184 mots (une histoire d'environ 75 s). Script : `bench/bench_voix.py`.

| Étape | Temps de calcul | Audio produit | Pic mémoire |
| --- | --- | --- | --- |
| Kokoro **fp32** (`kokoro-v1.0.onnx`), voix af_heart, vitesse 1,05 | **33,4 s** (0,64 × temps réel) | 52,3 s | 710 Mo |
| Kokoro int8 (`kokoro-v1.0.int8.onnx`) | 107,3 s (2,04 × temps réel) | 52,6 s | 353 Mo |
| Horodatage faster-whisper small.en int8, modèle en cache | **9,7 s** | — | 822 Mo |
| Horodatage, premier lancement (téléchargement du modèle de 464 Mo compris) | 118,3 s | — | 1 033 Mo |

Whisper retrouve 180 des 184 mots.

**Décisions**

- **On utilise Kokoro fp32.** Il est 3 fois plus rapide que la version int8 sur ce processeur, et ses 710 Mo restent sous la limite.
- **Kokoro parle à environ 200 mots/min à vitesse 1,0**, plus vite que les 175 mots/min des recettes. La vitesse est donc calculée à partir du débit voulu (`vitesse_pour_debit` dans `voix.py`) : 175 mots/min donne une vitesse de 0,875.

## 3. Estimation d'une vidéo complète de 75 s (hors appels à Claude)

Voix (environ 48 s), puis horodatage (environ 14 s), puis rendu (environ 48 s) : **environ 2 min**, avec un pic de mémoire inférieur à 1 Go à chaque étape, puisqu'elles s'enchaînent l'une après l'autre.

L'objectif provisoire du cahier était de moins de 15 min. **Nouvel objectif proposé : moins de 4 min hors appels API**, en attendant de mesurer les appels à Claude, qui demandent une clé.

## 4. Module Recette (point 3) — en cours

## 5. Contrôles d'originalité et témoin positif (point 6) — en cours

## 6. Restent à faire, par toi (point 1, vérifications externes)

- [ ] Ouvrir TikTok Studio, rubrique Creator Rewards, et noter si ton compte y est éligible.
- [ ] Créer l'application développeur TikTok sur developers.tiktok.com. La revue est longue, donc autant la lancer tôt.
- [ ] Lister les jeux dont tu enregistrerais le gameplay, et vérifier que leur éditeur autorise la monétisation.
- [ ] Créer une clé API Anthropic (Claude), à mettre dans le trousseau du système. Sans elle, ni les scripts ni l'analyse des recettes ne peuvent tourner.
- [ ] Créer une clé API Pexels (gratuite), pour les vidéos de fond.
