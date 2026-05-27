"""
parser.py — Couche d'ingestion : extraction du texte brut.
Reçoit le contenu brut envoyé par l'API (texte libre ou futur PDF/DOCX)
et le normalise en une chaîne de caractères propre pour les étapes suivantes.

Extension future : intégrer PyMuPDF (fitz) pour l'extraction PDF,
python-docx pour les fichiers Word, etc.
"""

import logging
import unicodedata
import re

logger = logging.getLogger(__name__)


def extract_text(raw_input: str | bytes, source_type: str = "text") -> str:
    """
    Extrait et normalise le texte brut depuis différentes sources.

    Args:
        raw_input:   Contenu brut (chaîne texte, ou bytes pour de futurs formats binaires).
        source_type: Type de source : "text" | "pdf" | "docx" (PDF/DOCX non implémentés ici).

    Returns:
        Texte normalisé, prêt pour l'anonymisation.

    Raises:
        ValueError: Si le type de source est inconnu ou si l'extraction échoue.
    """
    # Normalisation défensive : "file" est un alias de "text"
    # (le dashboard envoie parfois "file" quand l'onglet upload est actif)
    if source_type == "file":
        logger.warning("source_type='file' reçu → traité comme 'text'")
        source_type = "text"

    logger.info(f"Extraction du texte | source_type={source_type}")

    if source_type == "text":
        return _clean_text(raw_input if isinstance(raw_input, str) else raw_input.decode("utf-8"))

    elif source_type == "pdf":
        # Placeholder : nécessite l'installation de PyMuPDF (`pip install pymupdf`)
        # import fitz
        # doc = fitz.open(stream=raw_input, filetype="pdf")
        # text = "\n".join(page.get_text() for page in doc)
        # return _clean_text(text)
        raise NotImplementedError("L'extraction PDF sera disponible dans la prochaine version (nécessite PyMuPDF).")

    elif source_type == "docx":
        # Placeholder : nécessite python-docx (`pip install python-docx`)
        raise NotImplementedError("L'extraction DOCX sera disponible dans la prochaine version (nécessite python-docx).")

    else:
        raise ValueError(f"Type de source inconnu : '{source_type}'. Valeurs acceptées : text, pdf, docx.")


def _clean_text(text: str) -> str:
    """
    Nettoyage interne du texte :
    - Normalisation Unicode (NFC) pour harmoniser les caractères accentués
    - Suppression des caractères de contrôle non-imprimables
    - Réduction des espaces/sauts de ligne multiples
    """
    # Normalisation Unicode
    text = unicodedata.normalize("NFC", text)

    # Suppression des caractères de contrôle (sauf \n et \t)
    text = re.sub(r"[^\S\n\t ]+", " ", text)

    # Réduction des lignes vides consécutives (max 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Suppression des espaces en début/fin de chaîne
    text = text.strip()

    if not text:
        raise ValueError("Le texte extrait est vide. Vérifiez le contenu fourni.")

    logger.info(f"Texte extrait avec succès | longueur={len(text)} caractères")
    return text
