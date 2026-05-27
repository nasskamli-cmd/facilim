"""
rapo_filler.py — Génération de la lettre RAPO via un agent IA spécialisé
en droit des personnes handicapées.

Le Recours Administratif Préalable Obligatoire (RAPO) est la procédure à suivre
avant tout recours contentieux contre une décision MDPH. L'agent utilise :
  - La loi n° 2005-102 du 11 février 2005 (égalité des droits et des chances)
  - Le Code de l'Action Sociale et des Familles (CASF), L. 241-1 à L. 241-10
  - Les bases légales AAH, AEEH, PCH, RQTH, CMI selon les droits en jeu
  - La jurisprudence CDAPH et les délais réglementaires

Le résultat est mis en page dans un PDF A4 au format lettre administrative.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_JUSTIFY

from config import get_settings

logger   = logging.getLogger(__name__)
settings = get_settings()

# ─── Couleurs ────────────────────────────────────────────────────────────────
_BLEU     = HexColor("#1B3A6B")
_GRIS     = HexColor("#718096")
_VERT     = HexColor("#2ECC9A")

_SYSTEM_PROMPT = """\
Tu es un juriste expert en droit du handicap et des personnes handicapées en France,
spécialisé dans les procédures MDPH et les recours administratifs.

Ta mission : rédiger une lettre de Recours Administratif Préalable Obligatoire (RAPO)
complète, argumentée juridiquement et personnalisée au dossier fourni.

Références légales à mobiliser selon les droits en jeu :
- Loi n° 2005-102 du 11 février 2005 pour l'égalité des droits et des chances,
  la participation et la citoyenneté des personnes handicapées
- CASF art. L.241-1 à L.241-10 (missions CDAPH, droits reconnaissables)
- AAH : CASF art. L.821-1 à L.821-7 + taux d'incapacité ≥ 80 % ou 50-79 %
  avec restriction substantielle d'emploi
- AEEH : CSS art. L.541-1 ; CASF art. R.541-1
- PCH : CASF art. L.245-1 à L.245-14 + critères d'éligibilité (difficultés absolues
  ou graves dans la réalisation d'activités)
- RQTH : CASF art. L.5213-1 Code du travail
- CMI mobilité / stationnement : CASF art. L.241-3
- Délai RAPO : 2 mois à compter de la notification (CASF R. 241-33)
- Si pas de réponse sous 2 mois : décision implicite de rejet
- Voie suivante : Tribunal Administratif ou TASS selon nature du droit

Structure OBLIGATOIRE de ta lettre (utilise ces marqueurs exacts) :
[OBJET] : objet de la lettre en une ligne
[INTRO] : formule de saisine + référence à la décision contestée
[FAITS] : résumé des faits et de la situation de l'enfant / de la personne
[MOYENS_FAIT] : arguments de fait (situation médicale, besoins réels, pièces)
[MOYENS_DROIT] : arguments juridiques (articles de loi, critères non respectés)
[DEMANDE] : demande précise de révision ou d'annulation de la décision
[CLÔTURE] : formule de politesse professionnelle

Adapte les arguments aux droits spécifiques refusés ou insuffisants.
Sois précis, factuel, et cite les articles de loi pertinents.
Longueur : entre 400 et 700 mots, ton juridique professionnel mais accessible.
"""


def _construire_contexte(dossier: dict[str, Any]) -> str:
    """Synthétise les informations du dossier en un contexte lisible pour l'IA."""
    analyse = dossier.get("analyse") or {}
    droits   = ", ".join(analyse.get("droits_identifies", [])) or "non précisés"
    manquants = "; ".join(analyse.get("elements_manquants", [])) or "aucun"
    reco      = analyse.get("recommandation_finale", "")

    enfant = " ".join(filter(None, [
        dossier.get("prenom_enfant", ""),
        dossier.get("nom_enfant", ""),
    ])) or "l'enfant"

    ddn    = dossier.get("ddn_enfant", "non renseignée")
    dept   = dossier.get("departement_code", "—")
    dossier_id = dossier.get("dossier_id", "—")[:8]

    context = f"""DOSSIER MDPH — Référence : {dossier_id}
Département : {dept}
Enfant / personne concernée : {enfant}, né(e) le {ddn}

DROITS IDENTIFIÉS DANS LE DOSSIER : {droits}
ÉLÉMENTS SIGNALÉS COMME MANQUANTS : {manquants}
RECOMMANDATION DE L'ANALYSE : {reco}

Ce RAPO est rédigé suite à une décision de la CDAPH jugée insuffisante
ou non conforme aux droits auxquels la personne peut prétendre.
Rédige la lettre en tenant compte de l'ensemble de ces éléments.
"""
    return context


