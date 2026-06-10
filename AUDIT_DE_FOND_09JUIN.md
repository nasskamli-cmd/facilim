# Audit de fond — chaîne CERFA Facilim

Lecture faite à partir du code réel et du test 11 (NOBILE Antoine), pas d'un seul symptôme. L'objectif est de voir, onglet par onglet, ce qui marche, ce qui ne marche pas, les questions absentes et les redondances. Rien n'a été modifié en profondeur avant ta validation.

## La cause derrière la plupart des symptômes

Trois machines se parlent mal, et c'est de là que viennent presque tous les défauts que tu as relevés.

La première est l'extraction documentaire. Le bilan transmis est bien lu, mais l'extracteur ne récupère que huit champs de contenu fonctionnel : limitations, restrictions, besoins, freins, ressources, projets, verbatim, chronologie. Il ne lit jamais l'identité. Ni le nom, ni la civilité, ni la date de naissance, ni l'adresse. Or ton bilan dit « Mr NOBILE Antoine, né le 14/03/1966, 36 rue des Porchins ». Tout cela existe dans le document, mais le système ne le voit pas, donc il le redemande. Ton intuition était juste : la question du genre n'aurait pas dû être posée, et la cause exacte est là. Pire, ce qui est extrait est rangé dans un espace à part, `_document_knowledge`, qui ne remplit aucun champ structuré du dossier. Le code lui-même le note : cette connaissance « alimente le texte, pas les champs structurés ».

La deuxième est la double génération du récit. Un premier moteur, le V3, rédige les textes des sections B, D et E à partir, entre autres, de la connaissance documentaire. Puis le pont transmet ce texte au second moteur, le V2, celui qui remplit réellement le PDF. Et le V2 ne reprend pas ce texte tel quel : il le repasse dans un nouvel appel au modèle qui le réécrit. Le récit est donc fabriqué deux fois, et c'est cette seconde réécriture libre qui invente la toilette et l'habillage à partir d'une simple fatigue. J'ai posé un garde-fou qui bloque maintenant cette invention, mais le vrai correctif de fond est de supprimer la double génération.

La troisième est la logique de questions. La prochaine question est simplement le premier champ obligatoire encore vide. Le problème n'est pas l'ordre en lui-même, c'est que les réponses libres ne sont pas toujours rangées dans le bon champ. Quand Antoine répond « en 2025 » ou « depuis plusieurs années », aucun champ de date ne reçoit la valeur, donc le système considère qu'il manque encore quelque chose et relance, d'où la boucle. Et quand il répond « Mr Nobile Antoine » à la question du genre, c'est « Mr » qui est rangé comme genre, valeur que la suite ne savait pas interpréter.

## Onglet par onglet

### Accueil et identité

Cette partie vit en dehors du dictionnaire, dans la logique de base. Le nom, la date de naissance, le numéro de sécurité sociale et l'adresse remontent correctement. Le genre était le maillon cassé : la civilité n'était pas reconnue. C'est corrigé, Mr, Monsieur, Mme et Madame sont désormais lus comme une déclaration de genre. Reste le fond : ces informations figurent souvent dans le bilan transmis et devraient être lues automatiquement plutôt que redemandées.

### Section A, administratif

Mode de contact, organisme payeur, numéro d'allocataire, caisse d'assurance maladie, nationalité, nom et lieu de naissance. Toutes ces questions existent dans le dictionnaire. Dans le test 11, aucune n'a été posée, parce que la conversation s'est bloquée en section D avant d'y arriver et que tu l'as arrêtée. Ce n'est donc pas un trou de conception sur A, c'est la boucle de D qui a mangé la conversation. À surveiller toutefois : le dictionnaire décrit la cible CERFA de chaque champ mais ne pilote pas le remplissage, qui garde des correspondances codées en dur dans le V2. Il existe donc un risque réel de champs collectés mais jamais reportés sur le PDF.

### Section B, vie quotidienne

Les aides humaines, les aides techniques et les frais restant à charge sont prévus, avec la bonne règle d'interrogation ouverte qui ne cible un acte que si la personne en parle. Le défaut majeur ici était l'invention du récit, désormais bloquée par le garde-fou. Dans le test 11, seul l'impact a été recueilli ; les aides techniques et les frais n'ont pas été demandés, là encore parce que la conversation a déraillé avant.

### Section C, scolarité

Type d'établissement, classe, accompagnement AESH, aménagements. Conditionnée aux profils enfant et seize-vingt-cinq ans, ce qui est correct. Non éprouvée sur ce test, qui est un adulte.

### Section D, situation professionnelle

C'est l'onglet qui a déraillé. La situation a bien été captée, licencié pour inaptitude, ainsi que le projet, retrouver un travail adapté via une préorientation. Mais la question « depuis quand votre situation a changé » a tourné trois fois alors qu'Antoine avait répondu « en 2025 » à deux reprises. La réponse n'était rangée nulle part, donc elle était redemandée. Le projet professionnel, lui, alimente bien la section.

### Section E, projet de vie

Attentes et projet de vie. Bien recueillis sur ce test : AAH, RQTH, orientation ORP en ESPO, et le souhait d'une préorientation vers un projet adapté à la santé. C'est l'onglet le plus solide.

### Section F, aidant

Volontairement non obligatoire, demandé seulement si une aide existe. Antoine n'a évoqué aucun aidant, donc rien n'a été demandé. Comportement correct.

## Questions manquantes et redondances sur ce test

Manquent réellement, parce que la conversation s'est arrêtée en D : toute la section A, ainsi que les aides techniques et les frais de la section B. La cause commune est la boucle de D et l'ordre de parcours, pas une absence dans le dictionnaire.

Redondances : le genre, déjà présent dans le bilan, le « depuis quand » répété trois fois, et un récapitulatif affiché deux fois de suite.

## Ce qui est déjà corrigé cette session

La civilité est reconnue comme genre, donc la case sexe se cochera. Le garde-fou anti-invention bloque tout acte d'aide absent des informations réelles dans le récit de la vie quotidienne. Le refus de donner les données médicales est bien respecté, sans insistance, ce qui est le bon comportement.

## Correctifs de fond proposés, par priorité

D'abord, lire l'identité dans les documents. Étendre l'ingestion du bilan pour en tirer nom, prénom, civilité, date et lieu de naissance, adresse, et écrire ces valeurs dans les vrais champs du dossier. C'est ce qui supprime la redondance du genre et de l'identité, et c'est l'attente que tu as exprimée.

Ensuite, supprimer la double rédaction du récit. Quand le texte du moteur V3 existe, le V2 doit l'utiliser tel quel pour la page 8 plutôt que de le réécrire. On retire ainsi une surface entière d'invention et un coût de modèle, en plus du garde-fou déjà posé.

Puis, capter les réponses temporelles libres. Ranger « en 2025 » ou « depuis plusieurs années » dans le champ de date, et plafonner la relance pour qu'une réponse déjà donnée ne soit jamais redemandée.

Ensuite, faire du dictionnaire le vrai pilote du remplissage. Aujourd'hui il décrit la cible mais ne remplit pas ; tant que ce lien n'est pas fait, des champs collectés peuvent ne jamais arriver sur le PDF. C'est la consolidation que nous avions identifiée.

Enfin, revoir l'ordre de parcours pour que l'administratif et l'identité se terminent sans qu'un blocage en section D fige toute la conversation.

## Le cadre, inchangé

Facilim propose et structure, l'humain valide, Facilim ne décide jamais des droits. On n'invente rien, on s'appuie sur le réel, et ce qui manque se demande sans se fabriquer.
