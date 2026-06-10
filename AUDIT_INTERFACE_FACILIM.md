# Audit critique de l'interface Facilim

Analyse de la page de connexion et du tableau de bord, fondée sur le code et le rendu réels, avec un objectif clair: renforcer l'image de Facilim et la confiance qu'elle inspire à un professionnel du médico-social. Je distingue ce qui touche à la crédibilité, ce qui touche à la cohérence de marque, et ce qui touche à l'usage.

## Ce qui fonctionne déjà

La structure est saine et professionnelle. La connexion en deux panneaux, marque à gauche, formulaire à droite, est un schéma éprouvé et rassurant. Le tableau de bord a une vraie densité d'information utile, des indicateurs en tête, une liste de dossiers lisible, un cockpit détaillé. La police Inter sur la connexion est un bon choix, sobre et moderne. Et le logo, désormais présent partout, donne enfin une identité visible.

## Le point le plus sensible : la crédibilité

C'est ici que se joue l'image, plus encore que dans l'esthétique.

La page de connexion affiche des chiffres qui ne sont pas réels: « 3 200+ dossiers traités », « 94 % de taux de complétion », et un témoignage attribué à une personne nommée, « Sophie C., éducatrice spécialisée, MDPH 75 », avec une citation précise sur une réduction de 60 % du temps de traitement. Pour un outil encore en phase pilote, qui touche aux droits de personnes vulnérables et à des données de santé, afficher des statistiques inventées et un témoignage fabriqué est un risque réel. Un professionnel averti le repérera, et la confiance, une fois entamée sur ce terrain, ne se regagne pas. Je recommande de retirer ces éléments tant qu'ils ne sont pas vrais, et de les remplacer par quelque chose d'honnête et tout aussi fort: la mission, le cadre éthique, ou la phrase de signature du logo, « l'intelligence au service des droits des personnes ».

Dans le même esprit, le bas du formulaire affiche « Données hébergées en France · Conforme RGPD ». Or l'hébergement de santé conforme n'est pas encore en place, il est planifié. Annoncer une conformité qu'on n'a pas encore est à la fois un risque d'image et un risque juridique. Mieux vaut formuler ce qui est vrai aujourd'hui, par exemple « hébergement en France » si c'est le cas, et n'ajouter la mention de conformité que lorsqu'elle sera réelle.

## La cohérence de marque

Aujourd'hui, trois systèmes de couleur cohabitent, et ça se voit. La connexion est en bleu nuit avec un accent vert émeraude. Le tableau de bord est construit sur un bleu ciel. Et le logo, lui, déroule un dégradé vert vers turquoise, bleu, puis violet. Résultat, l'œil ne retrouve pas la même marque d'une page à l'autre.

Le logo doit devenir la référence. Je recommande d'aligner les deux interfaces sur sa palette: un bleu nuit profond pour les aplats et le texte, le turquoise du logo comme accent principal d'action, et le dégradé réservé aux moments forts, l'en-tête, les boutons principaux, les éléments de marque. Le vert émeraude actuel de la connexion, qui jure avec le turquoise du logo, devrait disparaître au profit de ce turquoise. Un bouton « Continuer » et un bouton « Accéder à mon espace » dans le turquoise de la marque, plutôt qu'en vert ou en bleu nuit, créeraient immédiatement une continuité.

## Le tableau de bord, côté usage

Quelques indicateurs desservent le produit par leur formulation plus que par leur fond.

« Maturité moy. 0 / 100 », affiché en grand et en bleu, sur un compte qui n'a qu'un dossier en cours de collecte, se lit comme une mauvaise note alors que ce n'est qu'un dossier pas encore mûr. Un score à zéro mis en avant donne une impression d'échec dès l'ouverture. Soit on le contextualise, soit on l'affiche seulement quand un dossier est suffisamment avancé pour que le chiffre ait du sens.

« Taux d'enrichissement ×1.17 » est du jargon interne. Un éducateur ne sait pas ce que ça mesure. Si l'indicateur est utile en interne, il faut le nommer en clair, par exemple « informations ajoutées par la conversation », ou le réserver à une vue d'administration.

Il y a aussi une redondance: « Dossiers actifs » en haut et « Dossiers total » plus bas affichent tous deux 1. Regrouper les compteurs en une seule rangée cohérente éviterait l'impression de répétition.

Enfin, « Poste de pilotage ESSMS » comme sous-titre est très administratif. La promesse du produit, « le dossier MDPH, enfin simple », est plus parlante et plus chaleureuse pour le public visé.

## L'accessibilité, à ne pas négliger

Plusieurs textes sont en gris très clair sur fond sombre, les noms et rôles du panneau de gauche, la note de bas de page, à des opacités de quarante à quarante-cinq pour cent. Le contraste passe sous les seuils de lisibilité, ce qui est paradoxal pour un outil dédié au handicap. Les libellés de champs à onze pixels sont également petits. Remonter les contrastes et la taille minimale du texte serait cohérent avec la mission, et c'est un signal fort vis-à-vis des MDPH.

## Détails qui comptent

Le code de la connexion conserve encore l'ancien carré vert du logo dans ses styles, devenu inutile depuis l'intégration du vrai logo. Un nettoyage évite les résidus. La page de double authentification, elle, gagnerait à expliquer en une ligne pourquoi ce code est demandé, ce qu'elle fait déjà bien avec « votre espace contient des données sensibles », c'est le bon ton à généraliser.

## Priorités, dans l'ordre

D'abord, la crédibilité: retirer les chiffres et le témoignage inventés, et ajuster la mention de conformité à la réalité. C'est le plus urgent, car c'est ce qui peut abîmer durablement l'image.

Ensuite, la cohérence de marque: aligner connexion et tableau de bord sur la palette du logo, et faire du turquoise l'accent d'action commun.

Puis l'usage: reformuler les indicateurs en langage clair, contextualiser le score de maturité, dédoublonner les compteurs, et adoucir le vocabulaire administratif.

Enfin, l'accessibilité: remonter contrastes et tailles de texte.

Aucune de ces évolutions ne touche au moteur ni aux données. Ce sont des changements d'interface, sûrs, que je peux appliquer progressivement, en te montrant chaque étape, dès que tu me donnes le feu vert.
