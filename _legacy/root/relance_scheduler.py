"""
relance_scheduler.py — Scheduler de relances automatiques (Mathilde)

Lance une tâche périodique toutes les heures pour vérifier les dossiers
en attente de réponse et déclencher les relances via MathildeAgent.

Intégration : appelé depuis api_agents.py via lifespan FastAPI.
"""
import asyncio
import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger("facilim.scheduler")


async def run_relance_cycle():
    """
    Cycle principal : cherche les dossiers à relancer et déclenche Mathilde.
    Tourne en background (asyncio.create_task).

    IMPORTANT — délai initial de 5 minutes :
    Sans ce délai, chaque redémarrage Railway (déploiement, crash-loop)
    déclenche immédiatement une salve de relances sur tous les dossiers actifs.
    5 minutes laissent le temps à l'app de se stabiliser et garantissent
    qu'un crash-loop rapide ne spamme pas les familles.
    """
    from database_extensions import get_dossiers_a_relancer
    from agents.mathilde_agent import MathildeAgent

    logger.info("[SCHEDULER] Démarrage dans 5 minutes (délai anti-spam post-démarrage).")
    await asyncio.sleep(300)   # ← délai initial : 5 min
    logger.info("[SCHEDULER] Cycle de relances actif.")

    while True:
        try:
            dossiers = get_dossiers_a_relancer()
            if dossiers:
                logger.info(f"[SCHEDULER] {len(dossiers)} dossier(s) à relancer.")

            for d in dossiers:
                try:
                    # Connexion DB par dossier
                    conn = sqlite3.connect("mdph_dossiers.db", check_same_thread=False)
                    conn.row_factory = sqlite3.Row

                    agent = MathildeAgent(db_conn=conn)
                    agent.run(d, force=False, db_conn=conn)

                    conn.close()
                    logger.info(f"[SCHEDULER] Relance traitée | dossier={d['dossier_id'][:8]}")
                except Exception as e:
                    logger.error(f"[SCHEDULER] Erreur relance dossier {d.get('dossier_id', '?')[:8]} : {e}")

                # Pause entre chaque dossier : évite de spammer plusieurs familles d'un coup
                await asyncio.sleep(10)

        except Exception as e:
            logger.error(f"[SCHEDULER] Erreur cycle relances : {e}")

        # Attendre 1 heure avant le prochain cycle
        await asyncio.sleep(3600)


def start_scheduler():
    """Démarre le scheduler en background (à appeler au startup FastAPI)."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(run_relance_cycle())
    else:
        logger.warning("[SCHEDULER] Impossible de démarrer — aucune boucle asyncio active.")
    logger.info("[SCHEDULER] Scheduler de relances démarré (cycle 1h).")
