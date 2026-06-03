-- Migration 004 — Mise a jour valeur par defaut de persona_actif
-- L'ancien systeme utilisait 'intake'. Le nouveau pipeline utilise 'identification'.
-- Les deux sont geres par l'alias dans services/conversation/router.py,
-- mais la valeur par defaut doit refleter le nouvel etat initial.

-- SQLite ne supporte pas ALTER TABLE DEFAULT directement.
-- On met a jour les sessions existantes qui ont encore 'intake'.
UPDATE sessions_whatsapp
    SET persona_actif = 'identification'
    WHERE persona_actif = 'intake';
