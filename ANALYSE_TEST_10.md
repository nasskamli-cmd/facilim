# Analyse consolidée — Test 10 (WhatsApp)

Contexte : dossier de test mené sur le même numéro WhatsApp que les tests précédents (Karim). Profil annoncé « Mourade ». Ce test a révélé deux anomalies critiques, désormais corrigées.

## Déroulé de la conversation

L'assistant accueille « Mourade », recueille le consentement RGPD (accepté par « Oui »), puis interroge sur la vie quotidienne. La personne décrit des difficultés respiratoires, un besoin d'oxygène à proximité, une fatigue rapide à l'effort, et un temps accru pour réaliser ses activités. Puis, à la demande de relecture, l'assistant affiche un récapitulatif — mais ce récapitulatif contient les données de NAIT ALI Karim, pas celles de Mourade. La personne le signale elle-même : « je ne suis pas monsieur Nait Ali ».

## Ce qui fonctionne

Le consentement RGPD s'affiche correctement : finalités d'usage, chiffrement, contact, « Tapez OUI ou NON ». La transcription des messages vocaux est prise en compte. Les demandes ont été correctement identifiées au fil des tests : AAH, RQTH, ORP, et orientation vers une formation au centre Richebois. Le récapitulatif sur demande fonctionne désormais (« Voici ce que j'ai noté »), avec le numéro de Sécurité Sociale masqué (1•••••••••••450). Le ton reste empathique et adapté.

## Anomalies relevées, causes racines et statut

### 1. CRITIQUE — Fuite de données entre deux personnes (RGPD)

Mourade est accueilli mais le récapitulatif affiche l'identité complète de NAIT ALI Karim : nom, date de naissance, numéro de Sécurité Sociale, adresse, médecin traitant.

Cause racine : le rattachement d'un message entrant à un dossier se fait par numéro de téléphone, avec une requête « LIMIT 1 » sans aucun tri. Le même numéro ayant servi pour Karim puis pour Mourade, plusieurs sessions coexistaient, et la requête renvoyait une session au hasard — celle de Karim. Le message de Mourade tombait donc dans le dossier de Karim.

Statut : CORRIGÉ. Le système retient désormais toujours la session la plus récemment créée, c'est-à-dire le dernier dossier ouvert. Le message d'une nouvelle personne ne peut plus retomber dans l'ancien dossier d'une autre.

### 2. CRITIQUE — Plantage à la génération du CERFA

Erreur affichée : « latin-1 codec can't encode character ' ».

Cause racine : le nom de l'usager était inséré tel quel dans l'en-tête HTTP qui sert le PDF. Or cet en-tête n'accepte que le latin-1, et une apostrophe courbe ou un caractère hors latin-1 dans le nom faisait planter l'envoi.

Statut : CORRIGÉ. Le nom est translittéré en ASCII pur pour le nom de fichier, sans toucher au contenu du CERFA.

### 3. Confusion d'identité

L'assistant accueille « Mourade » puis l'appelle « Karim ». C'est une conséquence directe du bug de rattachement ci-dessus ; le correctif de routage le résout.

### 4. Mémoire et questions répétées

Sur les tests précédents, le numéro de Sécurité Sociale était redemandé plusieurs fois. Cause : un décalage de nom de champ entre ce qui était collecté et ce que l'agent surveillait. Statut : CORRIGÉ précédemment.

### 5. Récapitulatif « Demandes : non précisé »

Les demandes AAH / RQTH / ORP n'étaient pas encore enregistrées dans ce dossier au moment du récapitulatif, la collecte n'étant pas terminée. À revérifier sur un parcours complet.

### 6. Couverture du CERFA à rendre exhaustive

Chantier en cours via le dictionnaire CERFA, source de vérité unique, dont les six sections A à F sont désormais déployées : chaque case applicable au profil est censée être demandée.

## Conclusion

Les deux anomalies critiques, la fuite de données et le plantage de génération, sont corrigées et prêtes à déployer. Le reste relève d'améliorations déjà engagées. Le point le plus important : plus jamais les données d'une personne ne doivent apparaître dans le dossier d'une autre, et c'est désormais verrouillé au niveau du rattachement.
