ALTER TABLE dossiers ADD COLUMN cockpit_pro_json TEXT DEFAULT '{}';
-- Migration 013 — FACILIM PROD-1 : persistance du cockpit professionnel consolidé.
-- Câblage uniquement, aucune logique métier nouvelle.
-- NB : l'ALTER doit rester en première position du fichier — le moteur de
-- migration ignore tout bloc SQL commençant par "--" (un commentaire en tête
-- happerait l'ALTER dans le même segment et l'empêcherait de s'exécuter).
