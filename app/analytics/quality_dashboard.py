"""
app/analytics/quality_dashboard.py — Module Analytics Facilim V2.2

Mesure · Analyse · Pilotage

RÈGLE ABSOLUE : ce module ne modifie JAMAIS le pipeline CERFA.
Il lit uniquement la table quality_evaluations.
Aucune dépendance aux moteurs métier, agents ou prompts.

Répond aux 3 questions stratégiques :
  1. Facilim fait-il gagner du temps ?
  2. Les documents apportent-ils une vraie valeur ?
  3. Où investir le prochain développement ?
"""

from __future__ import annotations

import json
import logging
import statistics
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("facilim.analytics")

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────────────────────

SEUIL_AB_MIN       = 70.0   # % niveaux A+B pour "prêt"
SEUIL_SCORE_MIN    = 65.0   # score global moyen minimum
SEUIL_TEMPS_MAX    = 20.0   # minutes correction maximum
SEUIL_GAIN_MIN     = 30.0   # minutes gagnées minimum
SEUIL_N_MIN        = 5      # évaluations minimum pour KPIs fiables

NIVEAUX_DOC_LABELS = {
    0: "Aucun document",
    1: "Documentation légère (ordonnance, notification)",
    2: "Documentation moyenne (1 bilan significatif)",
    3: "Documentation riche (PCR, ESRP, multi-bilans)",
}

# Coefficients score de priorité levier (pct_temps, taux_réécrit, impact_score)
COEF_LEVIER = (0.40, 0.30, 0.30)


# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_avg(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None and v >= 0]
    return round(statistics.mean(vals), 2) if vals else None


def _safe_median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None and v >= 0)
    return round(statistics.median(vals), 2) if vals else None


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in (rows or [])]


def _score_global_auto(scores: dict[str, float]) -> float:
    """Calcule le score global depuis les notes de section."""
    valides = [v for v in scores.values() if v is not None and v >= 0]
    return round(statistics.mean(valides) * 10, 1) if valides else 0.0


def _reecriture_global_auto(r: dict) -> float:
    """Calcule le taux de réécriture global comme moyenne des sections renseignées."""
    vals = [r.get(f"taux_reecriture_{s}", 0) or 0
            for s in ("b", "c", "d", "e")]
    positifs = [v for v in vals if v > 0]
    return round(statistics.mean(positifs), 1) if positifs else 0.0


def _niveau_validation(score_global: float) -> str:
    if score_global >= 80:  return "A"
    if score_global >= 65:  return "B"
    if score_global >= 45:  return "C"
    return "D"


# ─────────────────────────────────────────────────────────────────────────────
# ENREGISTREMENT
# ─────────────────────────────────────────────────────────────────────────────

