# Passage à l'échelle nationale — plan de migration

Ce document cadre le passage de Facilim de la base SQLite actuelle vers PostgreSQL sur un hébergement de santé conforme. Il est volontairement séparé du reste du travail, parce que c'est le seul chantier qui ne se règle pas entièrement en code: il dépend d'un hébergement à provisionner et d'une base cible pour être testé. Le faire à l'aveugle casserait la production qui fonctionne aujourd'hui.

## Pourquoi maintenant, et pourquoi pas dans le code seul

La base SQLite tient parfaitement le pilote. Elle est persistante, prouvée, et suffisante tant que l'usage reste celui d'une structure ou de quelques-unes. Elle montre ses limites au-delà: un seul fichier, des écritures concurrentes sérialisées, pas de réplication, et surtout un cadre de données de santé qui, à l'échelle nationale, impose un hébergement certifié.

Le code est déjà préparé à ce changement. Toutes les requêtes passent par une couche unique, `app/database/connection.py`, et la branche PostgreSQL y est prévue mais pas encore branchée: elle lève aujourd'hui une erreur explicite plutôt qu'une fausse implémentation. C'est volontaire, car une implémentation non testée serait plus dangereuse qu'une absence claire.

## Les conditions préalables, hors code

D'abord, choisir et contractualiser un hébergeur de données de santé certifié HDS. C'est une obligation légale dès lors que des données de santé sont hébergées pour le compte de tiers. Cet hébergeur doit fournir une instance PostgreSQL managée, sauvegardée et chiffrée au repos.

Ensuite, disposer d'un environnement de recette identique à la production, avec sa propre base PostgreSQL, pour tester la migration avant de toucher au réel. Sans cet environnement, la migration ne doit pas être lancée.

## Le travail de code, dans l'ordre

La première étape est la couche de connexion. Ajouter dans `connection.py` la branche PostgreSQL via psycopg, en gardant SQLite par défaut, le choix se faisant sur le préfixe de `DATABASE_URL`. La couche doit exposer exactement la même interface qu'aujourd'hui, pour que le reste du code n'ait rien à savoir de la base sous-jacente.

La deuxième étape est l'uniformisation des requêtes. SQLite utilise le point d'interrogation comme marqueur de paramètre, PostgreSQL utilise un autre format. Il faut soit normaliser via la couche de connexion, soit adapter les appels. C'est mécanique mais étendu, donc à faire avec une recherche systématique et une passe de tests.

La troisième étape est le schéma. Les types et les clés autoincrémentées diffèrent entre les deux moteurs. Le fichier de création des tables doit produire un schéma valide pour PostgreSQL, en repartant des définitions existantes.

La quatrième étape est la reprise des données. Exporter le contenu de la base SQLite actuelle et l'injecter dans PostgreSQL, en vérifiant les comptages table par table et l'intégrité des dossiers, des sessions et des pièces.

## L'ordre de bascule, sans risque

On valide d'abord toute la chaîne en recette sur PostgreSQL, dossier neuf compris. On fait ensuite une bascule à froid: gel des écritures le temps de la reprise des données, vérification, puis ouverture sur la nouvelle base. La base SQLite est conservée intacte en sauvegarde, ce qui permet un retour arrière immédiat si quoi que ce soit cloche.

## Ce qui ne change pas

Le cadre reste le même à toutes les échelles. Facilim propose et structure, l'humain valide, Facilim ne décide jamais des droits. Le passage à PostgreSQL est une affaire d'infrastructure et de conformité, il ne modifie ni la logique métier, ni les garde-fous, ni la qualité du CERFA.

## En résumé

Le seul prérequis bloquant est l'hébergement HDS et son instance PostgreSQL de recette. Une fois ces deux éléments en place, le travail de code décrit ici se mène en quelques étapes encadrées, chacune testée avant la suivante, avec la base actuelle conservée en filet. Tant que ces prérequis ne sont pas réunis, le pilote continue sereinement sur SQLite, qui est fait pour ça.
