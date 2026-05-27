"""
pch_filler.py — Génération du formulaire PCH Parentalité pré-rempli.

Contexte technique :
    Le formulaire source (static/forms/pch_parentalite.pdf) est un PDF image
    sans champs AcroForm — la technique de pypdf utilisée pour le CERFA 15692
    ne s'applique pas. On génère donc un nouveau document ReportLab qui reproduit
    fidèlement la structure officielle (sections, libellés, mise en page) avec les
    données du dossier déjà inscrites. La famille imprime, signe, et joint les
    pièces obligatoires.

Limitation connue :
    Le modèle de dossier Facilim stocke les données de l'*enfant*. La section 1
    du formulaire PCH identifie le *parent* bénéficiaire de la PCH. Les champs
    du demandeur sont laissés vides pour saisie manuelle ; seuls le n° de dossier
    et les données de l'enfant sont pré-remplis.
"""

import io
import logging
from datetime import date
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

# ── Couleurs reprises de la charte graphique officielle du formulaire ────────
_BLEU_MDPH   = HexColor("#1D4E8F")   # bleu des sections
_BLEU_CLAIR  = HexColor("#D6E4F7")   # fond des en-têtes de section
_GRIS_FOND   = HexColor("#F5F5F5")   # fond des lignes de tableau
_GRIS_BORD   = HexColor("#CCCCCC")   # bordures
_ROUGE_RF    = HexColor("#C0392B")   # rouge République Française
_NOIR        = HexColor("#1A1A1A")