def enregistrer_evaluation(db: Any, data: dict[str, Any]) -> str:
    """
    Enregistre une évaluation terrain dans quality_evaluations.
    Calcule automatiquement score_global, taux_reecriture_global,
    gain_temps et niveau_validation si non fournis.

    Retourne l'ID de l'évaluation créée.
    """
    eval_id = data.get("id") or str(uuid.uuid4())
    now     = _now_iso()

    # Calculs automatiques
    scores = {
        "b": data.get("score_b", -1),
        "c": data.get("score_c", -1),
        "d": data.get("score_d", -1),
        "e": data.get("score_e", -1),
    }
    score_global = data.get("score_global") or _score_global_auto(scores)
    reecriture_global = data.get("taux_reecriture_global") or _reecriture_global_auto(data)
    gain = data.get("gain_temps") or max(
        0.0,
        (data.get("temps_estime_sans_facilim") or 0) -
        (data.get("temps_reel_avec_facilim") or data.get("temps_correction") or 0)
    )
    niveau = data.get("niveau_validation") or _niveau_validation(score_global)

    erreurs = data.get("erreurs_detectees", [])
    if isinstance(erreurs, list):
        erreurs = json.dumps(erreurs, ensure_ascii=False)

    metadata = data.get("metadata", {})
    if isinstance(metadata, dict):
        metadata = json.dumps(metadata, ensure_ascii=False)

    db.execute("""
        INSERT OR REPLACE INTO quality_evaluations (
            id, dossier_id, date_evaluation, evaluateur, version_facilim,
            essms_source, created_at,
            profil_mdph, type_handicap, type_dossier,
            document_present, type_document, niveau_documentation,
            score_b, score_c, score_d, score_e, score_global, score_maturite,
            temps_correction, temps_correction_b, temps_correction_c,
            temps_correction_d, temps_correction_e,
            temps_estime_sans_facilim, temps_reel_avec_facilim, gain_temps,
            taux_reecriture_b, taux_reecriture_c, taux_reecriture_d,
            taux_reecriture_e, taux_reecriture_global,
            questions_supprimees, items_extraits,
            niveau_validation, erreurs_detectees, metadata
        ) VALUES (
            ?,?,?,?,?,?,?,  ?,?,?,?,?,?,  ?,?,?,?,?,?,
            ?,?,?,?,?,      ?,?,?,
            ?,?,?,?,?,      ?,?,  ?,?,?
        )
    """, (
        eval_id,
        data.get("dossier_id"),
        data.get("date_evaluation", now[:10]),
        data.get("evaluateur", "nassim"),
        data.get("version_facilim", ""),
        data.get("essms_source", ""),
        now,
        data.get("profil_mdph", ""),
        data.get("type_handicap", ""),
        data.get("type_dossier", ""),
        int(bool(data.get("document_present", False))),
        data.get("type_document", ""),
        int(data.get("niveau_documentation", 0)),
        scores["b"], scores["c"], scores["d"], scores["e"],
        score_global,
        data.get("score_maturite", 0),
        data.get("temps_correction", 0),
        data.get("temps_correction_b", 0),
        data.get("temps_correction_c", 0),
        data.get("temps_correction_d", 0),
        data.get("temps_correction_e", 0),
        data.get("temps_estime_sans_facilim", 0),
        data.get("temps_reel_avec_facilim", 0),
        gain,
        data.get("taux_reecriture_b", 0),
        data.get("taux_reecriture_c", 0),
        data.get("taux_reecriture_d", 0),
        data.get("taux_reecriture_e", 0),
        reecriture_global,
        data.get("questions_supprimees", 0),
        data.get("items_extraits", 0),
        niveau,
        erreurs,
        metadata,
    ))
    db.commit()
    logger.info("[ANALYTICS] Évaluation enregistrée : %s | profil=%s | score=%.1f | niveau=%s",
                eval_id[:8], data.get("profil_mdph"), score_global, niveau)
    return eval_id


# ─────────────────────────────────────────────────────────────────────────────
# KPI GLOBAUX
# ─────────────────────────────────────────────────────────────────────────────

def calculer_kpi_globaux(db: Any, periode_debut: str = "", periode_fin: str = "") -> dict:
    """KPI agrégés sur l'ensemble des évaluations."""
    where, params = _filtre_periode(periode_debut, periode_fin)

    row = db.execute(f"""
        SELECT
            COUNT(*)                                                   AS nb,
            ROUND(AVG(score_global), 1)                                AS score_global_moy,
            ROUND(AVG(CASE WHEN score_b >= 0 THEN score_b END), 1)     AS score_b_moy,
            ROUND(AVG(CASE WHEN score_c >= 0 THEN score_c END), 1)     AS score_c_moy,
            ROUND(AVG(CASE WHEN score_d >= 0 THEN score_d END), 1)     AS score_d_moy,
            ROUND(AVG(CASE WHEN score_e >= 0 THEN score_e END), 1)     AS score_e_moy,
            ROUND(AVG(score_maturite), 1)                              AS score_maturite_moy,
            ROUND(AVG(temps_correction), 1)                            AS temps_correction_moy,
            ROUND(AVG(gain_temps), 1)                                  AS gain_temps_moy,
            ROUND(AVG(taux_reecriture_global), 1)                      AS reecriture_moy,
            ROUND(100.0*SUM(CASE WHEN niveau_validation='A' THEN 1 ELSE 0 END)/COUNT(*),1) AS pct_A,
            ROUND(100.0*SUM(CASE WHEN niveau_validation='B' THEN 1 ELSE 0 END)/COUNT(*),1) AS pct_B,
            ROUND(100.0*SUM(CASE WHEN niveau_validation='C' THEN 1 ELSE 0 END)/COUNT(*),1) AS pct_C,
            ROUND(100.0*SUM(CASE WHEN niveau_validation='D' THEN 1 ELSE 0 END)/COUNT(*),1) AS pct_D,
            ROUND(AVG(questions_supprimees), 1)                        AS questions_sup_moy,
            ROUND(SUM(gain_temps) / 60.0, 1)                          AS gain_total_h
        FROM quality_evaluations {where}
    """, params).fetchone()

    if not row or not row["nb"]:
        return {"nb": 0, "fiable": False}

    r = dict(row)
    r["fiable"]  = r["nb"] >= SEUIL_N_MIN
    r["taux_AB"] = round((r["pct_A"] or 0) + (r["pct_B"] or 0), 1)
    r["ecart_facilim_nassim"] = round(
        (r["score_global_moy"] or 0) - (r["score_maturite_moy"] or 0) / 10, 1
    )

    # Médiane gain (Python)
    gains = [g["gain_temps"] for g in _rows_to_list(db.execute(
        f"SELECT gain_temps FROM quality_evaluations {where} AND gain_temps > 0", params
    ).fetchall())]
    r["gain_temps_median"] = _safe_median(gains)

    return r