def _parse_sections(texte: str) -> dict[str, str]:
    """Extrait les sections marquées [TAG] du texte généré par l'IA."""
    tags = ["OBJET", "INTRO", "FAITS", "MOYENS_FAIT", "MOYENS_DROIT", "DEMANDE", "CLÔTURE"]
    sections: dict[str, str] = {}
    for i, tag in enumerate(tags):
        start_marker = f"[{tag}]"
        start = texte.find(start_marker)
        if start == -1:
            continue
        start += len(start_marker)
        # Fin = début du prochain tag ou fin de chaîne
        end = len(texte)
        for next_tag in tags[i + 1:]:
            pos = texte.find(f"[{next_tag}]", start)
            if pos != -1:
                end = min(end, pos)
                break
        sections[tag] = texte[start:end].strip()
    return sections


def remplir_rapo(dossier: dict[str, Any]) -> bytes:
    """
    Génère la lettre RAPO complète via GPT-4o et la met en forme en PDF.

    Args:
        dossier : Dictionnaire complet du dossier.

    Returns:
        Bytes du PDF de la lettre RAPO.

    Raises:
        RuntimeError : En cas d'échec de l'appel à l'API OpenAI.
    """
    # ── Appel à l'agent juridique ─────────────────────────────────────────────
    contexte = _construire_contexte(dossier)

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": contexte},
            ],
            temperature=0.4,
            max_tokens=1800,
        )
        lettre_brute = response.choices[0].message.content.strip()
        logger.info(f"Lettre RAPO générée | {len(lettre_brute)} caractères")
    except Exception as exc:
        raise RuntimeError(f"Agent RAPO : appel API échoué → {exc}") from exc

    sections = _parse_sections(lettre_brute)

    # ── Mise en page PDF ──────────────────────────────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title="Lettre RAPO — Facilim",
    )

    styles = getSampleStyleSheet()
    titre_style = ParagraphStyle(
        "titre", parent=styles["Normal"],
        fontSize=13, fontName="Helvetica-Bold",
        textColor=_BLEU, spaceBefore=0, spaceAfter=6,
    )
    corps_style = ParagraphStyle(
        "corps", parent=styles["Normal"],
        fontSize=10, fontName="Helvetica",
        leading=16, alignment=TA_JUSTIFY,
        spaceAfter=10,
    )
    label_style = ParagraphStyle(
        "label", parent=styles["Normal"],
        fontSize=9, fontName="Helvetica",
        textColor=_GRIS,
    )
    right_style = ParagraphStyle(
        "right", parent=styles["Normal"],
        fontSize=10, fontName="Helvetica",
        alignment=TA_RIGHT, spaceAfter=4,
    )

    story = []
    now_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    # ── En-tête expéditeur ────────────────────────────────────────────────────
    story.append(Paragraph(
        "<b>Madame / Monsieur,</b><br/>[Prénom Nom du représentant légal]<br/>"
        "[Adresse complète]<br/>[Code postal — Commune]<br/>[Email — Téléphone]",
        corps_style,
    ))
    story.append(Spacer(1, 0.5 * cm))

    # ── Destinataire ──────────────────────────────────────────────────────────
    story.append(Paragraph(
        "<b>À l'attention de</b><br/>Madame / Monsieur le(la) directeur(trice)<br/>"
        "de la MDPH<br/>[Adresse de la MDPH]",
        corps_style,
    ))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(f"Fait le {now_str}", right_style))
    story.append(Spacer(1, 0.3 * cm))

    # ── Objet ─────────────────────────────────────────────────────────────────
    objet = sections.get("OBJET", "Recours Administratif Préalable Obligatoire (RAPO)")
    story.append(Paragraph(f"<b>Objet : {objet}</b>", corps_style))

    short_id = (dossier.get("dossier_id") or "")[:8]
    if short_id:
        story.append(Paragraph(f"Référence dossier Facilim : {short_id}", label_style))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#E2E8F0"), spaceAfter=12))

    # ── Corps de la lettre ───────────────────────────────────────────────────
    section_order = [
        ("INTRO",        None),
        ("FAITS",        "Exposé des faits"),
        ("MOYENS_FAIT",  "Arguments de fait"),
        ("MOYENS_DROIT", "Fondements juridiques"),
        ("DEMANDE",      "Demande"),
        ("CLÔTURE",      None),
    ]

    for tag, titre in section_order:
        contenu = sections.get(tag, "")
        if not contenu:
            continue
        if titre:
            story.append(Paragraph(titre, titre_style))
        # Convertit les sauts de ligne en <br/>
        contenu_html = contenu.replace("\n\n", "<br/><br/>").replace("\n", " ")
        story.append(Paragraph(contenu_html, corps_style))

    # Si l'IA n'a pas suivi les marqueurs, on insère quand même le texte brut
    if not sections:
        corps_brut = lettre_brute.replace("\n\n", "<br/><br/>").replace("\n", " ")
        story.append(Paragraph(corps_brut, corps_style))

    # ── Pied de page ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#CBD5E0")))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "Document généré par Facilim · Lettre à relire et signer avant envoi recommandé avec AR",
        ParagraphStyle("footer", parent=label_style, fontSize=8),
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(f"PDF RAPO généré | {len(pdf_bytes)} octets")
    return pdf_bytes
