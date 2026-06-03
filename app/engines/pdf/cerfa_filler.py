"""
app/engines/pdf/cerfa_filler.py — Orchestrateur de génération du CERFA 15692*01.

Point d'entrée unique pour la production du PDF CERFA.
Ce fichier ne contient QUE la logique d'assemblage de haut niveau.
Chaque section est déléguée à son module dédié.

Pipeline :
  1. Exécution du moteur de règles métier MDPH
  2. Délégation à chaque mapper de section
  3. Fusion des champs dans une seule dict plate
  4. Persistance du conflit d'autodétermination si détecté
  5. Remplissage du PDF via pdfrw / pypdf (à brancher selon le template disponible)
  6. Stockage et mise à jour du dossier en base
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.database.schemas import DossierCERFA
from app.engines.rules_engine import executer_regles_metier_mdph
from app.engines.pdf.accueil import mapper_accueil
from app.engines.pdf.section_a import mapper_section_a
from app.engines.pdf.section_b import mapper_section_b
from app.engines.pdf.section_c import mapper_section_c
from app.engines.pdf.section_d import mapper_section_d
from app.engines.pdf.section_f import mapper_section_f

logger = logging.getLogger("facilim.pdf.filler")

# Clés internes réservées — ne pas transmettre au moteur PDF
_INTERNAL_KEYS = frozenset({"_aidant_present", "_autodetermination_conflict"})


@dataclass
class CerfaFillerResult:
    """Résultat de la génération CERFA."""
    success:            bool
    dossier_id:         str
    pdf_path:           str | None = None
    champs_remplis:     int = 0
    has_conflict:       bool = False
    conflict_details:   dict | None = None
    error:              str | None = None


class CerfaFiller:
    """
    Orchestrateur de haut niveau pour la génération du CERFA MDPH.

    Usage :
        filler = CerfaFiller(db_conn=db, storage_path="./storage/cerfa")
        result = filler.generer(
            dossier_cerfa=dossier_cerfa,
            cerfa_reponses=cerfa_reponses,
            donnees_pro=donnees_pro,
        )
    """

    def __init__(self, db_conn: Any, storage_path: str = "./storage/cerfa"):
        self.db           = db_conn
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    # ── Point d'entrée principal ─────────────────────────────────────────────

    def generer(
        self,
        dossier_cerfa: DossierCERFA,
        cerfa_reponses: dict | None = None,
        donnees_pro: dict | None = None,
        dossier_id: str | None = None,
        donnees_brutes: dict | None = None,
        service_type: str = "adulte",
    ) -> CerfaFillerResult:
        """
        Orchestre la génération du CERFA 15692*01 pour un dossier donné.

        Args:
            dossier_cerfa:   Modèle Pydantic complet
            cerfa_reponses:  Réponses WhatsApp de l'usager (souhait_orientation_usager, etc.)
            donnees_pro:     Saisies du professionnel (orientation_professionnelle, etc.)
            dossier_id:      ID du dossier en base (pour persistance)

        Returns:
            CerfaFillerResult avec le chemin PDF et les métadonnées de conflit
        """
        cerfa_reponses = cerfa_reponses or {}
        donnees_pro    = donnees_pro    or {}
        eff_id         = dossier_id or str(uuid.uuid4())

        try:
            # Étape 1 — Moteur de règles
            cases_cerfa = executer_regles_metier_mdph(
                dossier_cerfa,
                cerfa_reponses=cerfa_reponses,
                donnees_pro=donnees_pro,
            )

            # Étape 2 — Extraction et persistance du conflit d'autodétermination
            conflit = cases_cerfa.get("_autodetermination_conflict")
            has_conflict = conflit is not None
            if has_conflict and dossier_id:
                self._persister_conflit(dossier_id, conflit)

            # Étape 3 — Construction des champs PDF depuis les données réelles (synthese_json)
            # On utilise field_mapper (qui lit les donnees_brutes) plutôt que les anciens
            # mappers de section (qui lisaient le modèle Pydantic vide DossierCERFA).
            # Les cases_cerfa issues du moteur de règles sont mergées par-dessus.
            from app.engines.pdf.field_mapper import build_field_map
            champs_depuis_donnees = build_field_map(
                donnees_brutes or {}, service_type=service_type
            ) if donnees_brutes else {}

            # Fusionner cases_cerfa (règles métier) par-dessus les données
            champs_pdf: dict[str, Any] = {**champs_depuis_donnees}
            for k, v in cases_cerfa.items():
                if k not in _INTERNAL_KEYS and v not in (None, False, ""):
                    champs_pdf[k] = "/Yes" if v is True else str(v)

            logger.info(
                f"[CERFA] {len(champs_pdf)} champs assemblés | "
                f"dossier={eff_id[:8]} | conflit_autod={has_conflict}"
            )

            # Étape 5 — Remplissage du PDF (brancher pdfrw/pypdf ici)
            pdf_path = self._remplir_pdf(
                eff_id, champs_pdf,
                donnees=donnees_brutes,
                service_type=service_type,
            )

            # Étape 6 — Mise à jour de la trace en base
            if dossier_id and pdf_path:
                self._mettre_a_jour_dossier(dossier_id, pdf_path)

            return CerfaFillerResult(
                success=True,
                dossier_id=eff_id,
                pdf_path=pdf_path,
                champs_remplis=len(champs_pdf),
                has_conflict=has_conflict,
                conflict_details=conflit,
            )

        except Exception as e:
            logger.error(f"[CERFA] Erreur génération | dossier={eff_id[:8]} | {e}", exc_info=True)
            return CerfaFillerResult(
                success=False,
                dossier_id=eff_id,
                error=str(e),
            )

    # ── Persistance du conflit d'autodétermination ───────────────────────────

    def _persister_conflit(self, dossier_id: str, conflit: dict) -> None:
        """
        Enregistre le conflit dans la table dossiers :
          has_autodetermination_conflict = 1
          conflict_history_json = liste append-only des conflits horodatés
        """
        row = self.db.execute(
            "SELECT conflict_history_json FROM dossiers WHERE id = ?",
            (dossier_id,),
        ).fetchone()

        if not row:
            return

        historique = json.loads(row["conflict_history_json"] or "[]")
        historique.append(conflit)

        self.db.execute(
            """
            UPDATE dossiers SET
                has_autodetermination_conflict = 1,
                conflict_history_json          = ?,
                updated_at                     = ?
            WHERE id = ?
            """,
            (
                json.dumps(historique, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
                dossier_id,
            ),
        )
        logger.info(
            f"[CERFA] Conflit autodétermination persisté | dossier={dossier_id[:8]} | "
            f"usager='{conflit.get('souhait_usager','?')}' vs "
            f"pro='{conflit.get('orientation_pro','?')}'"
        )

    # ── Remplissage PDF ───────────────────────────────────────────────────────

    def _remplir_pdf(
        self,
        dossier_id: str,
        champs: dict[str, Any],
        donnees: dict[str, Any] | None = None,
        service_type: str = "adulte",
    ) -> str | None:
        """
        Injecte les données dans le template CERFA PDF officiel 15692*01.

        Utilise :
          1. field_mapper.build_field_map() pour convertir donnees → champs PDF réels
          2. pdfrw pour injecter les valeurs dans les 580 champs du formulaire
          3. Fallback JSON si pdfrw absent (ne devrait pas arriver, pdfrw est installé)

        Template : storage/templates/cerfa_15692_01.pdf (inclus dans le projet)
        """
        import pdfrw

        template_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "storage", "templates",
            "cerfa_15692_01.pdf",
        )

        output_filename = (
            f"cerfa_{dossier_id[:8]}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        output_path = os.path.join(self.storage_path, output_filename)

        if not os.path.isfile(template_path):
            logger.error("[CERFA] Template PDF absent : %s", template_path)
            stub_path = output_path.replace(".pdf", "_champs.json")
            with open(stub_path, "w", encoding="utf-8") as f:
                json.dump({"dossier_id": dossier_id, "champs": champs},
                          f, ensure_ascii=False, indent=2)
            return stub_path

        # ── Construire le mapping réel depuis les données brutes ──────────────
        from app.engines.pdf.field_mapper import build_field_map
        pdf_fields = build_field_map(donnees or {}, service_type=service_type)

        # Fusionner avec les champs déjà calculés par les mappers de section
        # (rules_engine cases, cases CERFA) — les champs rules ont priorité
        merged = {**pdf_fields}
        for k, v in champs.items():
            if v not in (None, "", False) and not k.startswith("_"):
                merged[k] = "/Yes" if v is True else str(v)

        # ── Injection dans le PDF ─────────────────────────────────────────────
        template = pdfrw.PdfReader(template_path)
        filled   = 0

        for page in template.pages:
            annotations = page.get("/Annots")
            if not annotations:
                continue
            for annot in annotations:
                field_name = annot.get("/T")
                if not field_name:
                    continue
                clean = str(field_name).strip("()")
                if clean not in merged:
                    continue

                val        = merged[clean]
                _ft        = annot.get("/FT")
                field_type = str(_ft).strip("()") if _ft else ""

                if field_type == "/Btn":
                    # Case à cocher
                    checked = val in ("/Yes", "Yes", "true", "True", True)
                    on_val  = pdfrw.PdfName("Yes")
                    off_val = pdfrw.PdfName("Off")
                    annot.update(pdfrw.PdfDict(
                        AS=on_val  if checked else off_val,
                        V =on_val  if checked else off_val,
                    ))
                else:
                    # Champ texte
                    annot.update(pdfrw.PdfDict(V=str(val), AP=""))

                filled += 1

        # NeedAppearances = true → force le navigateur à recalculer l'affichage des champs
        if template.Root.AcroForm:
            template.Root.AcroForm.update(
                pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject("true"))
            )

        pdfrw.PdfWriter().write(output_path, template)
        logger.info(
            "[CERFA] PDF généré | %d/%d champs remplis | dossier=%s | path=%s",
            filled, len(merged), dossier_id[:8], output_path,
        )

        # Tentative d'aplatissement avec pypdf pour garantir l'affichage dans tous les navigateurs
        try:
            import io
            from pypdf import PdfReader, PdfWriter
            reader_flat = PdfReader(output_path)
            writer_flat = PdfWriter()
            writer_flat.append(reader_flat)
            # Supprimer AcroForm pour forcer l'aplatissement visuel
            if "/AcroForm" in writer_flat._root_object:
                writer_flat._root_object["/AcroForm"].update(
                    {pdfrw.objects.pdfname.PdfName("NeedAppearances"): True}
                )
            flat_path = output_path.replace(".pdf", "_flat.pdf")
            with open(flat_path, "wb") as f:
                writer_flat.write(f)
            if os.path.getsize(flat_path) > 10_000:
                os.replace(flat_path, output_path)
                logger.info("[CERFA] PDF aplati avec pypdf")
        except Exception as e:
            logger.debug("[CERFA] Aplatissement optionnel échoué : %s", e)

        return output_path

    # ── Mise à jour de la trace base ─────────────────────────────────────────

    def _mettre_a_jour_dossier(self, dossier_id: str, pdf_path: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """
            UPDATE dossiers SET
                cerfa_chemin    = ?,
                cerfa_version   = '15692*01',
                cerfa_genere_le = ?,
                updated_at      = ?
            WHERE id = ?
            """,
            (pdf_path, now, now, dossier_id),
        )