# ─────────────────────────────────────────────────────────────────────────────
# KPI PAR DIMENSION
# ─────────────────────────────────────────────────────────────────────────────

def _kpi_group_by(db: Any, group_col: str, where: str, params: tuple) -> list[dict]:
    rows = db.execute(f"""
        SELECT
            {group_col}                                                AS groupe,
            COUNT(*)                                                   AS nb,
            ROUND(AVG(score_global), 1)                                AS score_moyen,
            ROUND(AVG(temps_correction), 1)                            AS temps_correction_moy,
            ROUND(AVG(gain_temps), 1)                                  AS gain_moyen,
            ROUND(AVG(taux_reecriture_global), 1)                      AS reecriture_moy,
            ROUND(100.0*SUM(CASE WHEN niveau_validation IN('A','B') THEN 1 ELSE 0 END)/COUNT(*),1) AS taux_AB,
            ROUND(AVG(questions_supprimees), 1)                        AS questions_sup_moy
        FROM quality_evaluations {where}
        GROUP BY {group_col}
        ORDER BY nb DESC
    """, params).fetchall()
    return _rows_to_list(rows)


def calculer_kpi_par_profil(db: Any, **kwargs) -> list[dict]:
    w, p = _filtre_periode(**kwargs)
    return _kpi_group_by(db, "profil_mdph", w, p)


def calculer_kpi_par_version(db: Any, **kwargs) -> list[dict]:
    w, p = _filtre_periode(**kwargs)
    rows = _kpi_group_by(db, "version_facilim", w, p)
    # Calcul delta vs version précédente
    for i, r in enumerate(rows):
        if i > 0:
            prev = rows[i - 1]
            r["delta_score"]  = round((r["score_moyen"] or 0) - (prev["score_moyen"] or 0), 1)
            r["delta_taux_AB"]= round((r["taux_AB"]    or 0) - (prev["taux_AB"]    or 0), 1)
            r["delta_gain"]   = round((r["gain_moyen"] or 0) - (prev["gain_moyen"] or 0), 1)
    return rows


def calculer_kpi_par_type_dossier(db: Any, **kwargs) -> list[dict]:
    w, p = _filtre_periode(**kwargs)
    return _kpi_group_by(db, "type_dossier", w, p)


def calculer_kpi_par_essms(db: Any, **kwargs) -> list[dict]:
    w, p = _filtre_periode(**kwargs)
    rows = _kpi_group_by(db, "essms_source", w, p)
    # Ajouter top erreurs par ESSMS
    for r in rows:
        essms = r["groupe"]
        erreurs_rows = db.execute(
            "SELECT erreurs_detectees FROM quality_evaluations WHERE essms_source=?", (essms,)
        ).fetchall()
        r["top_erreurs"] = _compter_erreurs(erreurs_rows)[:3]
    return rows


def calculer_kpi_par_niveau_documentation(db: Any, **kwargs) -> list[dict]:
    w, p = _filtre_periode(**kwargs)
    rows = _kpi_group_by(db, "niveau_documentation", w, p)
    # Ajouter labels
    for r in rows:
        r["label"] = NIVEAUX_DOC_LABELS.get(int(r["groupe"] or 0), "")
    # Delta niv 3 vs niv 0
    scores = {int(r["groupe"] or 0): r["score_moyen"] or 0 for r in rows}
    gains  = {int(r["groupe"] or 0): r["gain_moyen"] or 0  for r in rows}
    delta_score = round(scores.get(3, 0) - scores.get(0, 0), 1)
    delta_gain  = round(gains.get(3, 0)  - gains.get(0, 0),  1)
    return {"par_niveau": rows, "delta_score_niv3_niv0": delta_score, "delta_gain_niv3_niv0": delta_gain}


