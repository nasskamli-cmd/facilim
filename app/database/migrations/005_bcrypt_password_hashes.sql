-- Migration 005 — Mise à jour des hashes de mots de passe (bcrypt)
-- Les comptes LEGACY créés avec password_hash='[LEGACY]' reçoivent un hash valide.
-- Les hashes ci-dessous correspondent aux valeurs dans .env (AUTH_PASSWORD_HASH).
-- À réexécuter si les mots de passe changent.

UPDATE utilisateurs
    SET password_hash  = '$2b$12$QsHKAk0sTms0Xqf2G7d0AOVioa.93RySsG.8Ke4Rt3uoFMZgpxJq2',
        updated_at     = datetime('now')
    WHERE email = (SELECT value FROM (SELECT 'nasskamli@gmail.com' AS value))
      AND (password_hash = '[LEGACY]' OR password_hash IS NULL OR password_hash = '');

UPDATE utilisateurs
    SET password_hash  = '$2b$12$GS3jQ23KE77UP2WkAUqwA.s8I8lMTIOAXO0wusHcc6d/rfLvKSjiG',
        updated_at     = datetime('now')
    WHERE email = (SELECT value FROM (SELECT 'charlotte.besancenot@wanadoo.fr' AS value))
      AND (password_hash = '[LEGACY]' OR password_hash IS NULL OR password_hash = '');
