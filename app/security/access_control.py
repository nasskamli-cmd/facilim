"""
app/security/access_control.py — Contrôle d'accès basé sur les rôles (RBAC).

Rôles Facilim :
  SUPER_ADMIN     → accès total à toutes les organisations
  ADMIN_ESSMS     → accès total à son organisation uniquement
  EDUCATEUR       → accès aux dossiers de son organisation, création et suivi
  LECTEUR         → accès lecture seule aux dossiers de son organisation
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger("facilim.security.access")


class Role(str, Enum):
    SUPER_ADMIN  = "SUPER_ADMIN"
    ADMIN_ESSMS  = "ADMIN_ESSMS"
    EDUCATEUR    = "EDUCATEUR"
    LECTEUR      = "LECTEUR"


class Permission(str, Enum):
    # Dossiers
    DOSSIER_CREATE     = "dossier:create"
    DOSSIER_READ       = "dossier:read"
    DOSSIER_UPDATE     = "dossier:update"
    DOSSIER_DELETE     = "dossier:delete"
    DOSSIER_SUBMIT     = "dossier:submit"
    DOSSIER_EXPORT     = "dossier:export"
    # Documents médicaux
    MEDICAL_READ       = "medical:read"
    MEDICAL_WRITE      = "medical:write"
    # Validation humaine
    HUMAN_VALIDATE     = "human:validate"
    FLAG_MANAGE        = "flag:manage"
    # Administration
    USER_MANAGE        = "user:manage"
    ORG_MANAGE         = "org:manage"
    AUDIT_READ         = "audit:read"
    RGPD_MANAGE        = "rgpd:manage"
    # Consentements
    CONSENT_READ       = "consent:read"
    CONSENT_MANAGE     = "consent:manage"


_ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SUPER_ADMIN: set(Permission),  # tout

    Role.ADMIN_ESSMS: {
        Permission.DOSSIER_CREATE,
        Permission.DOSSIER_READ,
        Permission.DOSSIER_UPDATE,
        Permission.DOSSIER_DELETE,
        Permission.DOSSIER_SUBMIT,
        Permission.DOSSIER_EXPORT,
        Permission.MEDICAL_READ,
        Permission.MEDICAL_WRITE,
        Permission.HUMAN_VALIDATE,
        Permission.FLAG_MANAGE,
        Permission.USER_MANAGE,
        Permission.AUDIT_READ,
        Permission.CONSENT_READ,
        Permission.CONSENT_MANAGE,
    },

    Role.EDUCATEUR: {
        Permission.DOSSIER_CREATE,
        Permission.DOSSIER_READ,
        Permission.DOSSIER_UPDATE,
        Permission.DOSSIER_SUBMIT,
        Permission.MEDICAL_READ,
        Permission.MEDICAL_WRITE,
        Permission.HUMAN_VALIDATE,
        Permission.FLAG_MANAGE,
        Permission.CONSENT_READ,
    },

    Role.LECTEUR: {
        Permission.DOSSIER_READ,
        Permission.MEDICAL_READ,
        Permission.CONSENT_READ,
    },
}


class AccessDenied(Exception):
    """Levée quand un utilisateur tente une action non autorisée."""
    pass


def has_permission(role: str, permission: Permission) -> bool:
    """Vérifie si un rôle possède une permission."""
    try:
        r = Role(role)
    except ValueError:
        logger.warning(f"[RBAC] Rôle inconnu : {role}")
        return False
    return permission in _ROLE_PERMISSIONS.get(r, set())


def require_permission(role: str, permission: Permission) -> None:
    """Lève AccessDenied si la permission est manquante."""
    if not has_permission(role, permission):
        msg = f"Permission refusée : rôle={role}, permission={permission}"
        logger.warning(f"[RBAC] {msg}")
        raise AccessDenied(msg)


def can_access_dossier(
    utilisateur: dict[str, Any],
    dossier: dict[str, Any],
) -> bool:
    """
    Un EDUCATEUR/LECTEUR ne peut voir que les dossiers de son organisation.
    Un SUPER_ADMIN voit tout.
    """
    role = utilisateur.get("role", "")
    if role == Role.SUPER_ADMIN:
        return True
    org_user = utilisateur.get("organisation_id")
    org_dossier = dossier.get("organisation_id")
    return org_user is not None and org_user == org_dossier


def audit_medical_access(
    utilisateur_id: str,
    dossier_id: str,
    operation: str,
    justification: str,
) -> dict[str, Any]:
    """Construit le payload d'audit pour un accès aux données médicales."""
    return {
        "utilisateur_id": utilisateur_id,
        "dossier_id": dossier_id,
        "table_accedee": "donnees_medicales",
        "operation": operation,
        "justification": justification,
    }