# ─────────────────────────────────────────────────────────────────────────────
# KPI ROI
# ─────────────────────────────────────────────────────────────────────────────

def calculer_roi(db: Any, **kwargs) -> dict:
    """Gain de temps détaillé : global, par profil, par version, avec/sans doc."""
    w, p = _filtre_periode(**kwargs)

    row = db.execute(f"""
        SELECT
            COUNT(*)                                   AS nb,
            ROUND(AVG(gain_temps), 1)                  AS gain_moy,
            ROUND(MIN(gain_temps), 1)                  AS gain_min,
            ROUND(MAX(gain_temps), 1)                  AS gain_max,
            ROUND(AVG(temps_correction), 1)            AS temps_corr_moy,
            ROUND(AVG(temps_estime_sans_facilim), 1)   AS temps_estime_moy
        FROM quality_evaluations {w} AND gain_temps > 0
    """, p).fetchone()

    gains = [r["gain_temps"] for r in _rows_to_list(db.execute(
        f"SELECT gain_temps FROM quality_evaluations {w} AND gain_temps > 0", p
    ).fetchall())]

    # Par profil
    par_profil = {}
    for r in _rows_to_list(db.execute(f"""
        SELECT profil_mdph,
               ROUND(AVG(gain_temps),1) AS gain, COUNT(*) AS nb
        FROM quality_evaluations {w} AND gain_temps > 0
        GROUP BY profil_mdph
    """, p).fetchall()):
        par_profil[r["profil_mdph"]] = {"gain_moy": r["gain"], "nb": r["nb"]}

    # Avec vs sans document
    doc_row = db.execute(f"""
        SELECT
            ROUND(AVG(CASE WHEN document_present=1 THEN gain_temps END), 1) AS gain_doc,
            ROUND(AVG(CASE WHEN document_present=0 THEN gain_temps END), 1) AS gain_no_doc,
            ROUND(AVG(CASE WHEN document_present=1 THEN score_global END), 1) AS score_doc,
            ROUND(AVG(CASE WHEN document_present=0 THEN score_global END), 1) AS score_no_doc
        FROM quality_evaluations {w}
    """, p).fetchone()

    return {
        "nb":               dict(row)["nb"] if row else 0,
        "gain_moyen":       dict(row)["gain_moy"] if row else None,
        "gain_median":      _safe_median(gains),
        "gain_min":         dict(row)["gain_min"] if row else None,
        "gain_max":         dict(row)["gain_max"] if row else None,
        "temps_corr_moyen": dict(row)["temps_corr_moy"] if row else None,
        "temps_estime_moy": dict(row)["temps_estime_moy"] if row else None,
        "par_profil":       par_profil,
        "impact_document":  dict(doc_row) if doc_row else {},
    }


def calculer_kpi_economique(db: Any, tarif_horaire: float = 0.0, **kwargs) -> dict:
    """Valeur économique totale générée par Facilim."""
    w, p = _filtre_periode(**kwargs)

    row = db.execute(f"""
        SELECT
            COUNT(*)              AS nb,
            ROUND(SUM(gain_temps), 1) AS total_min,
            ROUND(AVG(gain_temps), 1) AS gain_moy
        FROM quality_evaluations {w}
    """, p).fetchone()
    if not row: return {}

    r = dict(row)
    total_h   = round(r["total_min"] / 60, 1)
    equiv_j   = round(total_h / 8, 1)
    valeur    = round(total_h * tarif_horaire, 0) if tarif_horaire else None
    proj_100  = round((r["gain_moy"] or 0) * 100 / 60, 1)

    return {
        "nb_dossiers":              r["nb"],
        "gain_moyen_min":           r["gain_moy"],
        "total_economise_min":      r["total_min"],
        "total_economise_h":        total_h,
        "equivalent_journees":      equiv_j,
        "valeur_estimee":           valeur,
        "projection_100_dossiers_h": proj_100,
    }


