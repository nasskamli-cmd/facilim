-- Migration 003 — Navigation conversationnelle par onglets
-- Ajoute contexte_navigation_json à la table dossiers pour persister
-- l'onglet courant, l'état de validation en attente, et les onglets déjà validés.

ALTER TABLE dossiers
    ADD COLUMN contexte_navigation_json TEXT DEFAULT '{}';
