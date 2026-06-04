# Checklist déploiement Railway — Facilim Production

## Statut actuel

| Étape | Statut |
|---|---|
| Variables d'environnement locales | ✅ 5/5 obligatoires présentes |
| DB locale — migrations | ✅ 10/10 appliquées |
| DB locale — colonnes Phase 3+ | ✅ 12/12 présentes |
| Serveur local `/health` | ✅ DEGRADED (ENCRYPTION_KEY manquante — acceptable en dev) |
| APP_SECRET_KEY / AES_SECRET_KEY sécurisées | ✅ Clés fortes générées et déployées |
| Migrations au démarrage (main.py) | ✅ run_all() intégré au startup |
| Railway déployé | ✅ facilim.fr — HTTP 200 OK |
| `/health` production | ✅ `{"status":"OK","db":true}` |
| WhatsApp webhook production | ⏳ À configurer Meta Business Manager |
| Test bout en bout | ⏳ À faire |

---

## Variables d'environnement Railway à configurer

### Obligatoires (bloquantes)

| Variable | Description | Valeur |
|---|---|---|
| `OPENAI_API_KEY` | Clé OpenAI GPT-4o | À copier depuis .env |
| `DATABASE_URL` | PostgreSQL Railway | Fournie automatiquement par Railway |
| `JWT_SECRET_KEY` | Sécurité dashboard (> 32 chars) | Générer une valeur forte |
| `WHATSAPP_API_TOKEN` | Token Meta Business | Depuis Meta Developer Console |
| `WHATSAPP_PHONE_NUMBER_ID` | ID numéro WhatsApp | Depuis Meta Developer Console |

### Recommandées (dégradation si absentes)

| Variable | Description |
|---|---|
| `ENCRYPTION_KEY` | Chiffrement données PII — obligatoire HDS |
| `BREVO_API_KEY` | Email 2FA et notifications |
| `OPENAI_MODEL` | Défaut : gpt-4o-mini |

---

## Commandes Railway

```bash
# 1. Appliquer les migrations sur la base PostgreSQL de production
railway run python -c "from app.database.migrations import run_all; run_all()"

# 2. Vérifier la santé du déploiement
railway run python -c "from app.engines.health_check import health_check; import json; print(json.dumps(health_check(check_openai=True).to_dict(), indent=2))"

# 3. Déployer
railway up
```

---

## Configuration Meta Business Manager

1. Aller dans Meta Developer Console → App → Webhooks
2. URL du webhook : `https://[nom-app].railway.app/webhook/whatsapp`
3. Token de vérification : valeur de `WHATSAPP_VERIFY_TOKEN` (à ajouter dans Railway)
4. Événements à activer : `messages`
5. Tester la réception avec un message entrant depuis le numéro de production

---

## Test bout en bout — Scénario de validation

### Profil test recommandé
Adulte autonome, handicap moteur (SEP), demande PCH + RQTH.
Pourquoi : profil bien couvert, données faciles à vérifier, acteurs attendus connus.

### Séquence attendue
```
1. Message WhatsApp entrant → 200 OK immédiat
2. Identification profil → routage vers Corrine (adulte)
3. Questions B prioritaires → relance si réponse courte
4. Section D (emploi) → si applicable
5. Section E (projet de vie) → expression directe demandée
6. Collecte complète → génération narratif + rapport qualité + analyse
7. Dashboard → panneau "Appui à l'évaluation" visible
```

### Résultat attendu
- Score maturité ≥ 60
- Niveau confiance ≥ MOYEN
- Panneau appui visible avec synthèse, facteurs, acteurs
- Aucun blocage technique

---

## Critères de passage en production réelle

- [ ] `/health` retourne `{"status": "OK"}` (ENCRYPTION_KEY définie)
- [ ] Webhook WhatsApp valide (réception confirmée par Meta)
- [ ] Un dossier test traité de bout en bout sans erreur
- [ ] Dashboard accessible et panneau appui visible
- [ ] `retours_terrain.md` ouvert et premier retour documenté
