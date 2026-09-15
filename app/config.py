from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "Exam Finding"
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'exam_finding.db'}"
    source_config_path: Path = PROJECT_ROOT / "config" / "sources.yaml"
    division_seed_path: Path = PROJECT_ROOT / "config" / "divisions.csv"
    raw_data_path: Path = PROJECT_ROOT / "data" / "raw"
    crawler_user_agent: str = "ExamFinding/0.1 (personal research; low frequency)"
    max_raw_document_bytes: int = 10 * 1024 * 1024

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="EXAM_FINDING_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
