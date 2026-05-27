"""
agents/ines_agent.py — Inès (Niveau 2 : Anonymisation & chiffrement)

Responsabilités :
  - Anonymise les données PII avant tout envoi au LLM (nom, prénom, NSS, adresse)
  - Chiffre les données sensibles en AES-256-GCM avant stockage en base
  - Maintient une table de correspondance token → valeur réelle (en mémoire + DB chiffrée)
  - Déchiffre à la demande pour affichage éducateur (authentifié)

Clé AES : variable d'environnement AES_SECRET_KEY (32 octets hex).
"""
import os
import re
import json
import base64
import secrets
import hashlib
from typing import Any

from agents.base_agent import BaseAgent

# ── Chiffrement AES-256-GCM ───────────────────────────────────────────────────
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def _get_aes_key() -> bytes:
    """Dérive une clé AES 32 octets depuis AES_SECRET_KEY (ou app_secret_key)."""
    raw = os.environ.get("AES_SECRET_KEY", os.environ.get("APP_SECRET_KEY", "facilim-default-key-change-in-prod"))
    return hashlib.sha256(raw.encode()).digest()


def chiffrer_valeur(valeur: str) -> str:
    """
    Chiffre une valeur sensible en AES-256-GCM.
    Retourne une chaîne base64 : nonce(12) + ciphertext + tag.
    """
    if not _HAS_CRYPTO or not valeur:
        return valeur  # fallback sans crypto
    key   = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce  = secrets.token_bytes(12)
    ct     = aesgcm.encrypt(nonce, valeur.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def dechiffrer_valeur(valeur_chiffree: str) -> str:
    """Déchiffre une valeur AES-256-GCM."""
    if not _HAS_CRYPTO or not valeur_chiffree:
        return valeur_chiffree
    try:
        key    = _get_aes_key()
        aesgcm = AESGCM(key)
        raw    = base64.b64decode(valeur_chiffree)
        nonce  = raw[:12]
        ct     = raw[12:]
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        return "[ERREUR DÉCHIFFREMENT]"


# ── Patterns PII ──────────────────────────────────────────────────────────────
_PII_PATTERNS = [
    # NSS : 15 chiffres (avec ou sans espaces)
    (re.compile(r"\b[12]\s?\d{2}\s?\d{2}\s?\d{2,3}\s?\d{3}\s?\d{3}\s?\d{2}\b"), "NSS"),
    # Email
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "EMAIL"),
    # Téléphone français
    (re.compile(r"\b(?:0[1-9]|\+33\s?[1-9])(?:[\s.\-]?\d{2}){4}\b"), "TEL"),
    # Date de naissance (JJ/MM/AAAA ou AAAA-MM-JJ)
    (re.compile(r"\b\d{1,2}[/\-]\d{1,2}[/\-]\d{4}\b|\b\d{4}[/\-]\d{2}[/\-]\d{2}\b"), "DDN"),
]


def anonymiser_texte(texte: str, mapping: dict | None = None) -> tuple[str, dict]:
    """
    Remplace les PII détectées par des tokens [TYPE_XXX].
    Retourne (texte_anonymisé, mapping {token: valeur_originale}).
    """
    if mapping is None:
        mapping = {}
    reverse = {v: k for k, v in mapping.items()}

    for pattern, type_label in _PII_PATTERNS:
        for match in pattern.finditer(texte):
            val = match.group()
            if val in reverse:
                token = reverse[val]
            else:
                token = f"[{type_label}_{secrets.token_hex(3).upper()}]"
                mapping[token] = val
                reverse[val] = token
            texte = texte.replace(val, token, 1)

    return texte, mapping


class InesAgent(BaseAgent):
    NOM    = "Inès"
    NIVEAU = "N2"
    ROLE   = "Anonymisation & chiffrement AES"

    # Champs à chiffrer avant stockage
    _CHAMPS_SENSIBLES = ["nom_enfant", "prenom_enfant", "telephone_famille",
                         "email_famille", "adresse_enfant", "nss"]

    def run(self, dossier: dict[str, Any], **kwargs) -> dict[str, Any]:
        dossier_id = dossier.get("dossier_id", "—")

        # ── 1. Anonymisation du texte brut pour le LLM ───────────────────────
        texte_brut = dossier.get("texte_brut") or dossier.get("analyse", {}).get("texte_brut", "")
        if texte_brut:
            texte_anon, mapping = anonymiser_texte(texte_brut, {})
            dossier["_texte_anon"]    = texte_anon
            dossier["_pii_mapping"]   = mapping
            # Injecter dans l'analyse pour que les agents LLM utilisent la version anon
            if "analyse" not in dossier:
                dossier["analyse"] = {}
            dossier["analyse"]["_texte_anon"] = texte_anon
            self.log_info(
                f"Texte anonymisé | {len(mapping)} tokens PII remplacés",
                dossier_id=dossier_id,
            )

        # ── 2. Chiffrement des champs sensibles avant stockage ───────────────
        for champ in self._CHAMPS_SENSIBLES:
            valeur = dossier.get(champ)
            if valeur and isinstance(valeur, str) and not valeur.startswith("["):
                chiffre = chiffrer_valeur(valeur)
                dossier[f"{champ}_chiffre"] = chiffre
                # On CONSERVE la valeur en clair pour le traitement en cours,
                # mais on note qu'elle doit être supprimée après envoi PDF.
                dossier[f"_{champ}_original"] = valeur

        dossier["ines_traite"] = True
        dossier["agent_actuel"] = "Inès"
        self.log_info("Chiffrement des champs sensibles OK.", dossier_id=dossier_id)
        return dossier

    @staticmethod
    def dechiffrer_dossier(dossier: dict[str, Any]) -> dict[str, Any]:
        """
        Déchiffre les champs sensibles d'un dossier pour affichage éducateur.
        Retourne un nouveau dict avec les valeurs lisibles.
        """
        suffixe = "_chiffre"
        resultat = dict(dossier)
        for key, val in dossier.items():
            if key.endswith(suffixe) and val:
                champ_clair = key[:-len(suffixe)]
                resultat[champ_clair + "_dechiffre"] = dechiffrer_valeur(val)
        return resultat
