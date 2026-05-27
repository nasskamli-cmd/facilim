"""
agents/lea_agent.py — Léa (Niveau -1 : Accueil & Validation entrée)

Responsabilités :
  - Valide la date de naissance (format, plausibilité)
  - Vérifie la présence de l'email famille et du WhatsApp
  - Détecte le type de dossier (enfant / jeune 16-25 / adulte)
  - Rejette les dossiers incomplets avec message explicite

Si la validation échoue, Léa lève une ValueError avec un message clair
destiné à être renvoyé à l'éducateur.
"""
import re
from datetime import date, datetime
from typing import Any

from agents.base_agent import BaseAgent


def _parse_ddn(ddn: str) -> date | None:
    """Parse JJ/MM/AAAA ou AAAA-MM-JJ → date. Retourne None si invalide."""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(ddn.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _detecter_type_dossier(ddn: date) -> str:
    today = date.today()
    age = (today - ddn).days // 365
    if age < 16:
        return "enfant"
    elif age < 26:
        return "jeune_16_25"
    else:
        return "adulte"


class LeaAgent(BaseAgent):
    NOM    = "Léa"
    NIVEAU = "N-1"
    ROLE   = "Validation entrée dossier"

    # Format E.164 simplifié : +33XXXXXXXXX ou 06/07XXXXXXXX
    _RE_PHONE = re.compile(r"^(\+\d{7,15}|0[67]\d{8})$")
    _RE_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

    def run(self, dossier: dict[str, Any], **kwargs) -> dict[str, Any]:
        dossier_id = dossier.get("dossier_id", "—")
        erreurs = []

        # ── 1. Date de naissance ─────────────────────────────────────────────
        ddn_brut = (dossier.get("ddn_enfant") or "").strip()
        if not ddn_brut:
            erreurs.append("La date de naissance est obligatoire.")
        else:
            ddn = _parse_ddn(ddn_brut)
            if ddn is None:
                erreurs.append(
                    f"Date de naissance invalide : « {ddn_brut} ». "
                    "Format attendu : JJ/MM/AAAA (ex: 15/03/2010)."
                )
            elif ddn > date.today():
                erreurs.append("La date de naissance ne peut pas être dans le futur.")
            elif (date.today() - ddn).days > 365 * 130:
                erreurs.append("La date de naissance semble incorrecte (âge > 130 ans).")
            else:
                dossier["ddn_parsee"] = ddn.isoformat()
                dossier["type_dossier"] = _detecter_type_dossier(ddn)
                age = (date.today() - ddn).days // 365
                dossier["age_beneficiaire"] = age
                dossier["is_enfant"] = age < 16

        # ── 2. WhatsApp famille ──────────────────────────────────────────────
        tel = (dossier.get("telephone_famille") or "").strip().replace(" ", "").replace("-", "")
        if not tel:
            erreurs.append("Le numéro WhatsApp de la famille est obligatoire.")
        elif not self._RE_PHONE.match(tel):
            erreurs.append(
                f"Numéro WhatsApp invalide : « {tel} ». "
                "Format attendu : +33XXXXXXXXX ou 06/07XXXXXXXX."
            )
        else:
            # Normalisation en E.164
            if tel.startswith("0"):
                tel = "+33" + tel[1:]
            dossier["telephone_famille"] = tel

        # ── 3. Email famille (optionnel mais fortement recommandé) ───────────
        email = (dossier.get("email_famille") or "").strip().lower()
        if email and not self._RE_EMAIL.match(email):
            erreurs.append(f"Email famille invalide : « {email} ».")

        # ── 4. Département ───────────────────────────────────────────────────
        dept = (dossier.get("departement_code") or "").strip()
        if not dept:
            erreurs.append("Le code département MDPH est obligatoire.")

        # ── Bilan ────────────────────────────────────────────────────────────
        if erreurs:
            msg = "Dossier rejeté par Léa (validation entrée) :\n" + "\n".join(
                f"  • {e}" for e in erreurs
            )
            self.log_error(msg, dossier_id=dossier_id)
            raise ValueError(msg)

        dossier["lea_validee"] = True
        self.log_info(
            f"Validation OK | type={dossier.get('type_dossier')} | "
            f"age={dossier.get('age_beneficiaire')}ans",
            dossier_id=dossier_id,
        )
        return dossier
