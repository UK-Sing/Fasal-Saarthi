from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # Repo-root .env first, backend/.env (if any) overrides; real env vars override both.
    model_config = SettingsConfigDict(env_file=(_BACKEND.parent / ".env", _BACKEND / ".env"), extra="ignore")
    # firestore (primary) | sqlite (offline fallback, uses database_url) | memory (tests)
    database_backend: Literal["firestore", "sqlite", "memory"] = "sqlite"
    database_url: str = "sqlite:///./fasal.db"
    firebase_project_id: str = ""
    firebase_credentials: str = ""  # path to service-account JSON, exported as GOOGLE_APPLICATION_CREDENTIALS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    use_live_data: bool = False
    data_gov_api_key: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    # If set, every endpoint except /health requires header `X-API-Key: <value>`.
    api_key: str = ""


settings = Settings()