def remplir_pch(dossier: dict[str, Any]) -> bytes:
    """
    Génère le formulaire PCH Parentalité pré-rempli au format PDF.

    Args:
        dossier : Dictionnaire complet du dossier Facilim.

    Returns:
        Bytes du PDF généré.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="Formulaire PCH Parentalité — MDPH",
        author="Facilim",
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── Styles ───────────────────────────────────────────────────────────────
    s_titre_header = ParagraphStyle(
        "titre_header", parent=styles["Normal"],
        fontSize=15, fontName="Helvetica-Bold",
        textColor=white, alignment=TA_LEFT,
    )
    s_sous_header = ParagraphStyle(
        "sous_header", parent=styles["Normal"],
        fontSize=8, fontName="Helvetica",
        textColor=HexColor("#D0D8E8"), alignment=TA_LEFT, leading=11,
    )
    s_section = ParagraphStyle(
        "section", parent=styles["Normal"],
        fontSize=10, fontName="Helvetica-Bold",
        textColor=white, alignment=TA_LEFT,
    )
    s_label = ParagraphStyle(
        "label", parent=styles["Normal"],
        fontSize=9, fontName="Helvetica",
        textColor=HexColor("#444444"),
    )
    s_valeur = ParagraphStyle(
        "valeur", parent=styles["Normal"],
        fontSize=9, fontName="Helvetica-Bold",
        textColor=_NOIR,
    )
    s_note = ParagraphStyle(
        "note", parent=styles["Normal"],
        fontSize=7.5, fontName="Helvetica-Oblique",
        textColor=HexColor("#888888"), leading=10,
    )
    s_corps = ParagraphStyle(
        "corps", parent=styles["Normal"],
        fontSize=8.5, fontName="Helvetica",
        textColor=_NOIR, leading=12,
    )
    s_footer = ParagraphStyle(
        "footer", parent=styles["Normal"],
        fontSize=7, fontName="Helvetica",
        textColor=HexColor("#999999"), alignment=TA_CENTER,
    )

    # ── Extraction des données ────────────────────────────────────────────────
    dossier_id  = (dossier.get("dossier_id") or "")[:8].upper()
    nom_enfant  = (dossier.get("nom_enfant") or "").upper()
    prenom_enf  = dossier.get("prenom_enfant") or ""
    ddn_enf     = dossier.get("ddn_enfant") or ""
    adresse     = dossier.get("adresse_enfant") or ""
    cp          = dossier.get("cp_enfant") or ""
    commune     = (dossier.get("commune_enfant") or "").upper()
    adresse_complete = " ".join(filter(None, [adresse, cp, commune])) or "—"
    telephone   = dossier.get("telephone_famille") or ""
    dept        = dossier.get("departement_code") or ""
    today_str   = date.today().strftime("%d/%m/%Y")

    def _vide_ou(valeur: str) -> str:
        """Retourne la valeur ou un trait de soulignement si vide."""
        return valeur if valeur else "___________________________"

    # ─────────────────────────────────────────────────────────────────────────
    # EN-TÊTE — reproduit la bannière bleue du formulaire officiel
    # ─────────────────────────────────────────────────────────────────────────
    header_data = [[
        Paragraph(
            "DEMANDE À LA MDPH",
            s_titre_header,
        ),
        Paragraph(
            "Article R.146-26 du code de l'action sociale et des familles<br/>"
            "<b>Formulaire de demande de la prestation de compensation du<br/>"
            "handicap (PCH) au titre de l'aide à la parentalité</b><br/>"
            "pour les personnes ayant un droit ouvert à la PCH",
            s_sous_header,
        ),
        Paragraph(
            f"<b>Réf. Facilim</b><br/>{dossier_id}<br/><br/>"
            f"<b>Dépt.</b> {dept}",
            ParagraphStyle("ref", parent=s_sous_header, alignment=TA_RIGHT),
        ),
    ]]
    header_table = Table(header_data, colWidths=[5 * cm, 9.5 * cm, 3 * cm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _BLEU_MDPH),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3 * cm))

    # ── Bandeau d'information ─────────────────────────────────────────────────
    info_data = [[Paragraph(
        "Vous avez un droit ouvert à la PCH et souhaitez bénéficier des nouvelles "
        "aides à la parentalité. Vous devez utiliser ce formulaire pour adresser "
        "votre demande à la MDPH/MDA, accompagné des pièces justificatives indiquées.",
        s_corps,
    )]]
    info_table = Table(info_data, colWidths=[17.5 * cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), HexColor("#EBF3FB")),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("BOX",           (0, 0), (-1, -1), 0.5, _BLEU_MDPH),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.4 * cm))

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 1 — Identification et situation du demandeur
    # ─────────────────────────────────────────────────────────────────────────
    story.append(_section_header("1", "Identification et situation du demandeur", s_section))
    story.append(Spacer(1, 0.15 * cm))

    # Note explicative sur les données disponibles
    story.append(Paragraph(
        "⚠ Les champs ci-dessous concernent le parent bénéficiaire de la PCH. "
        "Ces données ne sont pas encore renseignées dans Facilim — merci de les "
        "compléter manuellement.",
        s_note,
    ))
    story.append(Spacer(1, 0.2 * cm))

    s1_rows = [
        ["Nom de naissance :",             "___________________________"],
        ["Prénom(s) :",                    "___________________________"],
        ["Date de naissance :",            "___________________________"],
        ["Adresse :",                      adresse_complete],
        ["N° de dossier à la MDPH :",      dossier_id],
        ["Date(s) d'attribution de la PCH :", "___________________________"],
        ["Nombre d'enfants :",             "1" if nom_enfant else "___"],
    ]
    story.append(_tableau_section(s1_rows, s_label, s_valeur))
    story.append(Spacer(1, 0.2 * cm))

    # Monoparentalité
    mono_data = [[
        Paragraph("Situation de monoparentalité :", s_label),
        Paragraph("□ Oui (compléter l'attestation jointe)    □ Non", s_valeur),
    ]]
    mono_table = Table(mono_data, colWidths=[7 * cm, 10.5 * cm])
    mono_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 0.5, _GRIS_BORD),
        ("BACKGROUND",    (0, 0), (-1, -1), _GRIS_FOND),
    ]))
    story.append(mono_table)
    story.append(Spacer(1, 0.4 * cm))

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 2 — Identification de la demande
    # ─────────────────────────────────────────────────────────────────────────
    story.append(_section_header("2", "Identification de la demande", s_section))
    story.append(Spacer(1, 0.15 * cm))

    s2_data = [
        [
            Paragraph("<b>PCH Aide humaine à la parentalité</b>", s_valeur),
            Paragraph("□  à cocher si demandé", s_label),
        ],
        [
            Paragraph(
                "<i>Conditions cumulatives : Être bénéficiaire de l'élément 1 aide "
                "humaine de la PCH ET avoir au moins un enfant âgé entre 0 et 7 ans.</i>",
                s_note,
            ),
            Paragraph("", s_label),
        ],
        [
            Paragraph("<b>PCH Aides techniques à la parentalité</b>", s_valeur),
            Paragraph("□  à cocher si demandé", s_label),
        ],
        [
            Paragraph(
                "<i>Conditions cumulatives : Être bénéficiaire de la PCH ET avoir un "
                "enfant qui vient de naître ou va naître, ou qui tirera son 3ème ou "
                "5ème anniversaire au cours de la période d'attribution de la PCH.</i>",
                s_note,
            ),
            Paragraph("", s_label),
        ],
    ]
    s2_table = Table(s2_data, colWidths=[13 * cm, 4.5 * cm])
    s2_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("BACKGROUND",    (0, 0), (-1, 0),  _GRIS_FOND),
        ("BACKGROUND",    (0, 2), (-1, 2),  _GRIS_FOND),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.5, _GRIS_BORD),
        ("LINEABOVE",     (0, 2), (-1, 2),  0.5, _GRIS_BORD),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.5, _GRIS_BORD),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(s2_table)
    story.append(Spacer(1, 0.4 * cm))

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 3 — Identification et date(s) de naissance de(s) enfant(s)
    # ─────────────────────────────────────────────────────────────────────────
    story.append(_section_header("3", "Identification et date(s) de naissance de(s) enfant(s)", s_section))
    story.append(Spacer(1, 0.15 * cm))

    # En-tête du tableau enfants
    enfants_header = [
        Paragraph("<b>Nom</b>", s_label),
        Paragraph("<b>Prénom</b>", s_label),
        Paragraph("<b>Date de naissance</b>", s_label),
    ]
    enfants_rows = [enfants_header]

    # Ligne pré-remplie avec l'enfant du dossier
    enfants_rows.append([
        Paragraph(nom_enfant or "___________________________", s_valeur),
        Paragraph(prenom_enf or "___________________________", s_valeur),
        Paragraph(ddn_enf or "___________________________", s_valeur),
    ])

    # Lignes vides supplémentaires (4 enfants de plus possibles)
    for _ in range(4):
        enfants_rows.append([
            Paragraph("___________________________", s_label),
            Paragraph("___________________________", s_label),
            Paragraph("___________________________", s_label),
        ])

    enfants_table = Table(enfants_rows, colWidths=[5.8 * cm, 5.8 * cm, 5.9 * cm])
    enfants_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  _BLEU_CLAIR),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.5, _GRIS_BORD),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, _GRIS_FOND]),
    ]))
    story.append(enfants_table)
    story.append(Spacer(1, 0.4 * cm))

    # ─────────────────────────────────────────────────────────────────────────
    # SECTION 4 — Pièces à joindre
    # ─────────────────────────────────────────────────────────────────────────
    story.append(_section_header("4", "Pièces à joindre", s_section))
    story.append(Spacer(1, 0.15 * cm))

    pieces_data = [[Paragraph(
        "<b>Pièces obligatoires :</b><br/>"
        "Extrait d'acte de naissance de chacun des enfants "
        "(si vous attendez un enfant, ce document sera à fournir ultérieurement).",
        s_corps,
    )]]
    pieces_table = Table(pieces_data, colWidths=[17.5 * cm])
    pieces_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), HexColor("#E8F4FD")),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("BOX",           (0, 0), (-1, -1), 0.5, _BLEU_MDPH),
    ]))
    story.append(pieces_table)
    story.append(Spacer(1, 0.5 * cm))

    # ─────────────────────────────────────────────────────────────────────────
    # BLOC SIGNATURE
    # ─────────────────────────────────────────────────────────────────────────
    sig_data = [
        [
            Paragraph(f"Fait le : <b>{today_str}</b>", s_valeur),
            Paragraph("Signature :", s_label),
        ],
        [
            Paragraph(
                "□ De la personne concernée<br/>□ De son représentant légal",
                s_corps,
            ),
            Paragraph("", s_label),
        ],
    ]
    sig_table = Table(sig_data, colWidths=[8 * cm, 9.5 * cm])
    sig_table.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, _GRIS_BORD),
        ("LINEAFTER",     (0, 0), (0, -1),  0.5, _GRIS_BORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("SPAN",          (1, 0), (1, 1)),
        ("VALIGN",        (1, 0), (1, 1),   "TOP"),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 0.3 * cm))

    # Case certification
    certif_data = [[Paragraph(
        "□ En cochant cette case, je certifie sur l'honneur l'exactitude des "
        "informations déclarées ci-dessus.",
        s_corps,
    )]]
    certif_table = Table(certif_data, colWidths=[17.5 * cm])
    certif_table.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, _GRIS_BORD),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    story.append(certif_table)
    story.append(Spacer(1, 0.4 * cm))

    # ── Mention RGPD ─────────────────────────────────────────────────────────
    story.append(Paragraph(
        "Les informations personnelles recueillies par la MDPH lors de l'examen, "
        "du traitement et du suivi de votre demande font l'objet d'un traitement "
        "informatique. Vous pouvez demander à la MDPH de récupérer, corriger, "
        "supprimer ou réutiliser ces informations (droits prévus dans la loi "
        "« Informatique et Libertés » du 6 janvier 1978 modifiée en 2018).",
        s_note,
    ))

    # ── Pied de page Facilim ──────────────────────────────────────────────────
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#CCCCCC")))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(
        f"Document généré par Facilim · Réf. dossier {dossier_id} · "
        f"17 avril 2021 — Formulaire PCH Parentalité",
        s_footer,
    ))

    # ── Build ─────────────────────────────────────────────────────────────────
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(
        f"PCH Parentalité généré | dossier={dossier.get('dossier_id', '?')} "
        f"| enfant={nom_enfant} {prenom_enf}"
    )
    return pdf_bytes


# ── Helpers ───────────────────────────────────────────────────────────────────

def _section_header(numero: str, titre: str, style: ParagraphStyle) -> Table:
    """Génère une ligne d'en-tête de section numérotée sur fond bleu."""
    from reportlab.platypus import Table, TableStyle

    data = [[
        Paragraph(f"<b>{numero}</b>", style),
        Paragraph(titre, style),
    ]]
    table = Table(data, colWidths=[1 * cm, 16.5 * cm])
    table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _BLEU_MDPH),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (0, -1),  10),
        ("LEFTPADDING",   (1, 0), (1, -1),  8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _tableau_section(
    rows: list[list[str]],
    s_label: ParagraphStyle,
    s_valeur: ParagraphStyle,
) -> Table:
    """Construit un tableau label / valeur pour les sections du formulaire."""
    from reportlab.platypus import Table, TableStyle

    data = [
        [Paragraph(label, s_label), Paragraph(valeur, s_valeur)]
        for label, valeur in rows
    ]
    table = Table(data, colWidths=[7 * cm, 10.5 * cm])
    table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [white, _GRIS_FOND]),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.5, _GRIS_BORD),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.5, _GRIS_BORD),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table
