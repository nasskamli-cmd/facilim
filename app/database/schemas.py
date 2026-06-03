"""
app/database/schemas.py — Modèle de données CERFA 15692*01 V3 Multi-Agents.

Architecture calquée sur les 20 pages officielles du CERFA MDPH :
  ConfigurationDossier       → Canal (texte/vocal) + langue cible de la session
  SectionA_Identite          → Pages 1-3  (identité, NIR, protection juridique)
  SectionB_VieScolaire       → Pages 9-12 (enfants et jeunes — éliminée pour les adultes)
  SectionC_VieQuotidienne    → Pages 5-7  (retentissements fonctionnels, logement)
  SectionD_SituationPro      → Pages 13-16 (statut professionnel actuel)
  SectionE_ProjetPro         → Pages 17-18 (droits demandés, orientations)
  SectionF_VieAidant         → Pages 19-20 (aidant familial)
  Section_Urgence            → Page 1 bas  (alerte expiration droits < 2 mois)

Profils légaux (simplifiés) :
  "enfant"   (0-15 ans)   → A + B + C         actifs
  "mixte"    (16-25 ans)  → A + B + C + D + E actifs (règle équipe mixte)
  "adulte"   (> 25 ans)   → A + C + D + E     actifs
  "inconnu"               → en attente de la date de naissance
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Profil légal MDPH
# ─────────────────────────────────────────────────────────────────────────────

ProfilMDPH = Literal["enfant", "mixte", "adulte", "inconnu"]


# ─────────────────────────────────────────────────────────────────────────────
# Configuration de session — canal et langue cible
# ─────────────────────────────────────────────────────────────────────────────

ConfigurationCanal = Literal["texte", "vocal"]

# Liste chirurgicale des langues majeures pour les accueils sociaux en France
ConfigurationLangue = Literal[
    "français",
    "anglais",
    "arabe",
    "espagnol",
    "portugais",
    "italien",
    "allemand",
    "turc",
    "roumain",
    "russe",
    "mandarin",
    "autre",
]

# Correspondance code ISO 639-1 → ConfigurationLangue (utilisée par l'Agent Traducteur)
_ISO_VERS_LANGUE: dict[str, ConfigurationLangue] = {
    "fr": "français",
    "en": "anglais",
    "ar": "arabe",
    "es": "espagnol",
    "pt": "portugais",
    "it": "italien",
    "de": "allemand",
    "tr": "turc",
    "ro": "roumain",
    "ru": "russe",
    "zh": "mandarin",
    "zh-cn": "mandarin",
    "zh-tw": "mandarin",
}

# Correspondance inverse ConfigurationLangue → code ISO 639-1
_LANGUE_VERS_ISO: dict[str, str] = {v: k for k, v in _ISO_VERS_LANGUE.items()}
_LANGUE_VERS_ISO["autre"] = "xx"   # code générique pour les langues non listées


def langue_vers_iso(langue: ConfigurationLangue) -> str:
    """Convertit un ConfigurationLangue en code ISO 639-1 pour l'Agent Traducteur."""
    return _LANGUE_VERS_ISO.get(langue, "xx")


def iso_vers_langue(code_iso: str) -> ConfigurationLangue:
    """Convertit un code ISO 639-1 en ConfigurationLangue. Retourne 'autre' si inconnu."""
    return _ISO_VERS_LANGUE.get(code_iso.lower()[:2], "autre")


class ConfigurationDossier(BaseModel):
    """
    Configuration de la session de collecte WhatsApp.

    langue_cible : langue dans laquelle Mathilde doit répondre à l'usager.
                   Mise à jour automatiquement par l'Agent Traducteur (Agent 0)
                   dès le premier message.
    canal_cible  : "texte" (WhatsApp écrit) ou "vocal" (transcription vocale).
                   Bascule sur "vocal" dès qu'un message audio est reçu.
    """
    langue_cible: ConfigurationLangue = "français"
    canal_cible:  ConfigurationCanal  = "texte"


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-CLASSE : Identité d'une personne (réutilisable)
# ─────────────────────────────────────────────────────────────────────────────

class IdentitePersonne(BaseModel):
    nom:     Optional[str] = None
    prenom:  Optional[str] = None
    qualite: Optional[str] = None   # "Tuteur" | "Curateur" | "Mandataire judiciaire"


