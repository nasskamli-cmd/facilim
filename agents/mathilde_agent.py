"""
agents/mathilde_agent.py — Mathilde (Niveau 0 : Relances automatiques)

Responsabilités :
  - Déclenche les relances famille à J+1 (24h), J+2 (48h), J+3 (72h)
  - Envoie via WhatsApp (puis email en fallback)
  - Notifie l'éducateur dans le dashboard (statut relance mis à jour en DB)
  - Gère les relances forcées par l'éducateur
  - Marque le dossier BLOQUÉ après 3 relances sans réponse

Utilisé par :
  - relance_scheduler.py (tâche periodique automatique)
  - api_agents.py (endpoint POST /dossiers/{id}/force-relance)
"""
import sqlite3
import importlib
from datetime import datetime, timezone, timedelta
from typing import Any

from agents.base_agent import BaseAgent

_wa = importlib.import_module("services.whatsapp_client")
send_text_message = _wa.send_text_message

try:
    from services.email_client import send_verification_code
    _HAS_EMAIL = True
except Exception:
    _HAS_EMAIL = False


# ── Messages de relance ───────────────────────────────────────────────────────
_MESSAGES = {
    1: (
        "Bonjour, c'est l'Assistant Facilim.\n\n"
        "Votre dossier MDPH est en attente de quelques informations. "
        "Pouvez-vous reprendre notre échange pour qu'on finalise ensemble ?"
    ),
    2: (
        "Bonjour, c'est l'Assistant Facilim.\n\n"
        "Votre dossier MDPH n'est pas encore complet. "
        "Il suffit de répondre à ce message pour reprendre là où nous en étions."
    ),
    3: (
        "Bonjour, c'est l'Assistant Facilim — dernier message de notre part.\n\n"
        "Sans réponse de votre part, votre accompagnateur sera informé pour "
        "trouver ensemble la meilleure solution. Répondez si vous avez besoin d'aide."
    ),
}


class MathildeAgent(BaseAgent):
    NOM    = "Mathilde"
    NIVEAU = "N0"
    ROLE   = "Relances automatiques famille"

    def run(self, dossier: dict[str, Any], **kwargs) -> dict[str, Any]:
        """
        Envoie une relance si nécessaire.
        kwargs attendus :
          - force (bool) : si True, envoie immédiatement sans vérifier le délai
          - db_conn : connexion SQLite pour mise à jour des relances
        """
        dossier_id = dossier.get("dossier_id", "—")
        force      = kwargs.get("force", False)
        db_conn    = kwargs.get("db_conn") or self.db

        nb_relances  = dossier.get("nb_relances", 0)
        last_relance = dossier.get("derniere_relance_at")
        statut       = dossier.get("statut", "EN_COURS")

        # Ne pas relancer si le dossier est complet ou archivé
        if statut in ("COMPLET", "ARCHIVE"):
            self.log_info("Pas de relance — dossier terminé.", dossier_id=dossier_id)
            return dossier

        # Ne pas aller au-delà de 3 relances
        if nb_relances >= 3:
            dossier["statut"]          = "BLOQUE"
            dossier["statut_relance"]  = "bloque_sans_reponse"
            self.log_warning(
                "3 relances sans réponse → dossier BLOQUÉ.",
                dossier_id=dossier_id,
            )
            if db_conn:
                self._update_statut_db(db_conn, dossier_id, "BLOQUE", nb_relances, "bloque_sans_reponse")
            return dossier

        # Vérification du délai (sauf si forcée)
        if not force and last_relance:
            try:
                dt_last = datetime.fromisoformat(last_relance)
                if (datetime.now(timezone.utc) - dt_last) < timedelta(hours=24):
                    self.log_info("Délai de relance non atteint.", dossier_id=dossier_id)
                    return dossier
            except ValueError:
                pass

        # ── Envoi de la relance ───────────────────────────────────────────────
        num_relance = nb_relances + 1
        message     = _MESSAGES.get(num_relance, _MESSAGES[3])
        telephone   = dossier.get("telephone_famille", "")
        envoye      = False

        if telephone:
            try:
                send_text_message(telephone, message)
                envoye = True
                self.log_info(
                    f"Relance #{num_relance} envoyée via WhatsApp → {telephone}",
                    dossier_id=dossier_id,
                )
            except Exception as e:
                self.log_error(
                    f"Échec WhatsApp relance #{num_relance} : {e}",
                    dossier_id=dossier_id,
                )

        # Fallback email si WhatsApp échoue
        if not envoye and _HAS_EMAIL:
            email = dossier.get("email_famille", "")
            if email:
                try:
                    from services.email_client import send_relance_email
                    send_relance_email(email, message, num_relance)
                    envoye = True
                    self.log_info(
                        f"Relance #{num_relance} envoyée par email → {email}",
                        dossier_id=dossier_id,
                    )
                except Exception as e:
                    self.log_error(f"Échec email relance : {e}", dossier_id=dossier_id)

        if envoye:
            now = datetime.now(timezone.utc).isoformat()
            dossier["nb_relances"]         = num_relance
            dossier["derniere_relance_at"] = now
            dossier["statut_relance"]      = f"relance_{num_relance}_envoyee"

            if db_conn:
                self._save_relance_db(db_conn, dossier_id, num_relance, message, now)
                self._update_statut_db(
                    db_conn, dossier_id,
                    dossier.get("statut", "INCOMPLET"),
                    num_relance,
                    dossier["statut_relance"],
                )
        else:
            dossier["statut_relance"] = f"relance_{num_relance}_echec"
            self.log_error(f"Relance #{num_relance} — aucun canal disponible.", dossier_id=dossier_id)

        dossier["agent_actuel"] = "Mathilde"
        return dossier

    # ── Helpers DB ────────────────────────────────────────────────────────────

    def _save_relance_db(self, conn, dossier_id: str, numero: int, message: str, sent_at: str):
        """Insère une ligne dans la table relances."""
        try:
            conn.execute("""
                INSERT INTO relances
                  (dossier_id, numero_relance, message_envoye, envoyee_le, statut, created_at)
                VALUES (?, ?, ?, ?, 'envoyee', ?)
            """, (dossier_id, numero, message, sent_at, sent_at))
            conn.commit()
        except Exception as e:
            self.log_error(f"Erreur DB save_relance : {e}", dossier_id=dossier_id)

    def _update_statut_db(self, conn, dossier_id: str, statut: str, nb: int, statut_relance: str):
        """Met à jour le statut, le compte de relances ET la date de dernière relance dans dossiers."""
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                UPDATE dossiers
                SET statut=?, nb_relances=?, statut_relance=?, derniere_relance_at=?, updated_at=?
                WHERE dossier_id=?
            """, (statut, nb, statut_relance, now, now, dossier_id))
            conn.commit()
        except sqlite3.OperationalError:
            # Les colonnes nb_relances/statut_relance/derniere_relance_at peuvent ne pas exister encore
            pass
        except Exception as e:
            self.log_error(f"Erreur DB update statut : {e}", dossier_id=dossier_id)
