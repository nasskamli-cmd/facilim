# Journal de retour terrain — Facilim Phase 3+

> Ce journal documente les observations issues des dossiers réels traités en production.
> Aucune nouvelle fonctionnalité ne sera priorisée sans preuve issue des usages réels.

---

## Format d'entrée par dossier

```
## Dossier [N] — [Date] — [Profil] — [Anonymisé]

### Contexte
- Profil MDPH : adulte / enfant / protégé
- Profil handicap détecté : [profil_principal] / [sous_profil]
- Acteur accompagnant : [ESRP / SAVS / MDPH / service social / ...]

### Métriques
- Score maturité        : [0-100] ([niveau])
- Taux enrichissement   : [×N moyen]
- Nombre de relances    : [N]
- Temps de traitement   : [durée estimée]
- Alertes qualité rouges : [N]

### Ce qui fonctionne
- 

### Ce qui manque
- 

### Ce qui surprend
- 

### Erreurs détectées
- 

### Améliorations souhaitées
- 

### Évaluation synthèse professionnelle (1-5)
- Note : 
- Commentaire : 

### Évaluation acteurs mobilisables (1-5)
- Note : 
- Commentaire : 

---
```

---

## Dossier TEST-001 — Activation webhook Meta

**Date** : 04/06/2026
**Étape** : Activation webhook + premier message WhatsApp
**Profil** : Test technique (pas encore un dossier usager)

### Contexte
Premier test de bout-en-bout après enregistrement du webhook Meta.

### Métriques
- Score maturité        : –
- Taux enrichissement   : –
- Nombre de relances    : –
- Temps de traitement   : –
- Alertes qualité rouges : –

### Vérification webhook Meta
- [ ] Webhook enregistré dans Meta Business Manager
- [ ] `hub.challenge` retourné correctement (HTTP 200)
- [ ] Événement `messages` souscrit

### Premier message WhatsApp envoyé
- Message : "Bonjour"
- Heure : –
- Numéro : –

### Logs Railway observés
```
[À compléter après réception]
```

### Dashboard
- [ ] Dossier créé
- [ ] Session WhatsApp créée
- [ ] Dossier visible dans la liste
- [ ] Parcours conversationnel démarré

### Ce qui fonctionne
-

### Ce qui manque ou surprend
-

### Anomalies détectées
-

### Actions correctives
-

---

## Bilan cumulé Sprint 7

| Indicateur | Valeur |
|---|---|
| Dossiers traités | 0 / 10 |
| Profils couverts | – |
| Score maturité moyen | – |
| Taux enrichissement moyen | – |
| Alertes rouges récurrentes | – |
| Problèmes bloquants | – |

---

## Incidents production

*(Aucun pour l'instant)*

---

## Demandes d'amélioration issues du terrain

*(À alimenter au fil des dossiers)*

---

## Décisions prises suite aux retours terrain

*(À renseigner quand les premières priorités Sprint 8 seront arrêtées)*