# ─────────────────────────────────────────────────────────────────────────────
# SOUS-CLASSE : Situation juridique (Section A4)
# Remplace l'ancien champ str "protection_juridique".
# ─────────────────────────────────────────────────────────────────────────────

class SituationJuridique(BaseModel):
    """
    Mesure de protection juridique et identité du représentant légal.

    Règle d'extraction LLM :
    - "sous tutelle de mon mari Jean Dupont" →
        sous_protection=True, type_mesure="tutelle",
        identite_representant=IdentitePersonne(nom="Dupont", prenom="Jean", qualite="Tuteur")
    - "je gère seul" | "pas de tuteur" →
        sous_protection=False, type_mesure="aucune"   ← JAMAIS None
    """
    sous_protection:       bool = False
    type_mesure:           Literal["tutelle", "curatelle", "sauvegarde", "aucune"] = "aucune"
    identite_representant: Optional[IdentitePersonne] = None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION A — Identité administrative (Pages 1-3)
# ─────────────────────────────────────────────────────────────────────────────

class SectionA_Identite(BaseModel):
    nom:                  Optional[str] = None
    prenom:               Optional[str] = None
    date_naissance:       Optional[str] = None    # JJ/MM/AAAA
    genre:                Optional[str] = None    # "homme" | "femme"
    adresse_complete:     Optional[str] = None
    situation_familiale:  Optional[str] = None
    enfants_a_charge:     Optional[int] = None
    organisme_payeur:     Optional[str] = None    # "CAF" | "MSA"
    situation_juridique:  SituationJuridique = SituationJuridique()
    historique_mdph:      Optional[str] = None
    type_demande:         Optional[str] = None    # calculé par model_validator
    numero_securite_sociale: Optional[str] = None
    # ── Accessibilité et contact ─────────────────────────────────────────────
    langue_usager:        str  = "fr"    # code ISO 639-1 : "ar", "en", "es", "fr"…
    canal_prefere_vocal:  bool = False   # True dès que l'usager interagit par la voix
    numero_allocataire:   Optional[str] = None   # N° allocataire CAF ou MSA
    mode_contact:         Optional[Literal["email", "courrier"]] = None

    @field_validator("numero_securite_sociale")
    @classmethod
    def valider_nir(cls, v: str | None) -> str | None:
        if v is None:
            return v
        cleaned = re.sub(r"[\s.\-]", "", v)
        if not re.fullmatch(r"\d{15}", cleaned):
            raise ValueError(f"NIR invalide : 15 chiffres requis (reçu : {v!r})")
        return cleaned

    @model_validator(mode="after")
    def forcer_renouvellement_si_historique(self) -> "SectionA_Identite":
        if self.historique_mdph and any(c.isdigit() for c in self.historique_mdph):
            self.type_demande = "renouvellement"
        return self


# ─────────────────────────────────────────────────────────────────────────────
# SECTION B — Vie scolaire (Pages 9-12)
# Active uniquement pour profil "enfant" et "mixte" (16-18 ans).
# Auto-éliminée (None) pour les adultes.
# ─────────────────────────────────────────────────────────────────────────────

class SectionB_VieScolaire(BaseModel):
    nom_etablissement:    Optional[str]  = None
    type_etablissement:   Optional[str]  = None   # "classe ordinaire", "ULIS", "IME"…
    classe_actuelle:      Optional[str]  = None
    a_aesh:               bool           = False
    a_pps:                bool           = False
    a_pai:                bool           = False
    a_ulis:               bool           = False
    gevasco_disponible:   Optional[bool] = None   # None = non encore demandé
    # ── Autodétermination — Règle B ──────────────────────────────────────────
    opposition_ime:             bool = False   # True = parents refusent IME
    scolarisation_ordinaire:    bool = False   # True = priorité milieu ordinaire confirmée


# ─────────────────────────────────────────────────────────────────────────────
# SECTION C — Vie quotidienne & besoins (Pages 5-7)
# Toujours active. Retentissements fonctionnels UNIQUEMENT.
# ─────────────────────────────────────────────────────────────────────────────