# ─────────────────────────────────────────────────────────────────────────────
# KPI SECTIONS
# ─────────────────────────────────────────────────────────────────────────────

def calculer_temps_par_section(db: Any, **kwargs) -> dict:
    """Temps de correction par section, global et par profil."""
    w, p = _filtre_periode(**kwargs)

    row = db.execute(f"""
        SELECT
            ROUND(AVG(temps_correction), 1)   AS total,
            ROUND(AVG(NULLIF(temps_correction_b,0)), 1) AS b,
            ROUND(AVG(NULLIF(temps_correction_c,0)), 1) AS c,
            ROUND(AVG(NULLIF(temps_correction_d,0)), 1) AS d,
            ROUND(AVG(NULLIF(temps_correction_e,0)), 1) AS e
        FROM quality_evaluations {w}
    """, p).fetchone()

    r = dict(row) if row else {}
    total = r.get("total") or 1

    global_r = {
        "total": r.get("total"),
        "B": r.get("b"), "C": r.get("c"), "D": r.get("d"), "E": r.get("e"),
        "pct_B": round((r.get("b") or 0) / total * 100, 1),
        "pct_C": round((r.get("c") or 0) / total * 100, 1),
        "pct_D": round((r.get("d") or 0) / total * 100, 1),
        "pct_E": round((r.get("e") or 0) / total * 100, 1),
    }

    # Par profil
    par_profil = {}
    for r2 in _rows_to_list(db.execute(f"""
        SELECT profil_mdph,
               ROUND(AVG(NULLIF(temps_correction_b,0)),1) AS b,
               ROUND(AVG(NULLIF(temps_correction_c,0)),1) AS c,
               ROUND(AVG(NULLIF(temps_correction_d,0)),1) AS d,
               ROUND(AVG(NULLIF(temps_correction_e,0)),1) AS e
        FROM quality_evaluations {w}
        GROUP BY profil_mdph
    """, p).fetchall()):
        par_profil[r2["profil_mdph"]] = {
            "B": r2["b"], "C": r2["c"], "D": r2["d"], "E": r2["e"]
        }

    return {"global": global_r, "par_profil": par_profil}


def calculer_taux_reecriture_par_section(db: Any, **kwargs) -> dict:
    """Taux de réécriture moyen par section."""
    w, p = _filtre_periode(**kwargs)

    row = db.execute(f"""
        SELECT
            ROUND(AVG(taux_reecriture_global), 1) AS global,
            ROUND(AVG(NULLIF(taux_reecriture_b,0)), 1) AS b,
            ROUND(AVG(NULLIF(taux_reecriture_c,0)), 1) AS c,
            ROUND(AVG(NULLIF(taux_reecriture_d,0)), 1) AS d,
            ROUND(AVG(NULLIF(taux_reecriture_e,0)), 1) AS e
        FROM quality_evaluations {w}
    """, p).fetchone()

    return dict(row) if row else {}


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSE PRODUIT
# ─────────────────────────────────────────────────────────────────────────────

def _compter_erreurs(rows) -> list[dict]:
    """Compte la fréquence des erreurs depuis les JSON erreurs_detectees."""
    compteur: dict[str, int] = {}
    for r in rows:
        try:
            erreurs = json.loads(r["erreurs_detectees"] or "[]")
            for e in erreurs:
                compteur[e] = compteur.get(e, 0) + 1
        except Exception:
            pass
    return sorted(
        [{"erreur": k, "occurrences": v} for k, v in compteur.items()],
        key=lambda x: -x["occurrences"],
    )


def identifier_top_erreurs(db: Any, top_n: int = 20, **kwargs) -> list[dict]:
    """Top N des erreurs les plus fréquentes avec impact estimé."""
    w, p = _filtre_periode(**kwargs)
    rows = db.execute(
        f"SELECT erreurs_detectees FROM quality_evaluations {w}", p
    ).fetchall()
    erreurs = _compter_erreurs(rows)[:top_n]
    # Ajouter nb total pour calcul %
    nb_total = db.execute(
        f"SELECT COUNT(*) FROM quality_evaluations {w}", p
    ).fetchone()[0] or 1
    for e in erreurs:
        e["pct_dossiers"] = round(e["occurrences"] / nb_total * 100, 1)
    return erreurs


