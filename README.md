# Facilim — Source de vérité

Ce fichier remplace les dizaines de rapports d'audit accumulés à la racine. Il décrit l'état réel du projet, vérifié le 8 juin 2026. En cas de doute, c'est lui qui fait foi.

## Ce qui tourne réellement en production

L'application déployée est le dossier `app/`. Railway la construit via le `Dockerfile`, dont le point d'entrée est `app.main:app`. Le service est en ligne sur www.facilim.fr.

Le `main.py` situé à la racine n'est PAS exécuté. C'est une ancienne version. Toute modification de comportement en production se fait dans `app/`, jamais à la racine. Cette confusion entre les deux bases de code est la raison pour laquelle des corrections passées semblaient sans effet : elles visaient le mauvais fichier.

## Où vivent les données

La base est en SQLite, posée sur un volume Railway persistant monté sur `/data`. Les variables d'environnement la dirigent correctement : `DATABASE_URL` vaut `sqlite:////data/mdph_dossiers.db` et `DATABASE_PATH` vaut `/data/mdph_dossiers.db`. Conséquence : les dossiers survivent aux redéploiements. La crainte d'une base qui s'efface à chaque mise en ligne ne correspond pas à la configuration actuelle.

## Authentification et sessions

Le Dashboard utilise un cookie JWT nommé `facilim_token`, signé par `JWT_SECRET_KEY`, variable présente et stable dans Railway. Les sessions ne sautent donc pas à chaque déploiement. Le seul élément en mémoire vive est le code de vérification à deux facteurs, valable dix minutes, dont la perte au redémarrage est sans conséquence.

## Dépendances racine encore utilisées (ne pas déplacer ni éditer à la légère)

L'app déployée s'appuie encore sur quelques fichiers restés à la racine. Les voici, ce sont les seuls à conserver hors de `app/` :

`config.py`, ainsi que `services/cerfa_expert.py`, `services/cerfa_filler.py` et `services/ocr_image.py`. S'ajoutent les dossiers `1_ingestion/`, `2_intelligence/`, `3_accessibility/` et `4_llm_client/`, dont au moins un module est chargé dynamiquement par `app/engines/orchestration_engine.py`.

## Code mis à l'écart

Le nettoyage a déplacé, sans rien supprimer, l'ancienne application et les fichiers morts dans `_legacy/`, et les anciens rapports et scripts jetables dans `_archive/`. Ces deux dossiers sont inertes, exclus du déploiement, conservés pour mémoire. Si un jour quelque chose y semble utile, il vaut mieux le réécrire proprement dans `app/` que de le réactiver tel quel.

## Déploiement

Le déploiement se fait depuis la racine du dépôt avec `railway up --detach`. Le fichier `nixpacks.toml` est obsolète : Railway utilise le `Dockerfile` (voir `railway.toml`), il peut être ignoré.

## Règle d'or

Une seule application vit : `app/`. Avant d'éditer un fichier, vérifier qu'il appartient à `app/` ou à la courte liste des dépendances racine ci-dessus. Tout le reste est du passé rangé, pas du code à modifier.