class SectionC_VieQuotidienne(BaseModel):
    difficultes_quotidiennes:   Optional[str]  = None
    besoins_aide_humaine:       bool           = False
    besoins_aide_technique:     bool           = False
    besoins_amenagement_logement: bool         = False
    type_logement:              Optional[str]  = None
    statut_occupation:          Optional[Literal["proprietaire", "locataire", "heberge"]] = None
    utilise_fauteuil_roulant:   bool           = False
    difficulte_marcher:         bool           = False
    besoin_aide_toilette:       bool           = False
    ressources_actuelles:       Optional[str]  = None
    frais_reels:                Optional[str]  = Field(
        default=None,
        description=(
            "Frais financiers uniquement (matériel, soins privés, transport). "
            "INTERDIT : aide humaine gratuite d'un proche, prestations CAF/MSA."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# SECTION D — Situation professionnelle actuelle (Pages 13-16)
# Active pour profil "adulte_actif" et "mixte".
# ─────────────────────────────────────────────────────────────────────────────

class SectionD_SituationPro(BaseModel):
    statut: Optional[Literal[
        "emploi", "recherche", "formation", "inactif", "retraite", "inconnu"
    ]] = None
    nom_employeur:            Optional[str]  = None
    poste_occupe:             Optional[str]  = None
    niveau_qualification:     Optional[str]  = None   # CAP, BAC, BTS…
    accident_travail:         bool           = False
    date_accident_travail:    Optional[str]  = None
    date_debut_sans_emploi:   Optional[str]  = None   # JJ/MM/AAAA — si statut = "recherche"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION E — Projet professionnel & droits demandés (Pages 17-18)
# Active pour profil "adulte_actif" et "mixte".
# ─────────────────────────────────────────────────────────────────────────────

class SectionE_ProjetPro(BaseModel):
    type_droits:          list[str]       = Field(default_factory=list)  # ["RQTH", "AAH"…]
    cmi_priorite:         bool            = False   # station debout pénible
    cmi_stationnement:    bool            = False   # déplacements < 200 m
    emploi_accompagne:    bool            = False
    projet_professionnel: Optional[str]   = None

    # ── Booléens d'orientation — forcés par l'Agent 3 ────────────────────────
    # Règle 3 — ESRP (alias : Richebois, Visa Pro, CRP, ESRP, CPO, UEROS)
    orientation_esrp:  bool = False   # Case P18 3 — Réadaptation professionnelle
    # Règle 2 — ESPO (projet non défini, "trouver sa voie")
    orientation_espo:  bool = False   # Pré-orientation — projet à construire
    orientation_esat:  bool = False   # Case P18 4 — Milieu protégé
    orientation_rqth:  bool = False   # Case P18 1 — Reconnaissance travailleur handicapé
    orientation_ea:    bool = False   # Entreprise adaptée


# ─────────────────────────────────────────────────────────────────────────────
# SECTION F — Vie de l'aidant familial (Pages 19-20)
# ─────────────────────────────────────────────────────────────────────────────

class AidantFamilial(BaseModel):
    """
    Aidant qui accompagne la personne au quotidien.

    Règles d'extraction LLM :
    - "Mon mari Pierre Durand m'aide tous les jours" →
        a_un_aidant=True, prenom="Pierre", nom="Durand", lien_parental="époux"
    - "personne" | "je me débrouille" →
        a_un_aidant=False  ← JAMAIS None — pages 19-20 entièrement vides.

    RÈGLE ABSOLUE : Toute aide humaine gratuite d'un proche va ici.
    Elle ne doit JAMAIS apparaître dans SectionC.frais_reels.
    """
    a_un_aidant:   bool           = False
    nom:           Optional[str]  = None
    prenom:        Optional[str]  = None
    lien_parental: Optional[str]  = None   # "époux", "mère", "fils"…
    nature_aide:   Optional[str]  = None   # "aide quotidienne", "soins", "déplacements"…


class SectionF_VieAidant(BaseModel):
    aidant: AidantFamilial = AidantFamilial()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION URGENCE — Alerte expiration droits
# ─────────────────────────────────────────────────────────────────────────────

class Section_Urgence(BaseModel):
    """
    Activée si expiration des droits dans moins de 2 mois.
    est_urgent = False par défaut — JAMAIS supposé True sans confirmation explicite.
    """
    est_urgent:              bool           = False
    date_expiration_droits:  Optional[date] = None

    @model_validator(mode="after")
    def calculer_urgence(self) -> "Section_Urgence":
        """Si date_expiration connue et < 2 mois → forcer est_urgent = True."""
        if self.date_expiration_droits and not self.est_urgent:
            delta = (self.date_expiration_droits - date.today()).days
            if 0 <= delta <= 60:
                self.est_urgent = True
        return self


# ─────────────────────────────────────────────────────────────────────────────
# MODÈLE PRINCIPAL — DossierCERFA complet
# ─────────────────────────────────────────────────────────────────────────────

class DossierCERFA(BaseModel):
    profil:          ProfilMDPH             = "inconnu"
    configuration:   ConfigurationDossier   = ConfigurationDossier()
    section_a:       SectionA_Identite      = SectionA_Identite()
    section_b:       Optional[SectionB_VieScolaire]  = None
    section_c:       SectionC_VieQuotidienne = SectionC_VieQuotidienne()
    section_d:       Optional[SectionD_SituationPro] = None
    section_e:       Optional[SectionE_ProjetPro]    = None
    section_f:       SectionF_VieAidant     = SectionF_VieAidant()
    section_urgence: Section_Urgence        = Section_Urgence()
    cases_cerfa:     dict                   = Field(default_factory=dict)

    @model_validator(mode="after")
    def router_profil(self) -> "DossierCERFA":
        """
        Routeur de profil — deux responsabilités :

        1. Auto-calcul du profil depuis section_a.date_naissance si profil == "inconnu"
           Délègue à profile_engine pour avoir UNE seule source de vérité sur les seuils.

        2. Activation / désactivation des sections selon le profil calculé :
           enfant  (≤ 15 ans)  → B activée, D/E supprimées
           mixte   (16-25 ans) → B + D + E toutes actives (règle équipe mixte)
           adulte  (> 25 ans)  → B supprimée, D + E actives
           inconnu             → aucun élagage
        """
        # ── 1. Calcul automatique du profil depuis la date de naissance ───────
        if self.profil == "inconnu" and self.section_a.date_naissance:
            try:
                from app.engines.profile_engine import calculer_profil
                profil_calc = calculer_profil(self.section_a.date_naissance)
                if profil_calc:
                    self.profil = profil_calc.profil_mdph  # type: ignore[assignment]
            except Exception:
                pass   # import circulaire toléré en mode test — profil reste "inconnu"

        # ── 2. Élagage / activation des sections ─────────────────────────────
        if self.profil == "enfant":
            if self.section_b is None:
                self.section_b = SectionB_VieScolaire()
            self.section_d = None
            self.section_e = None

        elif self.profil == "mixte":
            if self.section_b is None:
                self.section_b = SectionB_VieScolaire()
            if self.section_d is None:
                self.section_d = SectionD_SituationPro()
            if self.section_e is None:
                self.section_e = SectionE_ProjetPro()

        elif self.profil == "adulte":
            self.section_b = None
            if self.section_d is None:
                self.section_d = SectionD_SituationPro()
            if self.section_e is None:
                self.section_e = SectionE_ProjetPro()

        return self

    def champs_obligatoires_manquants(self) -> list[str]:
        """
        Retourne les champs bloquant le score 100 %.
        N'évalue que les sections actives selon le profil — jamais de faux manquants.

        Profil mixte : C ET D évaluées (règle équipe mixte).
        """
        manquants: list[str] = []

        # Section A — toujours obligatoire
        for champ in ["nom", "prenom", "date_naissance", "adresse_complete",
                      "organisme_payeur", "type_demande"]:
            if not getattr(self.section_a, champ):
                manquants.append(f"A.{champ}")

        # Section C — toujours obligatoire
        if not self.section_c.difficultes_quotidiennes:
            manquants.append("C.difficultes_quotidiennes")

        # Section B — enfant et mixte
        if self.profil in ("enfant", "mixte") and self.section_b:
            if not self.section_b.nom_etablissement:
                manquants.append("B.nom_etablissement")

        # Section D — adulte ET mixte
        if self.profil in ("adulte", "mixte") and self.section_d:
            if not self.section_d.statut:
                manquants.append("D.statut")

        # Section E — adulte ET mixte
        if self.profil in ("adulte", "mixte") and self.section_e:
            if not self.section_e.type_droits:
                manquants.append("E.type_droits")

        return manquants
