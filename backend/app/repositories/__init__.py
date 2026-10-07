from ..config import settings
from .base import NotFound, Repository

__all__ = ["NotFound", "Repository", "build_repository", "get_repo"]


def build_repository(cfg) -> Repository:
    if cfg.database_backend == "firestore":
        try:
            from .firestore import FirestoreRepository
            return FirestoreRepository(project_id=cfg.firebase_project_id,
                                       credentials_path=cfg.firebase_credentials)
        except Exception as e:
            raise RuntimeError(
                f"Firestore backend selected but initialisation failed: {e}. "
                "Set DATABASE_BACKEND=sqlite in .env for the offline fallback.") from e
    if cfg.database_backend == "memory":
        from .memory import InMemoryRepository
        return InMemoryRepository()
    from ..db import get_engine, init_db
    from .sql import SQLRepository
    init_db()
    return SQLRepository(get_engine())


_repo: Repository | None = None


def get_repo() -> Repository:
    global _repo
    if _repo is None:
        _repo = build_repository(settings)
    return _repo