def identifier_leviers_amelioration(db: Any, **kwargs) -> list[dict]:
    """
    Identifie les sections prioritaires pour le prochain développement.
    Score = pct_temps × 0.4 + taux_réécrit × 0.3 + |impact_score| × 0.3
    """
    w, p = _filtre_periode(**kwargs)
    temps  = calculer_temps_par_section(db, **kwargs)["global"]
    reecriture = calculer_taux_reecriture_par_section(db, **kwargs)
    total_temps = temps.get("total") or 1

    # Impact score par section : delta score_global quand la section est faible (< 6)
    def impact_section(s: str) -> float:
        col = f"score_{s.lower()}"
        row_h = db.execute(f"""
            SELECT
                ROUND(AVG(CASE WHEN {col} >= 6 THEN score_global END), 1) AS haut,
                ROUND(AVG(CASE WHEN {col} >= 0 AND {col} < 6 THEN score_global END), 1) AS bas
            FROM quality_evaluations {w} AND {col} >= 0
        """, p).fetchone()
        if row_h and row_h["haut"] and row_h["bas"]:
            return round(row_h["haut"] - row_h["bas"], 1)
        return 0.0

    leviers = []
    for s in ["B", "C", "D", "E"]:
        t     = temps.get(s) or 0
        r     = reecriture.get(s.lower()) or 0
        impact= impact_section(s)
        pct_t = round(t / total_temps * 100, 1) if total_temps else 0

        score_prio = round(
            pct_t   * COEF_LEVIER[0] +
            r       * COEF_LEVIER[1] +
            abs(impact) * COEF_LEVIER[2],
            1,
        )
        leviers.append({
            "section":           s,
            "temps_moyen_min":   t,
            "pct_temps_total":   pct_t,
            "taux_reecriture":   r,
            "impact_score_pts":  impact,
            "score_priorite":    score_prio,
        })

    leviers.sort(key=lambda x: -x["score_priorite"])
    for i, lv in enumerate(leviers):
        lv["rang"] = i + 1
    return leviers


# ─────────────────────────────────────────────────────────────────────────────
# DÉCISION PRODUIT
# ─────────────────────────────────────────────────────────────────────────────

def decision_produit(db: Any, **kwargs) -> dict:
    """
    Calcule la décision de déploiement selon les 4 seuils.
    NON PRÊT / PILOTE LIMITÉ / PILOTE ÉTENDU / DÉPLOIEMENT
    """
    kpi = calculer_kpi_globaux(db, **kwargs)
    roi = calculer_roi(db, **kwargs)

    taux_AB = kpi.get("taux_AB", 0)
    score   = kpi.get("score_global_moy", 0)
    temps   = kpi.get("temps_correction_moy", 99)
    gain    = roi.get("gain_moyen", 0) or 0
    nb      = kpi.get("nb", 0)

    seuils = {
        "taux_AB":    {"valeur": taux_AB, "seuil": SEUIL_AB_MIN,    "atteint": taux_AB >= SEUIL_AB_MIN},
        "score":      {"valeur": score,   "seuil": SEUIL_SCORE_MIN, "atteint": score   >= SEUIL_SCORE_MIN},
        "temps":      {"valeur": temps,   "seuil": SEUIL_TEMPS_MAX, "atteint": temps   <= SEUIL_TEMPS_MAX},
        "gain":       {"valeur": gain,    "seuil": SEUIL_GAIN_MIN,  "atteint": gain    >= SEUIL_GAIN_MIN},
    }
    nb_atteints = sum(1 for s in seuils.values() if s["atteint"])

    if nb_atteints == 4 and nb >= 30:
        decision = "DÉPLOIEMENT"
        justif   = f"Les 4 critères sont atteints sur {nb} dossiers (≥ 30). Passage en production générale recommandé."
    elif nb_atteints == 4:
        decision = "PILOTE ÉTENDU"
        justif   = f"Les 4 critères sont atteints sur {nb} dossiers. Déploiement recommandé auprès de 3 à 5 ESSMS pilotes."
    elif nb_atteints >= 2:
        manquants = [k for k, s in seuils.items() if not s["atteint"]]
        decision  = "PILOTE LIMITÉ"
        justif    = f"2–3 critères atteints. Usage possible avec accompagnement renforcé. Axes à corriger : {', '.join(manquants)}."
    else:
        manquants = [k for k, s in seuils.items() if not s["atteint"]]
        decision  = "NON PRÊT"
        justif    = f"{4-nb_atteints} critères non atteints. Optimisation requise : {', '.join(manquants)}."

    return {
        "decision":     decision,
        "justification": justif,
        "nb_dossiers":  nb,
        "seuils":       seuils,
        "nb_atteints":  nb_atteints,
        "fiable":       nb >= SEUIL_N_MIN,
    }


