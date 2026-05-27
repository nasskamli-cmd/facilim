"""
pdf_generator.py — Génération du dossier MDPH au format PDF.

Produit un document structuré et lisible avec :
  - En-tête Facilim
  - Informations générales du dossier
  - Résultat de l'analyse (score, droits, éléments manquants)
  - Historique des échanges WhatsApp avec la famille
  - Recommandation finale

Utilise reportlab (déjà installable via pip install reportlab).
"""

import io
import logging
from datetime import datetime, timezone
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

logger = logging.getLogger(__name__)

# ─── Couleurs Facilim ────────────────────────────────────────────────────────
_BLEU       = HexColor("#1B3A6B")
_VERT       = HexColor("#2ECC9A")
_GRIS_CLAIR = HexColor("#F0F4F8")
_GRIS_TEXTE = HexColor("#718096")
_ROUGE      = HexColor("#E53E3E")
_JAUNE      = HexColor("#D97706")


def generer_pdf_dossier(dossier: dict[str, Any]) -> bytes:
    """
    Génère le PDF du dossier MDPH et retourne les bytes du fichier.

    Args:
        dossier : Dictionnaire complet du dossier (même structure que la base de données).

    Returns:
        Bytes du fichier PDF généré.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Dossier MDPH — Facilim",
        author="Facilim",
    )

    styles  = getSampleStyleSheet()
    story   = []
    analyse = dossier.get("analyse") or {}

    # ── Styles personnalisés ──────────────────────────────────────────────────
    titre_style = ParagraphStyle(
        "titre",
        parent=styles["Normal"],
        fontSize=22,
        textColor=white,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    )
    sous_titre_style = ParagraphStyle(
        "sous_titre",
        parent=styles["Normal"],
        fontSize=11,
        textColor=HexColor("#CBD5E0"),
        fontName="Helvetica",
        alignment=TA_LEFT,
        spaceAfter=0,
    )
    section_style = ParagraphStyle(
        "section",
        parent=styles["Normal"],
        fontSize=13,
        textColor=_BLEU,
        fontName="Helvetica-Bold",
        spaceBefore=14,
        spaceAfter=6,
    )
    corps_style = ParagraphStyle(
        "corps",
        parent=styles["Normal"],
        fontSize=10,
        textColor=HexColor("#2D3748"),
        fontName="Helvetica",
        leading=16,
        spaceAfter=4,
    )
    label_style = ParagraphStyle(
        "label",
        parent=styles["Normal"],
        fontSize=9,
        textColor=_GRIS_TEXTE,
        fontName="Helvetica",
    )

    # ── En-tête coloré ───────────────────────────────────────────────────────
    header_data = [[
        Paragraph("Facilim", titre_style),
        Paragraph("Dossier MDPH", sous_titre_style),
    ]]
    header_table = Table(header_data, colWidths=[9 * cm, 8.5 * cm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), _BLEU),
        ("TOPPADDING",  (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
        ("LEFTPADDING",   (0, 0), (-1, -1), 16),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 16),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.5 * cm))

    # ── Badge statut ─────────────────────────────────────────────────────────
    statut       = dossier.get("statut", "INCONNU")
    statut_color = {"COMPLET": _VERT, "INCOMPLET": _JAUNE, "ERREUR": _ROUGE}.get(statut, _GRIS_TEXTE)
    score        = analyse.get("score_global", 0)

    badge_data = [[
        Paragraph(f"Statut : <b>{statut}</b>", ParagraphStyle("b", parent=corps_style, textColor=statut_color, fontSize=11)),
        Paragraph(f"Score de complétude : <b>{score} / 100</b>", ParagraphStyle("b2", parent=corps_style, alignment=TA_RIGHT, fontSize=11)),
    ]]
    badge_table = Table(badge_data, colWidths=[9 * cm, 8.5 * cm])
    badge_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _GRIS_CLAIR),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS", (0, 0), (-1, -1), [6, 6, 6, 6]),
    ]))
    story.append(badge_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Section 1 — Informations générales ───────────────────────────────────
    story.append(Paragraph("Informations générales", section_style))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#E2E8F0"), spaceAfter=8))

    date_creation = _format_date(dossier.get("created_at", ""))
    date_maj      = _format_date(dossier.get("updated_at", ""))

    infos = [
        ["Identifiant du dossier",  dossier.get("dossier_id", "—")],
        ["Département MDPH",        dossier.get("departement_code", "—")],
        ["Téléphone famille",       dossier.get("telephone_famille", "—")],
        ["Email famille",           dossier.get("email_famille") or "Non renseigné"],
        ["Langue de la famille",    dossier.get("langue_famille") or "Français"],
        ["Date de création",        date_creation],
        ["Dernière mise à jour",    date_maj],
    ]

    info_table = Table(
        [[Paragraph(k, label_style), Paragraph(v, corps_style)] for k, v in infos],
        colWidths=[5 * cm, 12.5 * cm],
    )
    info_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (0, -1),  0),
        ("LEFTPADDING",   (1, 0), (1, -1),  8),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.5, HexColor("#EDF2F7")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Section 2 — Droits identifiés ────────────────────────────────────────
    droits = analyse.get("droits_identifies", [])
    if droits:
        story.append(Paragraph("Droits identifiés", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#E2E8F0"), spaceAfter=8))
        for droit in droits:
            story.append(Paragraph(f"• {droit}", corps_style))
        story.append(Spacer(1, 0.3 * cm))

    # ── Section 3 — Éléments manquants ───────────────────────────────────────
    manquants = analyse.get("elements_manquants", [])
    if manquants:
        story.append(Paragraph("Éléments manquants", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#E2E8F0"), spaceAfter=8))
        for el in manquants:
            story.append(Paragraph(f"• {el}", corps_style))
        story.append(Spacer(1, 0.3 * cm))

    # ── Section 4 — Échanges avec la famille (WhatsApp) ─────────────────────
    reponses = dossier.get("historique_reponses", [])
    if reponses:
        story.append(Paragraph("Échanges avec la famille (WhatsApp)", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#E2E8F0"), spaceAfter=8))

        for i, rep in enumerate(reponses, 1):
            ts   = _format_date(rep.get("timestamp", ""))
            type_msg = rep.get("type", "text")
            lang = rep.get("langue") or "fr"
            texte = rep.get("reponse", "")
            label = f"Réponse {i} — {ts} ({type_msg}, langue : {lang})"
            story.append(Paragraph(label, label_style))
            story.append(Paragraph(texte, corps_style))
            story.append(Spacer(1, 0.2 * cm))

        story.append(Spacer(1, 0.2 * cm))

    # ── Section 5 — Recommandation finale ────────────────────────────────────
    recommandation = analyse.get("recommandation_finale", "")
    if recommandation:
        story.append(Paragraph("Recommandation finale", section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#E2E8F0"), spaceAfter=8))

        reco_data = [[Paragraph(recommandation, corps_style)]]
        reco_table = Table(reco_data, colWidths=[17.5 * cm])
        reco_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), HexColor("#F0FFF4")),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 12),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("BOX",           (0, 0), (-1, -1), 1, _VERT),
        ]))
        story.append(reco_table)
        story.append(Spacer(1, 0.4 * cm))

    # ── Pied de page ─────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#CBD5E0")))
    story.append(Spacer(1, 0.2 * cm))
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y à %H:%M UTC")
    story.append(Paragraph(
        f"Document généré par Facilim le {now_str} · Données hébergées en France · Conforme RGPD",
        ParagraphStyle("footer", parent=label_style, alignment=TA_CENTER, fontSize=8),
    ))

    # ── Construction du PDF ───────────────────────────────────────────────────
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(f"PDF généré | dossier={dossier.get('dossier_id')} | taille={len(pdf_bytes)} octets")
    return pdf_bytes


def _format_date(iso_str: str) -> str:
    """Convertit une date ISO 8601 en format lisible français."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y à %H:%M")
    except Exception:
        return iso_str
