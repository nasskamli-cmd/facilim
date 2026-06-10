-- cleanup_orphelins_suppression.sql
-- ─────────────────────────────────────────────────────────────────────────────
-- Nettoyage PROD one-time : alertes et relances ORPHELINES laissées par d'anciennes
-- suppressions de dossier (faites AVANT le correctif delete_dossier).
--
-- IDEMPOTENT : ré-exécutable sans effet supplémentaire (les WHERE ne re-matchent
-- plus une fois les lignes traitées). Ne touche PAS aux dossiers non supprimés.
-- Aucune suppression dure : l'historique reste auditable (acquittee / ANNULEE).
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Acquitter les alertes rattachées à un dossier supprimé (deleted_at non nul).
UPDATE alertes
   SET acquittee = 1
 WHERE acquittee = 0
   AND dossier_id IN (SELECT id FROM dossiers WHERE deleted_at IS NOT NULL);

-- 2. Annuler les relances PLANIFIEE rattachées à un dossier supprimé.
UPDATE relances
   SET statut = 'ANNULEE'
 WHERE statut = 'PLANIFIEE'
   AND dossier_id IN (SELECT id FROM dossiers WHERE deleted_at IS NOT NULL);

-- Contrôle (doit renvoyer 0, 0) :
--   SELECT
--     (SELECT COUNT(*) FROM alertes  WHERE acquittee = 0
--        AND dossier_id IN (SELECT id FROM dossiers WHERE deleted_at IS NOT NULL)) AS alertes_orphelines,
--     (SELECT COUNT(*) FROM relances WHERE statut = 'PLANIFIEE'
--        AND dossier_id IN (SELECT id FROM dossiers WHERE deleted_at IS NOT NULL)) AS relances_orphelines;