# ─────────────────────────────────────────────────────────────────────────────
# RESTITUTION
# ─────────────────────────────────────────────────────────────────────────────

def generer_tableau_bord(
    db: Any,
    periode_debut: str = "",
    periode_fin:   str = "",
) -> dict:
    """Tableau de bord JSON complet — tous les KPI assemblés."""
    kw = {"periode_debut": periode_debut, "periode_fin": periode_fin}

    kpi     = calculer_kpi_globaux(db, **kw)
    roi     = calculer_roi(db, **kw)
    eco     = calculer_kpi_economique(db, **kw)
    sections_temps  = calculer_temps_par_section(db, **kw)
    sections_reecriture = calculer_taux_reecriture_par_section(db, **kw)
    leviers = identifier_leviers_amelioration(db, **kw)
    erreurs = identifier_top_erreurs(db, top_n=10, **kw)
    decision = decision_produit(db, **kw)

    # Volume et répartitions
    w, p = _filtre_periode(**kw)
    volume = {}
    for col in ("profil_mdph", "essms_source", "type_dossier",
                "niveau_documentation", "niveau_validation"):
        rows = db.execute(
            f"SELECT {col} AS k, COUNT(*) AS n FROM quality_evaluations {w} GROUP BY {col}", p
        ).fetchall()
        volume[col] = {r["k"]: r["n"] for r in rows}

    return {
        "meta": {
            "genere_le":    _now_iso(),
            "periode_debut": periode_debut or "toutes",
            "periode_fin":   periode_fin   or "toutes",
            "nb_dossiers":  kpi.get("nb", 0),
            "fiable":       kpi.get("fiable", False),
        },
        "volume":    volume,
        "qualite": {
            "score_global_moy":    kpi.get("score_global_moy"),
            "score_maturite_moy":  kpi.get("score_maturite_moy"),
            "ecart_facilim_nassim":kpi.get("ecart_facilim_nassim"),
            "scores_sections":     {"B": kpi.get("score_b_moy"), "C": kpi.get("score_c_moy"),
                                    "D": kpi.get("score_d_moy"), "E": kpi.get("score_e_moy")},
            "niveaux":             {"A": kpi.get("pct_A"), "B": kpi.get("pct_B"),
                                    "C": kpi.get("pct_C"), "D": kpi.get("pct_D"),
                                    "AB": kpi.get("taux_AB")},
            "taux_reecriture":     sections_reecriture,
        },
        "roi":       roi,
        "economique": eco,
        "sections":  {"temps": sections_temps, "reecriture": sections_reecriture},
        "leviers":   leviers,
        "top_erreurs": erreurs,
        "par_profil":  calculer_kpi_par_profil(db, **kw),
        "par_version": calculer_kpi_par_version(db, **kw),
        "par_type_dossier": calculer_kpi_par_type_dossier(db, **kw),
        "par_essms":   calculer_kpi_par_essms(db, **kw),
        "documentation": calculer_kpi_par_niveau_documentation(db, **kw),
        "decision":    decision,
    }


