# Passation — état du projet Facilim au réveil

Bonjour Nassim. Voici la carte précise de ce qui a été fait, de ce qu'il reste à déployer, de ce qu'il faut tester, et de la route à suivre. Lis-le tranquillement avec ton café.

## 1. Ce qui est DÉJÀ en ligne (déployé pendant la session)

La fondation tient enfin. Ta base est persistante et prouvée. Le dépôt a été assaini, le code mort écarté. Et surtout, les bugs de fond du CERFA sont corrigés en production :

Le CERFA qui se vidait de tous ses champs au moment d'ajouter la page de couverture est réparé, c'était le bug de plusieurs semaines. La narration n'invente plus de profil de dépendance, ni en onglet B ni dans le projet. Le renouvellement à l'identique n'est plus inversé en réévaluation. La caisse d'assurance maladie ne se coche plus toute seule. Le numéro de Sécurité Sociale saisi à l'écran n'est plus redemandé sur WhatsApp. La confirmation montre un vrai récapitulatif. La voix du récit est juste : « je » pour l'adulte, troisième personne pour le majeur protégé, et « mon fils / ma fille » pour l'enfant selon le lien du proche.

Le socle du dictionnaire CERFA, source de vérité unique, est en ligne pour les six sections A à F, avec les bonnes conditions de profil : l'enfant sans la situation pro, l'adulte sans la scolarité, le mixte 16-25 avec les deux. Le mode de contact, la CAF, la caisse, la scolarité, la situation pro, le projet de vie et l'aidant sont enfin demandés.

La première brique de l'instructeur senior est en ligne : à la fin d'un dossier, une revue en lecture seule signale au professionnel les champs applicables restés vides.

## 2. Ce qu'il reste à DÉPLOYER ce matin

Pendant la nuit j'ai enrichi l'instructeur, en additif et sans toucher au cœur qui marche. Deux changements t'attendent :

La revue a maintenant des contrôles de cohérence d'instructeur senior : elle lève un drapeau rouge si un diagnostic est indiqué sans aucune conséquence sur la vie quotidienne (la cause numéro un de refus MDPH), si aucune demande de droit n'est renseignée, ou si le projet de vie est absent.

Et les alertes rouges de ton agent qualité, qui étaient calculées mais restaient invisibles, remontent désormais au professionnel dans le tableau de bord.

Pour déployer :

```
git add -A
git commit -m "feat(instructeur): controles de coherence + surfacage des alertes qualite"
railway up --detach
```

Tout est en additif et protégé par des gardes d'erreur. Si jamais le build échouait, Railway garde ta version actuelle en ligne, ta production ne risque rien.

## 3. Ce qu'il faut TESTER

Le seul vrai juge, c'est un dossier ENTIÈREMENT NEUF. Un ancien dossier comme Nait Ali a son récit en cache et ses champs jamais collectés, il te donnerait une fausse image.

Sur un dossier neuf, vérifie que l'assistant pose les nouvelles questions, que le récit reste sobre et fidèle, que le projet parle bien de projet et non de vie quotidienne, et qu'une fois le dossier prêt, le professionnel voit l'alerte de revue listant ce qui manque ou ce qui cloche.

## 4. État d'architecture, en toute honnêteté

Deux dettes restent, je te les redis pour qu'on les traite ensemble, pas en douce.

Il existe encore deux moteurs de CERFA en parallèle : celui qu'on a corrigé, dans `services/cerfa_filler.py`, qui remplit vraiment, et un second plus propre dans `app/engines/` qui ne sert pas au remplissage. Un seul moteur serait l'optimal.

Le dictionnaire pilote la collecte et l'extraction, mais pas encore le remplissage du PDF, qui garde ses correspondances codées en dur. La vraie source de vérité unique passera par là.

Ces deux consolidations sont à faire avec toi, déploiement et test à l'appui, jamais à l'aveugle. C'est la seule façon de ne rien casser.

## 5. La route qui reste, dans l'ordre

D'abord finir l'instructeur : réveiller les moteurs dormants de risque de refus et de solidité du dossier, et les router dans la revue. Puis fermer la boucle : l'instructeur renvoie ses points à l'agent, qui corrige depuis les vraies données ou relance la personne, avec deux garde-fous, une limite de tours et jamais d'envoi automatique à la MDPH.

Ensuite la consolidation vers un seul moteur piloté par le dictionnaire.

Et plus tard, quand le pilote aura prouvé que tout fonctionne, le passage de SQLite à PostgreSQL et l'hébergement de santé conforme, condition de l'échelle nationale.

## 6. Le cadre, qui ne bouge pas

Facilim propose et structure. L'humain valide. Facilim ne décide jamais des droits à la place de la MDPH. Et la règle d'or de toute cette session : on n'invente jamais, on s'appuie sur le réel, et ce qui manque, on le demande, on ne le fabrique pas.

Bonne journée. Quand tu es prêt, on reprend par le test du dossier neuf, puis la suite de l'instructeur.
