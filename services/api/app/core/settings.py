from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Keys from MVP TZ §8.4. Defaults keep local tests offline."""

    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    domain: str = "localhost"
    postgres_dsn: str = "postgresql+asyncpg://fsp:fsp@localhost:5432/fsp"
    redis_url: str = "redis://localhost:6379/0"
    keycloak_issuer: str = "http://localhost/auth/realms/fsp"
    keycloak_client_id: str = "career-web"
    keycloak_client_secret: str = "change-me"
    llm_base_url: str = "https://llm-provider.example/v1"
    llm_api_key: str = "change-me"
    llm_model: str = "qwen3-14b"
    llm_enabled: bool = False
    embedding_model: str = "intfloat/multilingual-e5-base"
    piston_url: str = "http://piston:2000"
    piston_enabled: bool = False
    match_alpha: float = 1.0
    match_beta: float = 0.15
    upload_dir: str = "/data/uploads"
    taxonomy_dir: str = "taxonomy/data"


@lru_cache
def get_settings() -> Settings:
    return Settings()