def generer_rapport_executif(db: Any, **kwargs) -> str:
    """Rapport texte court — réponse aux 3 questions stratégiques."""
    tb = generer_tableau_bord(db, **kwargs)
    kpi     = tb["qualite"]
    roi     = tb["roi"]
    eco     = tb["economique"]
    dec     = tb["decision"]
    leviers = tb["leviers"]
    erreurs = tb["top_erreurs"]
    meta    = tb["meta"]
    sections_temps = tb["sections"]["temps"]["global"]

    nb    = meta["nb_dossiers"]
    score = kpi.get("score_global_moy") or 0
    gain  = roi.get("gain_moyen") or 0
    temps = roi.get("temps_corr_moyen") or 0
    taux_ab = kpi["niveaux"].get("AB") or 0

    # Section la plus chronophage
    levier1 = leviers[0] if leviers else {}
    levier2 = leviers[1] if len(leviers) > 1 else {}

    # Top 3 erreurs
    top3 = [e["erreur"] for e in erreurs[:3]]

    sep = "═" * 54

    rapport = f"""
{sep}
FACILIM — RAPPORT EXÉCUTIF QUALITÉ
Période : {meta['periode_debut']} – {meta['periode_fin']}
Dossiers analysés : {nb}{"  ⚠ données insuffisantes" if not meta.get("fiable") else "  ✓ seuil atteint"}
{sep}

1. FACILIM FAIT-IL GAGNER DU TEMPS ?
{"─"*40}
{"   OUI." if gain >= SEUIL_GAIN_MIN else "   PARTIELLEMENT."}
   Sans Facilim (estimation) : {roi.get('temps_estime_moy') or '—'} min / dossier
   Avec Facilim              : {round(temps, 1)} min de correction
   Gain moyen                : {round(gain, 1)} min / dossier{"  ✓" if gain >= SEUIL_GAIN_MIN else "  ✗"}
   Gain médian               : {roi.get('gain_median') or '—'} min
   Temps total économisé     : {eco.get('total_economise_h') or '—'} h ({nb} dossiers)
   Projection 100 dossiers   : {eco.get('projection_100_dossiers_h') or '—'} h économisées

2. LES DOCUMENTS APPORTENT-ILS UNE VRAIE VALEUR ?
{"─"*40}
   Impact documentaire (niveau 3 vs niveau 0) :
"""
    doc = tb.get("documentation", {})
    delta_score = doc.get("delta_score_niv3_niv0")
    delta_gain  = doc.get("delta_gain_niv3_niv0")
    if delta_score is not None:
        rapport += f"   Score  : +{delta_score} pts avec documentation riche\n"
    if delta_gain is not None:
        rapport += f"   Gain   : +{delta_gain} min avec documentation riche\n"

    rapport += f"""
3. OÙ INVESTIR LE PROCHAIN DÉVELOPPEMENT ?
{"─"*40}
   Section la plus chronophage   : {levier1.get('section','—')} ({levier1.get('pct_temps_total','—')} % du temps)
   Section la plus réécrite      : D ({kpi.get('taux_reecriture', {}).get('d','—')} % réécriture)
"""
    if levier1:
        rapport += f"   Priorité n°1 : Section {levier1.get('section')} (score priorité {levier1.get('score_priorite')})\n"
    if levier2:
        rapport += f"   Priorité n°2 : Section {levier2.get('section')} (score priorité {levier2.get('score_priorite')})\n"

    rapport += f"""
QUALITÉ GLOBALE
{"─"*40}
   Score moyen              : {score}/100{"  ✓" if score >= SEUIL_SCORE_MIN else "  ✗"}
   Taux A+B                 : {taux_ab} %{"  ✓" if taux_ab >= SEUIL_AB_MIN else "  ✗"}
   Section B                : {kpi['scores_sections'].get('B') or '—'}/10
   Section D                : {kpi['scores_sections'].get('D') or '—'}/10
   Section E                : {kpi['scores_sections'].get('E') or '—'}/10
   Taux réécriture global   : {kpi.get('taux_reecriture', {}).get('global','—')} %

TOP {min(3,len(top3))} ERREURS OBSERVÉES
{"─"*40}"""
    for i, e in enumerate(top3, 1):
        rapport += f"\n   {i}. {e}"

    rapport += f"""

DÉCISION PRODUIT
{"─"*40}"""
    for k, s in dec["seuils"].items():
        mark = "✓" if s["atteint"] else "✗"
        rapport += f"\n   {mark} {k:<12} : {s['valeur']} (seuil {s['seuil']})"

    rapport += f"""

   → DÉCISION : {dec['decision']}
   → {dec['justification']}
{sep}"""
    return rapport.strip()


# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES INTERNES
# ─────────────────────────────────────────────────────────────────────────────

def _filtre_periode(
    periode_debut: str = "",
    periode_fin:   str = "",
    **_kwargs,
) -> tuple[str, tuple]:
    """Construit la clause WHERE + params pour filtrer par période."""
    clauses = ["1=1"]
    params: list[str] = []
    if periode_debut:
        clauses.append("date_evaluation >= ?")
        params.append(periode_debut)
    if periode_fin:
        clauses.append("date_evaluation <= ?")
        params.append(periode_fin)
    return "WHERE " + " AND ".join(clauses), tuple(params)
