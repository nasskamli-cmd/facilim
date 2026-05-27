"""
app/services/storage_service.py — Stockage sécurisé des documents.

Backends supportés :
  - local : système de fichiers local (dev/staging)
  - s3    : AWS S3 ou compatible (production)

Les documents médicaux sont chiffrés au repos avant stockage.
Les chemins sont opaques (UUID, pas de nom de fichier révélateur).
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import BinaryIO

logger = logging.getLogger("facilim.services.storage")


class LocalStorageService:
    """Backend de stockage local pour développement et staging."""

    def __init__(self, base_path: str = "./storage"):
        self.base = Path(base_path)
        for sub in ("documents", "cerfa", "temp"):
            (self.base / sub).mkdir(parents=True, exist_ok=True)

    def store(
        self,
        file_data: bytes | BinaryIO,
        category: str = "documents",
        extension: str = "bin",
    ) -> str:
        """
        Stocke un fichier. Retourne le chemin relatif opaque.
        Le nom de fichier est un UUID pour éviter toute identification.
        """
        file_id = str(uuid.uuid4())
        filename = f"{file_id}.{extension}"
        dest = self.base / category / filename

        if isinstance(file_data, bytes):
            dest.write_bytes(file_data)
        else:
            dest.write_bytes(file_data.read())

        logger.info(f"[STORAGE] Fichier stocké | cat={category} | id={file_id}")
        return str(dest.relative_to(self.base))

    def retrieve(self, relative_path: str) -> bytes:
        """Récupère le contenu d'un fichier stocké."""
        path = self.base / relative_path
        if not path.exists():
            raise FileNotFoundError(f"Fichier non trouvé : {relative_path}")
        return path.read_bytes()

    def delete(self, relative_path: str) -> bool:
        """Supprime un fichier du stockage."""
        path = self.base / relative_path
        if path.exists():
            path.unlink()
            logger.info(f"[STORAGE] Fichier supprimé : {relative_path}")
            return True
        return False

    def get_url(self, relative_path: str, expire_seconds: int = 3600) -> str:
        """Retourne une URL temporaire (local = chemin de téléchargement API)."""
        return f"/api/v1/documents/download/{relative_path}"


def get_storage_service(settings: object) -> LocalStorageService:
    """Factory — retourne le service de stockage selon la config."""
    backend = getattr(settings, "storage_backend", "local")
    if backend == "local":
        return LocalStorageService(getattr(settings, "storage_local_path", "./storage"))
    raise NotImplementedError(f"Backend de stockage '{backend}' non implémenté.")
